"""Action-state projection and signal wiring for the optional Qt shell."""

from __future__ import annotations

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtWidgets import QApplication, QLineEdit

from .action_contract import ActionState


class QtShellInteractionMixin:
    """Keep action targeting and widget wiring separate from shell layout."""

    def _resolved_action_target(self, target=None):
        registry = getattr(self, "action_registry", None)
        return target or getattr(registry, "active_target", None) or (
            QApplication.focusWidget()
        )

    def _invoke_target_method(self, method_name: str) -> None:
        target = self._resolved_action_target()
        method = getattr(target, method_name, None)
        if callable(method):
            method()
        self.action_registry.refresh()

    def _copy_action_selection(self) -> None:
        target = self._resolved_action_target()
        method = getattr(target, "copy", None)
        if callable(method):
            method()
            return
        current = getattr(target, "currentItem", lambda: None)()
        if current is None:
            return
        columns = getattr(target, "columnCount", lambda: 1)()
        text = "\t".join(
            current.text(column) for column in range(max(1, columns))
        ).strip()
        if text:
            QApplication.clipboard().setText(text)

    def _make_selected_primary(self) -> None:
        document_id = self.navigator.current_document_id
        if document_id is not None:
            self._set_primary_document(document_id)

    def _reveal_selected_diagnostic(self) -> None:
        item = self.diags.tree.currentItem()
        if item is not None:
            self._activate_diagnostic(item.data(0, Qt.UserRole))

    def _reveal_selected_mapping(self) -> None:
        item = self.mappings.tree.currentItem()
        if item is not None:
            self._activate_mapping(item.data(0, Qt.UserRole))

    def _action_states(self, _surface_id, target):
        snapshot = self.controller.snapshot
        target = self._resolved_action_target(target)
        source_target = target in (self.source, self.source_secondary)
        current_row = self.navigator.documents.currentRow()
        document_count = self.navigator.documents.count()
        has_selection = self._target_has_selection(target)
        writable = self._target_is_writable(target)
        can_undo = self._target_history_available(
            target, "isUndoAvailable"
        )
        can_redo = self._target_history_available(
            target, "isRedoAvailable"
        )
        clipboard = QApplication.clipboard()
        mime_data = (
            clipboard.mimeData()
            if clipboard is not None
            else None
        )
        can_paste = (
            writable
            and callable(getattr(target, "paste", None))
            and mime_data is not None
            and mime_data.hasText()
        )
        source_action = ActionState(source_target and writable)
        states = {
            "conversion.convert": ActionState(snapshot.can_convert),
            "conversion.cancel": ActionState(snapshot.can_cancel),
            "file.save_python": ActionState(snapshot.can_save_python),
            "file.save_python_as": ActionState(snapshot.can_save_python),
            "output.save_c": ActionState(
                snapshot.can_save_c
                and not self._source_sync_pending
                and not self.navigator.identity_pending
            ),
            "output.set_destination": ActionState(bool(snapshot.documents)),
            "bundle.new_module": ActionState(snapshot.can_add_document),
            "bundle.remove_module": ActionState(snapshot.can_remove_document),
            "bundle.move_up": ActionState(current_row > 0),
            "bundle.move_down": ActionState(
                0 <= current_row < document_count - 1
            ),
            "bundle.make_primary": ActionState(
                self.navigator.current_document_id is not None
                and self.navigator.primary_check.isEnabled()
            ),
            "edit.undo": ActionState(writable and can_undo),
            "edit.redo": ActionState(writable and can_redo),
            "edit.cut": ActionState(writable and has_selection),
            "edit.copy": ActionState(has_selection),
            "edit.paste": ActionState(can_paste),
            "edit.select_all": ActionState(
                callable(getattr(target, "selectAll", None))
            ),
            "edit.duplicate_line": source_action,
            "edit.move_line_up": source_action,
            "edit.move_line_down": source_action,
            "edit.indent": source_action,
            "edit.outdent": source_action,
            "edit.toggle_comment": source_action,
            "search.find": ActionState(True),
            "search.replace": ActionState(True),
            "search.bundle": ActionState(bool(snapshot.documents)),
            "search.next_match": ActionState(
                self.find_bar.next_button.isEnabled()
            ),
            "search.previous_match": ActionState(
                self.find_bar.previous_button.isEnabled()
            ),
            "search.replace_current": ActionState(
                self.find_bar.replace_button.isEnabled()
            ),
            "search.replace_all": ActionState(
                self.find_bar.replace_all_button.isEnabled()
            ),
            "search.close": ActionState(self.find_bar.isVisible()),
            "view.source_bundle": ActionState(
                checked=self.navigator.isVisible()
            ),
            "view.generated_c": ActionState(
                checked=self.output_panel.isVisible()
            ),
            "view.conversion_details": ActionState(
                checked=self.tabs.isVisible()
            ),
            "view.outline": ActionState(bool(snapshot.documents)),
            "view.conversion_history": ActionState(True),
            "view.whitespace": ActionState(
                checked=self.source.whitespace_visible
            ),
            "view.split_source": ActionState(
                checked=self.source_secondary.isVisible()
            ),
            "editor.toggle_fold": ActionState(source_target),
            "navigation.go_to_line": ActionState(bool(snapshot.documents)),
            "workspace.command_palette": ActionState(
                not getattr(self, "_command_palette_open", False)
            ),
            "tree.expand_all": ActionState(
                callable(getattr(target, "expandAll", None))
            ),
            "tree.collapse_all": ActionState(
                callable(getattr(target, "collapseAll", None))
            ),
            "diagnostics.reveal_source": ActionState(
                self.diags.tree.currentItem() is not None
            ),
            "mappings.reveal_output": ActionState(
                self.mappings.tree.currentItem() is not None
                and bool(snapshot.generated_c)
            ),
            "mappings.reveal_source": ActionState(
                self.mappings.tree.currentItem() is not None
            ),
        }
        return states

    @staticmethod
    def _target_has_selection(target) -> bool:
        if target is None:
            return False
        cursor_getter = getattr(target, "textCursor", None)
        if callable(cursor_getter):
            return bool(cursor_getter().hasSelection())
        selected_text = getattr(target, "hasSelectedText", None)
        if callable(selected_text):
            return bool(selected_text())
        selected_items = getattr(target, "selectedItems", None)
        return bool(selected_items()) if callable(selected_items) else False

    def _target_is_writable(self, target) -> bool:
        if target is None or target is self.output:
            return False
        if not all(
            callable(getattr(target, method_name, None))
            for method_name in ("cut", "paste")
        ):
            return False
        read_only = getattr(target, "isReadOnly", None)
        return not (callable(read_only) and read_only())

    @staticmethod
    def _target_history_available(target, method_name: str) -> bool:
        if target is None:
            return False
        method = getattr(target, method_name, None)
        if callable(method):
            return bool(method())
        document = getattr(target, "document", None)
        if callable(document):
            method = getattr(document(), method_name, None)
            return bool(method()) if callable(method) else False
        return False

    def _refresh_action_projection(self, *_args) -> None:
        self.action_registry.refresh()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if (
            event.type() == QEvent.KeyPress
            and self.action_registry.is_disabled_window_shortcut(
                event.key(),
                event.modifiers(),
            )
        ):
            return True
        if event.type() == QEvent.FocusIn and watched in (
            self.source,
            self.source_secondary,
            self.output,
        ):
            self.find_bar.attach_editor(watched)
        return super().eventFilter(watched, event)

    def _wire_workspace(self) -> None:
        for line_edit in self.findChildren(QLineEdit):
            line_edit.installEventFilter(self)
        for editor in (self.source, self.source_secondary):
            editor.textChanged.connect(self._source_changed)
            editor.installEventFilter(self)
            editor.markerActivated.connect(self._editor_marker_activated)
            editor.findRequested.connect(self._open_find)
            editor.cursorPositionChanged.connect(self._update_breadcrumbs)
        self.output.installEventFilter(self)
        self.output.markerActivated.connect(self._editor_marker_activated)
        self.output.findRequested.connect(self._open_find)
        self.navigator.document_selected.connect(self._select_document)
        self.navigator.add_requested.connect(self.add_document)
        self.navigator.remove_requested.connect(self._remove_document)
        self.navigator.move_up_requested.connect(self._move_document_up)
        self.navigator.move_down_requested.connect(self._move_document_down)
        self.navigator.identity_changed.connect(
            self._change_document_identity
        )
        self.navigator.identity_pending_changed.connect(
            self._present_pending_identity_edit
        )
        self.navigator.primary_requested.connect(
            self._set_primary_document
        )
        self.document_tabs.document_selected.connect(self._select_document)
        self.document_tabs.close_requested.connect(self._remove_document)
        self.document_tabs.order_requested.connect(
            self._reorder_document_tabs
        )
        self.breadcrumbs.location_requested.connect(
            self._navigate_breadcrumb
        )
        self.diags.diagnostic_activated.connect(self._activate_diagnostic)
        self.mappings.mapping_activated.connect(self._activate_mapping)
        self.outline.symbolActivated.connect(self._activate_outline_symbol)
        self.bundle_search.matchActivated.connect(
            self._activate_bundle_search_match
        )
        self.session_history.historyActivated.connect(
            self._activate_history_entry
        )
        self.find_bar.attach_editor(self.source)
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._refresh_action_projection)
            app.clipboard().dataChanged.connect(
                self._refresh_action_projection
            )
        for editor in (self.source, self.source_secondary, self.output):
            for signal in (
                editor.copyAvailable,
                editor.undoAvailable,
                editor.redoAvailable,
            ):
                signal.connect(self._refresh_action_projection)
        selection_views = (
            self.navigator.documents,
            self.diags.tree,
            self.mappings.tree,
            self.summary.tree,
            self.trace.tree,
            self.telemetry.tree,
            self.outline.tree,
            self.bundle_search.tree,
            self.session_history.tree,
        )
        for view in selection_views:
            view.itemSelectionChanged.connect(
                self._refresh_action_projection
            )
        source_actions = (
            "edit.duplicate_line",
            "edit.move_line_up",
            "edit.move_line_down",
            "edit.indent",
            "edit.outdent",
            "edit.toggle_comment",
            "editor.toggle_fold",
        )
        for action_id in source_actions:
            for editor in (self.source, self.source_secondary):
                self.action_registry.attach_to_widget(action_id, editor)


__all__ = ["QtShellInteractionMixin"]
