"""Document, conversion, search, and navigation actions for the Qt workspace."""
from __future__ import annotations

import re
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog

from .qt_contract import (
    diagnostic_character_range,
    mapping_character_range,
    qt_range,
)


class QtDocumentActionsMixin:
    """Cohesive document and conversion interaction surface for MainWindow."""
    def _source_changed(self) -> None:
        """Coalesce actual source edits without per-keystroke copies."""
        document_id = self._displayed_document_id
        if document_id is None or self._applying_source_text:
            return
        # Syntax highlighting emits textChanged without modifying characters.
        if not self.source_buffers.is_modified(document_id):
            return
        self._source_sync_document_id = document_id
        self._source_sync_pending = True
        self._source_sync_timer.start()
        self._invalidate_source_observers()
        if self.controller.snapshot.can_cancel:
            self.controller.cancel()
        self._present_pending_source_sync()

    def _present_pending_source_sync(self) -> None:
        """Expose unsynchronized edits as immediately stale and unsavable."""
        if not self._source_sync_pending:
            return
        self.action_registry.refresh()
        self.state_chip.setText("EDIT PENDING")
        self._set_dynamic_property(self.state_chip, "status", "warning")
        if self.controller.snapshot.generated_c is not None:
            self.output_state_label.setText("STALE · EDIT PENDING")
            self._set_dynamic_property(self.output_state_label, "status", "warning")

    def _present_pending_identity_edit(self, pending: bool) -> None:
        """Project navigator identity edits before focus commits them."""

        if pending and self.controller.snapshot.can_cancel:
            self.controller.cancel()
        self.action_registry.refresh()
        if not pending:
            if self._source_sync_pending:
                self._present_pending_source_sync()
            else:
                snapshot = self.controller.snapshot
                self._set_state_chip(snapshot.state.value)
                self._set_output_state(snapshot)
            return
        if self._source_sync_pending:
            self._present_pending_source_sync()
            return
        self.state_chip.setText("IDENTITY EDIT PENDING")
        self._set_dynamic_property(self.state_chip, "status", "warning")
        if self.controller.snapshot.generated_c is not None:
            self.output_state_label.setText(
                "STALE · IDENTITY EDIT PENDING"
            )
            self._set_dynamic_property(
                self.output_state_label, "status", "warning"
            )

    def _flush_pending_source_sync(self) -> bool:
        """Publish the latest editor text once before a semantic operation."""

        if not self._source_sync_pending:
            return True
        document_id = self._source_sync_document_id
        if document_id is None:
            self._source_sync_pending = False
            self._source_sync_timer.stop()
            return True
        text = self.source.toPlainText()
        self._source_sync_pending = False
        self._source_sync_timer.stop()
        # update_document stores this exact immutable string.  Pre-keying the
        # projection prevents its synchronous snapshot from reloading the
        # editor and moving the user's cursor after each coalesced edit.
        self._displayed_source_key = (document_id, id(text))
        try:
            updated = self.controller.update_document(document_id, text)
        except Exception as exc:
            self._source_sync_pending = True
            self._source_sync_timer.start()
            self._show_error("Source edit could not be recorded", exc)
            return False
        # The edit may have returned to the controller's exact prior text, in
        # which case update_document publishes no snapshot. Normalize the key
        # to the retained object and refresh local chrome without reloading the
        # editor or moving its cursor.
        self._displayed_source_key = (
            document_id,
            id(updated.text),
        )
        self.source_buffers.mark_synchronized(
            document_id, id(updated.text), dirty=updated.dirty
        )
        self._apply_snapshot(self.controller.snapshot)
        return True

    def _dispatch_io(
        self, future: Future, callback: Callable[[Future], None]
    ) -> None:
        future.add_done_callback(
            lambda completed: self.io_finished.emit(callback, completed)
        )

    def open_file(self) -> None:
        if not self._commit_pending_identity():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Python Source Bundle",
            self._last_directory,
            "Python (*.py);;All files (*)",
        )
        for value in paths:
            self._open_path(Path(value))

    def _open_path(self, path: Path) -> None:
        if not self._commit_pending_identity():
            return
        try:
            snapshot = self.controller.snapshot
            existing = next(
                (
                    item for item in snapshot.documents
                    if item.path is not None and Path(item.path) == path
                ),
                None,
            )
            if existing is not None:
                if existing.dirty and not self._confirm_reload(
                    existing.logical_name
                ):
                    return
                future = self.controller.open_document_async(
                    path,
                    document_id=existing.document_id,
                    make_active=True,
                )
                message = (
                    f"Reloaded {path.name} from its linked Python file."
                )
            else:
                active = snapshot.active_document
                replace_blank = bool(
                    len(snapshot.documents) == 1
                    and not active.text
                    and active.path is None
                    and not active.dirty
                )
                module_id = self._unique_module_id(
                    path.stem,
                    active.document_id if replace_blank else None,
                )
                logical_name = self._unique_logical_name(
                    path.name,
                    active.document_id if replace_blank else None,
                )
                future = self.controller.open_document_async(
                    path,
                    module_id=module_id,
                    logical_name=logical_name,
                    document_id=active.document_id if replace_blank else None,
                    make_active=True,
                )
                message = f"Opened {path.name} in the source bundle."
        except Exception as exc:
            self._show_error("Could not open Python source", exc)
            return

        def opened(completed: Future) -> None:
            try:
                completed.result()
            except Exception as exc:
                self._show_error("Could not open Python source", exc)
                return
            self._remember_path(path)
            self.toast.show_message(message, "info")

        self._dispatch_io(future, opened)

    def add_document(self) -> None:
        if not self._commit_pending_identity():
            return
        snapshot = self.controller.snapshot
        if not snapshot.can_add_document:
            self.toast.show_message(
                "The 64-document workspace capacity is full.", "warning"
            )
            return
        index = len(snapshot.documents) + 1
        try:
            module_id = self._unique_module_id(f"module_{index}")
            logical_name = self._unique_logical_name(f"module_{index}.py")
            self.controller.add_document(module_id, logical_name)
        except Exception as exc:
            self._show_error("Could not add a module", exc)

    def remove_active_document(self) -> None:
        self._remove_document(self.controller.snapshot.active_document_id)

    def _remove_document(self, document_id: str) -> None:
        if not self._commit_pending_identity():
            return
        try:
            document = next(
                item for item in self.controller.snapshot.documents
                if item.document_id == document_id
            )
        except StopIteration:
            self.toast.show_message(
                "The selected module no longer exists.", "warning"
            )
            return
        if document.dirty and not self._confirm_discard(document.logical_name):
            return
        try:
            self.controller.remove_document(document_id)
        except Exception as exc:
            self._show_error("Could not remove the module", exc)

    def _select_document(self, document_id: str) -> None:
        if not self._commit_pending_identity():
            return
        try:
            self.controller.select_document(document_id)
        except Exception as exc:
            self._show_error("Could not select the module", exc)

    def _change_document_identity(
        self, document_id: str, module_id: str, logical_name: str
    ) -> None:
        if not self._flush_pending_source_sync():
            return
        try:
            self.controller.set_document_identity(
                document_id,
                module_id=module_id,
                logical_name=logical_name,
            )
        except Exception as exc:
            self._show_error("Document identity was not accepted", exc)
            self._navigator_key = None
            self._apply_snapshot(self.controller.snapshot)

    def _set_primary_document(self, document_id: str) -> None:
        if not self._commit_pending_identity():
            return
        try:
            self.controller.set_primary_document(document_id)
        except Exception as exc:
            self._show_error("Could not set the primary module", exc)

    def _move_document_up(self, document_id: str | None = None) -> None:
        self._move_document(document_id, -1)

    def _move_document_down(self, document_id: str | None = None) -> None:
        self._move_document(document_id, 1)

    def _move_document(self, document_id: str | None, delta: int) -> None:
        """Move one document while preserving the controller's full order."""

        if not self._commit_pending_identity():
            return
        identifier = document_id or self.navigator.current_document_id
        if identifier is None:
            return
        identifiers = [
            item.document_id for item in self.controller.snapshot.documents
        ]
        try:
            index = identifiers.index(identifier)
        except ValueError:
            self.toast.show_message(
                "The selected module no longer exists.", "warning"
            )
            return
        destination = index + delta
        if destination < 0 or destination >= len(identifiers):
            return
        identifiers[index], identifiers[destination] = (
            identifiers[destination],
            identifiers[index],
        )
        try:
            self.controller.reorder_documents(identifiers)
        except Exception as exc:
            self._show_error("Could not reorder the source bundle", exc)

    def save_source(self) -> bool:
        if not self._commit_pending_identity():
            return False
        return (
            self._save_document(
                self.controller.snapshot.active_document_id
            )
            is not None
        )

    def save_source_as(self) -> bool:
        if not self._commit_pending_identity():
            return False
        return (
            self._save_document(
                self.controller.snapshot.active_document_id,
                force_dialog=True,
            )
            is not None
        )

    def _save_document(
        self, document_id: str, *, force_dialog: bool = False
    ) -> Future | None:
        document = next(
            item for item in self.controller.snapshot.documents
            if item.document_id == document_id
        )
        destination = None if force_dialog else document.path
        if destination is None:
            suggested = (
                str(Path(self._last_directory) / document.logical_name)
                if self._last_directory
                else document.logical_name
            )
            destination, _ = QFileDialog.getSaveFileName(
                self,
                "Save Python Document",
                suggested,
                "Python (*.py)",
            )
            if not destination:
                return None
        try:
            future = self.controller.save_document_async(
                document_id,
                Path(destination),
            )
        except Exception as exc:
            self._show_error("Could not save Python source", exc)
            return None

        def saved(completed: Future) -> None:
            try:
                completed.result()
            except Exception as exc:
                self._show_error("Could not save Python source", exc)
                return
            self._remember_path(Path(destination))
            self.toast.show_message(
                f"Saved Python: {destination}",
                "success",
            )

        self._dispatch_io(future, saved)
        return future

    def link_c_file(self) -> None:
        snapshot = self.controller.snapshot
        suggested = snapshot.linked_c_path or (
            str(Path(self._last_directory) / "generated.c")
            if self._last_directory else "generated.c"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Link Generated C Destination",
            suggested,
            "C source (*.c)",
        )
        if not path:
            return
        try:
            self.controller.link_generated_c(Path(path))
        except Exception as exc:
            self._show_error("Could not link the C destination", exc)
            return
        self._last_directory = str(Path(path).parent)
        self.toast.show_message(
            f"Generated C is linked to {path}. "
            "Use Save C after a fresh transpilation.",
            "success",
        )

    def save_c(self) -> bool:
        # Identity edits are semantic bundle edits even while they remain
        # in the navigator's line edits.  Commit and validate them before
        # consulting freshness so a shortcut cannot publish obsolete C.
        if not self._commit_pending_identity():
            return False
        snapshot = self.controller.snapshot
        if not snapshot.can_save_c:
            self.toast.show_message(
                "Generated C is unavailable or stale. "
                "Transpile the current bundle first.",
                "warning",
            )
            return False
        if snapshot.linked_c_path is None:
            self.link_c_file()
            snapshot = self.controller.snapshot
            if snapshot.linked_c_path is None:
                return False
        try:
            future = self.controller.save_generated_c_linked_async()
        except Exception as exc:
            self._show_error("Could not save generated C", exc)
            return False

        def saved(completed: Future) -> None:
            try:
                destination = completed.result()
            except Exception as exc:
                self._show_error("Could not save generated C", exc)
                return
            self._last_directory = str(Path(destination).parent)
            self.toast.show_message(
                f"Saved fresh generated C: {destination}",
                "success",
            )

        self._dispatch_io(future, saved)
        return True

    def convert(self) -> None:
        if not self._flush_pending_source_sync():
            return
        if not self._commit_pending_identity():
            return
        try:
            future = self.controller.convert_async()
        except Exception as exc:
            self._show_error("Transpilation could not start", exc)
            return
        future.add_done_callback(self._conversion_finished)

    def _conversion_finished(self, future: Future) -> None:
        try:
            future.result()
        except Exception as exc:
            if self._closing:
                return
            self.operation_error.emit(
                f"The transpilation worker stopped unexpectedly: {exc}"
            )

    def _open_find(self, replace: bool) -> None:
        target = self._resolved_action_target()
        editor = (
            target if target in (self.source, self.source_secondary)
            else self.output if target is self.output and not replace
            else self.source
        )
        self.find_bar.attach_editor(editor)
        self.find_bar.open_find(replace and not editor.isReadOnly())

    def _activate_diagnostic(self, diagnostic: dict[str, Any]) -> None:
        logical_name = diagnostic.get("source_logical_name")
        module_id = diagnostic.get("source_module_id")
        document = next(
            (
                item for item in self.controller.snapshot.documents
                if item.logical_name == logical_name
                or item.module_id == module_id
            ),
            None,
        )
        if document is None:
            self.toast.show_message(
                "The diagnostic's logical source is not present in this bundle.",
                "warning",
            )
            return
        self.controller.select_document(document.document_id)
        revision = self.controller.committed_revision
        position_index = None
        if revision is not None:
            try:
                position_index = revision.index_for(
                    document.document_id
                ).position_index
            except KeyError:
                position_index = None
        start, end = diagnostic_character_range(
            diagnostic,
            document.text,
            position_index,
        )
        start, end = qt_range(
            document.text,
            start,
            end,
            position_index,
        )
        QTimer.singleShot(
            0, lambda: self.source.go_to_position(start, end)
        )
        self.statusBar().showMessage(
            f"{diagnostic.get('code', 'Diagnostic')} — "
            f"{diagnostic.get('message', '')}",
            9000,
        )

    def _activate_mapping(self, mapping: dict[str, Any]) -> None:
        output_text = self.controller.snapshot.generated_c or ""
        if not output_text:
            return
        self._set_output_visible(True)
        position_index = self.controller.result_output_index
        if position_index is None:
            self.toast.show_message(
                "Generated-C position index is still preparing.",
                "info",
            )
            return
        start, end = mapping_character_range(
            mapping,
            output_text,
            position_index,
        )
        start, end = qt_range(
            output_text,
            start,
            end,
            position_index,
        )
        QTimer.singleShot(
            0, lambda: self.output.go_to_position(start, end)
        )
        detail = str(
            mapping.get("rule_plan_id") or mapping.get("origin_kind") or ""
        ).strip()
        # Serialized/adapted mapping labels may already carry the UI
        # prefix. Keep status announcements concise and non-duplicated.
        detail = re.sub(
            r"^Mappings?\s*[—-]\s*",
            "",
            detail,
            flags=re.IGNORECASE,
        )
        module = str(mapping.get("module_id") or "synthetic")
        suffix = f" · {detail}" if detail else ""
        self.statusBar().showMessage(
            f"Mapping — {module}{suffix}", 8000
        )

    def _editor_marker_activated(
        self, kind: str, marker_id: str, position: int
    ) -> None:
        del position
        snapshot = self.controller.snapshot
        if kind in {"diagnostic", "warning", "info"}:
            diagnostic = next(
                (
                    item for item in snapshot.diagnostics
                    if item.get("diagnostic_id") == marker_id
                ),
                None,
            )
            if diagnostic is not None:
                self.statusBar().showMessage(
                    f"{diagnostic.get('code', '')} — "
                    f"{diagnostic.get('message', '')}",
                    9000,
                )
        elif kind == "mapping":
            mapping = next(
                (
                    item for item in snapshot.mappings
                    if item.get("c_node_id") == marker_id
                ),
                None,
            )
            if mapping is not None:
                self._activate_mapping(mapping)


__all__ = ["QtDocumentActionsMixin"]
