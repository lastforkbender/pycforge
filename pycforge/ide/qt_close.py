"""Guarded modal choices and non-blocking close flow for the Qt workspace."""

from __future__ import annotations

from concurrent.futures import Future
from typing import Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class QtCloseMixin:
    """Keep destructive choices explicit and shutdown off the event loop."""

    def _confirm_discard(self, logical_name: str) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle("Discard unsaved module?")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"{logical_name} has unsaved changes. "
            "Removing it discards those changes."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox()
        discard = buttons.addButton(
            "Discard Module", QDialogButtonBox.DestructiveRole
        )
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        discard.clicked.connect(lambda: dialog.done(1))
        cancel.clicked.connect(lambda: dialog.done(0))
        layout.addWidget(buttons)
        return dialog.exec_() == 1

    def _confirm_reload(self, logical_name: str) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle("Reload linked Python file?")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        label = QLabel(
            f"{logical_name} has unsaved changes. Reloading replaces "
            "them with the explicitly selected disk version."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        buttons = QDialogButtonBox()
        reload_button = buttons.addButton(
            "Reload from Disk", QDialogButtonBox.DestructiveRole
        )
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        reload_button.clicked.connect(lambda: dialog.done(1))
        cancel.clicked.connect(lambda: dialog.done(0))
        layout.addWidget(buttons)
        return dialog.exec_() == 1

    def _unsaved_choice(self, documents: tuple[Any, ...]) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle("Unsaved Python documents")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        names = "\n".join(
            f"• {item.logical_name}" for item in documents[:8]
        )
        if len(documents) > 8:
            names += f"\n• and {len(documents) - 8} more"
        label = QLabel(
            "Save modified Python documents before closing?\n\n"
            + names
        )
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)
        buttons = QDialogButtonBox()
        save = buttons.addButton(
            "Save All", QDialogButtonBox.AcceptRole
        )
        discard = buttons.addButton(
            "Discard", QDialogButtonBox.DestructiveRole
        )
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        save.clicked.connect(lambda: dialog.done(1))
        discard.clicked.connect(lambda: dialog.done(2))
        cancel.clicked.connect(lambda: dialog.done(0))
        layout.addWidget(buttons)
        result = dialog.exec_()
        return {1: "save", 2: "discard"}.get(result, "cancel")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._closing:
            self._close_workspace_features()
            event.accept()
            return
        if self._close_save_pending:
            event.ignore()
            return
        if not self._flush_pending_source_sync():
            event.ignore()
            return
        dirty = tuple(
            item for item in self.controller.snapshot.documents
            if item.dirty
        )
        if dirty:
            choice = self._unsaved_choice(dirty)
            if choice == "cancel":
                event.ignore()
                return
            if choice == "save":
                futures: list[Future] = []
                for document in dirty:
                    future = self._save_document(
                        document.document_id
                    )
                    if future is None:
                        event.ignore()
                        return
                    futures.append(future)
                self._close_save_pending = len(futures)
                self._close_save_failed = False
                for future in futures:
                    self._dispatch_io(
                        future,
                        self._close_save_completed,
                    )
                event.ignore()
                return
        self._closing = True
        self._persist_workspace_state()
        self.controller.unsubscribe(self._snapshot_listener)
        self._close_workspace_features()
        self.controller.close(wait=False)
        event.accept()

    def _close_save_completed(self, future: Future) -> None:
        try:
            future.result()
        except Exception:
            self._close_save_failed = True
        self._close_save_pending = max(
            0, self._close_save_pending - 1
        )
        if self._close_save_pending:
            return
        if self._close_save_failed:
            self.toast.show_message(
                "Close paused because at least one Python file "
                "was not saved.",
                "warning",
            )
            return
        if any(
            item.dirty
            for item in self.controller.snapshot.documents
        ):
            self.toast.show_message(
                "Close paused because source changed while "
                "files were saving.",
                "warning",
            )
            return
        QTimer.singleShot(0, self.close)


__all__ = ["QtCloseMixin"]
