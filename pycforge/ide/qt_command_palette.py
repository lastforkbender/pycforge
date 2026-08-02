"""Optional Qt command-palette and go-to-line presentation adapters.

This module is imported only by the optional Qt workspace.  It creates no
actions and owns no action implementation: palette rows are inert projections
from the headless action contract, and activation resolves the selected stable
ID through the existing :class:`QtActionRegistry`.
"""

from __future__ import annotations

from collections.abc import Mapping

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .action_contract import ActionState
from .command_palette import (
    MAX_COMMAND_PALETTE_RESULTS,
    CommandPaletteProjection,
    project_command_palette,
)
from .qt_actions import QtActionRegistry


class CommandPaletteDialog(QDialog):
    """Keyboard-complete projection of the existing Qt action registry."""

    def __init__(
        self,
        owner: QWidget,
        registry: QtActionRegistry,
        states: Mapping[str, ActionState],
    ) -> None:
        if not isinstance(registry, QtActionRegistry):
            raise TypeError("registry must be QtActionRegistry")
        if not isinstance(states, Mapping):
            raise TypeError("palette states must be a mapping")
        super().__init__(owner)
        self._registry = registry
        self._states = dict(states)
        self._visible_action_ids: frozenset[str] = frozenset()
        self._invoked_action_id: str | None = None

        self.setObjectName("CommandPaletteDialog")
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.resize(720, 480)
        self.setAccessibleName("PyCForge command palette")
        self.setAccessibleDescription(
            "Filter and invoke declared PyCForge workspace actions."
        )

        heading = QLabel("COMMAND PALETTE")
        heading.setObjectName("PanelEyebrow")
        self.query_edit = QLineEdit()
        self.query_edit.setObjectName("CommandPaletteQuery")
        self.query_edit.setPlaceholderText("Type an action name or shortcut…")
        self.query_edit.setClearButtonEnabled(True)
        self.query_edit.setAccessibleName("Filter workspace actions")

        self.count_label = QLabel()
        self.count_label.setObjectName("MutedLabel")
        self.count_label.setAccessibleName("Command palette result count")
        heading_row = QHBoxLayout()
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(self.count_label)

        self.results = QTreeWidget()
        self.results.setObjectName("CommandPaletteResults")
        self.results.setColumnCount(2)
        self.results.setHeaderLabels(("Action", "Shortcut"))
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setAlternatingRowColors(False)
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.setAccessibleName("Matching workspace actions")
        self.results.setAccessibleDescription(
            "Use Up and Down to choose an enabled action and Enter to invoke it."
        )
        self.results.header().setStretchLastSection(False)
        self.results.header().resizeSection(0, 510)
        self.results.header().resizeSection(1, 130)

        self.empty_label = QLabel("No matching declared actions")
        self.empty_label.setObjectName("MutedLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setAccessibleName("No matching actions")
        self.empty_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        layout.addLayout(heading_row)
        layout.addWidget(self.query_edit)
        layout.addWidget(self.results, 1)
        layout.addWidget(self.empty_label)

        self.query_edit.textChanged.connect(self._refresh_projection)
        self.results.itemActivated.connect(self._activate_item)
        self.query_edit.installEventFilter(self)
        self.results.installEventFilter(self)
        self._refresh_projection("")
        self.query_edit.setFocus()

    @property
    def invoked_action_id(self) -> str | None:
        return self._invoked_action_id

    def projection(self) -> CommandPaletteProjection:
        """Return the current bounded headless projection."""

        return project_command_palette(
            self.query_edit.text(),
            states=self._states,
            limit=MAX_COMMAND_PALETTE_RESULTS,
        )

    def _refresh_projection(self, _query: str) -> None:
        projection = self.projection()
        self.results.clear()
        visible_ids: list[str] = []
        first_enabled: QTreeWidgetItem | None = None
        for palette_item in projection.items:
            action = self._registry.action(palette_item.action_id)
            rendered_shortcut = action.shortcut().toString(
                QKeySequence.NativeText
            )
            if not rendered_shortcut:
                rendered_shortcut = palette_item.shortcut or ""
            item = QTreeWidgetItem(
                (palette_item.label, rendered_shortcut)
            )
            item.setData(0, Qt.UserRole, palette_item.action_id)
            item.setIcon(0, action.icon())
            item.setToolTip(0, palette_item.tooltip)
            item.setData(
                0,
                Qt.AccessibleTextRole,
                (
                    palette_item.accessible_name
                    + (
                        f", shortcut {rendered_shortcut}"
                        if rendered_shortcut
                        else ""
                    )
                ),
            )
            enabled = palette_item.enabled and action.isEnabled()
            item.setDisabled(not enabled)
            self.results.addTopLevelItem(item)
            visible_ids.append(palette_item.action_id)
            if enabled and first_enabled is None:
                first_enabled = item

        self._visible_action_ids = frozenset(visible_ids)
        if first_enabled is not None:
            self.results.setCurrentItem(first_enabled)
        shown = len(projection.items)
        if projection.truncated:
            count = f"{shown} of {projection.total_count}"
        else:
            count = str(shown)
        self.count_label.setText(count)
        self.count_label.setAccessibleDescription(
            f"{shown} matching action" + ("" if shown == 1 else "s")
        )
        self.results.setVisible(bool(projection.items))
        self.empty_label.setVisible(not projection.items)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if (
            watched in (self.query_edit, self.results)
            and event.type() == QEvent.KeyPress
        ):
            key = event.key()
            if key == Qt.Key_Down:
                self._move_selection(1)
                event.accept()
                return True
            if key == Qt.Key_Up:
                self._move_selection(-1)
                event.accept()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._activate_item(self.results.currentItem(), 0)
                event.accept()
                return True
            if key == Qt.Key_Escape:
                self.reject()
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _enabled_items(self) -> tuple[QTreeWidgetItem, ...]:
        return tuple(
            item
            for row in range(self.results.topLevelItemCount())
            for item in (self.results.topLevelItem(row),)
            if not item.isDisabled()
            and isinstance(item.data(0, Qt.UserRole), str)
        )

    def _move_selection(self, step: int) -> None:
        choices = self._enabled_items()
        if not choices:
            return
        current = self.results.currentItem()
        try:
            index = choices.index(current)
        except ValueError:
            index = -1 if step > 0 else 0
        self.results.setCurrentItem(choices[(index + step) % len(choices)])
        self.results.scrollToItem(self.results.currentItem())

    def _activate_item(
        self,
        item: QTreeWidgetItem | None,
        _column: int,
    ) -> None:
        if item is None or item.isDisabled():
            return
        action_id = item.data(0, Qt.UserRole)
        if (
            not isinstance(action_id, str)
            or action_id not in self._visible_action_ids
        ):
            return
        action = self._registry.action(action_id)
        if not action.isEnabled():
            return
        self._invoked_action_id = action_id
        self.accept()
        action.trigger()


def open_command_palette(
    owner: QWidget,
    registry: QtActionRegistry,
    states: Mapping[str, ActionState],
) -> str | None:
    """Open the declared-action palette and return its invoked action ID."""

    dialog = CommandPaletteDialog(owner, registry, states)
    dialog.exec_()
    return dialog.invoked_action_id


def open_go_to_line(editor, owner: QWidget | None = None) -> int | None:
    """Prompt for and reveal a bounded document line without copying source."""

    document = editor.document()
    maximum = max(1, int(document.blockCount()))
    current = min(
        maximum,
        max(1, int(editor.textCursor().blockNumber()) + 1),
    )
    line, accepted = QInputDialog.getInt(
        owner or editor,
        "Go to Line",
        "Line:",
        current,
        1,
        maximum,
        1,
    )
    if not accepted:
        return None
    block = document.findBlockByNumber(line - 1)
    if not block.isValid():
        return None
    cursor = editor.textCursor()
    cursor.setPosition(block.position())
    editor.setTextCursor(cursor)
    editor.centerCursor()
    editor.setFocus()
    return line


__all__ = [
    "CommandPaletteDialog",
    "open_command_palette",
    "open_go_to_line",
]
