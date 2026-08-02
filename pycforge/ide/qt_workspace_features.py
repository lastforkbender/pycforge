"""Phase 15C workspace behavior for the PyQt5 application.

The public mixin owns presentation orchestration only.  The controller remains
the authority for the explicit SourceBundle and all transpilation artifacts.
"""

from __future__ import annotations

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QWidget

from .editor import large_file_mode_required
from .qt_command_palette import open_command_palette, open_go_to_line
from .qt_editor_buffers import SourceBufferStore
from .qt_workspace_navigation import (
    QtWorkspaceNavigationSupportMixin,
)
from .qt_workspace_observers import QtWorkspaceObserverSupportMixin
from .source_structure import SourceStructureResult
from .source_structure_async import AsyncSourceStructureService
from .workspace_session import (
    SplitOrientation,
    activate_document,
    activate_pane,
    close_split,
    create_workspace_session,
    reconcile_session,
    split_session,
)


class QtWorkspaceFeaturesMixin(
    QtWorkspaceObserverSupportMixin,
    QtWorkspaceNavigationSupportMixin,
):
    """Tabs, shared source buffers, editing, navigation, and observers."""

    def _initialize_workspace_features(self) -> None:
        """Create non-widget feature state before the shell is constructed."""

        if getattr(self, "_workspace_features_initialized", False):
            return
        snapshot = self.controller.snapshot
        document_ids = tuple(
            item.document_id for item in snapshot.documents
        )
        self.source_buffers = SourceBufferStore(self)
        self.workspace_session = create_workspace_session(
            document_ids,
            snapshot.active_document_id,
        )
        self._source_structure_service = AsyncSourceStructureService()
        self._expected_structure_generation: int | None = None
        self._expected_structure_key: str | None = None
        self._submitted_structure_key: tuple[int, str] | None = None
        self._source_structure_result: SourceStructureResult | None = None
        self._history_projection_key: int | None = None
        self._workspace_features_closed = False
        self._command_palette_open = False
        self._breadcrumb_timer = QTimer(self)
        self._breadcrumb_timer.setSingleShot(True)
        self._breadcrumb_timer.setInterval(60)
        self._breadcrumb_timer.timeout.connect(
            self._observer_update_breadcrumbs
        )
        self.structure_ready.connect(self._accept_source_structure)
        self._workspace_features_initialized = True

    def _project_workspace_features(
        self,
        snapshot,
        active_changed: bool = False,
    ) -> None:
        """Project one exact snapshot before the remaining workspace chrome."""

        if (
            not getattr(self, "_workspace_features_initialized", False)
            or self._workspace_features_closed
        ):
            return
        active = snapshot.active_document
        source_key = (active.document_id, id(active.text))
        pending_id = (
            self._source_sync_document_id
            if self._source_sync_pending
            else None
        )
        retained_editor_text = (
            pending_id is None
            and self._displayed_source_key == source_key
        )
        skip_id = pending_id or (
            active.document_id if retained_editor_text else None
        )
        applying = self._applying_source_text
        self._applying_source_text = True
        try:
            self.source_buffers.reconcile(
                snapshot.documents,
                skip_document_id=skip_id,
            )
            if retained_editor_text:
                self.source_buffers.mark_synchronized(
                    active.document_id,
                    id(active.text),
                    dirty=active.dirty,
                )
            self._bind_active_source_buffer(active)
        finally:
            self._applying_source_text = applying
        if pending_id is None:
            self._displayed_source_key = source_key

        document_ids = tuple(
            item.document_id for item in snapshot.documents
        )
        session = reconcile_session(
            self.workspace_session,
            document_ids,
            active_document_id=active.document_id,
        )
        active_pane = session.active_pane
        for pane in range(len(session.pane_document_ids)):
            session = activate_document(
                session,
                active.document_id,
                pane=pane,
            )
        self.workspace_session = activate_pane(session, active_pane)

        self.document_tabs.set_documents(
            snapshot.documents,
            snapshot.active_document_id,
        )
        history_key = id(snapshot.conversion_history)
        if history_key != self._history_projection_key:
            self._history_projection_key = history_key
            self.session_history.set_entries(snapshot.conversion_history)
        if pending_id is not None:
            self.bundle_search.invalidate_results()
            return
        self.bundle_search.set_documents(snapshot.documents)
        self._submit_source_structure(snapshot)
        if active_changed:
            self._update_breadcrumbs()

    def _close_workspace_features(self) -> None:
        """Stop observer work and release every payload-bearing Qt buffer."""

        if (
            not getattr(self, "_workspace_features_initialized", False)
            or self._workspace_features_closed
        ):
            return
        self._workspace_features_closed = True
        self._expected_structure_generation = None
        self._expected_structure_key = None
        self._submitted_structure_key = None
        self._source_structure_result = None
        self._breadcrumb_timer.stop()
        self._source_structure_service.cancel()
        self._source_structure_service.close(wait_seconds=0.05)
        self.find_bar.close_service()
        self.bundle_search.close_service()
        self.source_buffers.close()

    def _invalidate_source_observers(self) -> None:
        """Immediately clear observations for unsynchronized editor text."""

        if hasattr(self, "bundle_search"):
            self.bundle_search.invalidate_results()
        self._observer_invalidate()

    def _submit_source_structure(self, snapshot) -> None:
        """Submit exact open strings through the observer support boundary."""

        # The delegated, reviewable seam captures SourceStructureDocument(
        # values and submits them with
        # workspace_key=snapshot.bundle_fingerprint and
        # callback=self.structure_ready.emit.
        self._observer_submit(snapshot)

    def _accept_source_structure(self, result: object) -> None:
        """Accept only the generation authorized by observer support."""

        # Support validates result.generation and result.workspace_key against
        # self.controller.snapshot.bundle_fingerprint before publication.
        self._observer_accept(result)

    def _duplicate_source(self) -> bool:
        return self._run_source_command("duplicate_line_or_selection")

    def _move_source_up(self) -> bool:
        return self._run_source_command("move_source_lines_up")

    def _move_source_down(self) -> bool:
        return self._run_source_command("move_source_lines_down")

    def _indent_source(self) -> bool:
        return self._run_source_command("indent_source_lines")

    def _outdent_source(self) -> bool:
        return self._run_source_command("outdent_source_lines")

    def _toggle_source_comment(self) -> bool:
        return self._run_source_command("toggle_source_comment")

    def _show_bundle_search(self) -> None:
        self._navigation_show_panel(
            self.bundle_search,
            self.bundle_search.query_edit,
            select_all=True,
        )

    def _show_outline(self) -> None:
        self._navigation_show_panel(
            self.outline,
            self.outline.filter_edit,
        )

    def _show_conversion_history(self) -> None:
        self._navigation_show_panel(
            self.session_history,
            self.session_history.tree,
        )

    def _set_whitespace_visible(self, visible: bool) -> None:
        for editor in (self.source, self.source_secondary):
            editor.set_whitespace_visible(bool(visible))
        self.action_registry.refresh()

    def _set_source_split_visible(self, visible: bool) -> None:
        if bool(visible):
            self.workspace_session = split_session(
                self.workspace_session,
                self.workspace_session.split_orientation,
                document_id=self.controller.snapshot.active_document_id,
            )
            orientation = self.workspace_session.split_orientation
            self.source_splitter.setOrientation(
                Qt.Horizontal
                if orientation is SplitOrientation.HORIZONTAL
                else Qt.Vertical
            )
            self.source_secondary.setVisible(True)
            QTimer.singleShot(0, self._balance_source_splitter)
        else:
            secondary_had_focus = self.source_secondary.hasFocus()
            self.workspace_session = close_split(
                self.workspace_session,
                keep_pane=0,
            )
            self.source_secondary.setVisible(False)
            if secondary_had_focus:
                self.source.setFocus()
        if hasattr(self, "action_registry"):
            self.action_registry.refresh()

    def _toggle_source_fold(self) -> bool:
        target = self._active_source_editor()
        if target is self.source_secondary:
            retained = self.source.textCursor()
            self.source.setTextCursor(target.textCursor())
            try:
                changed = bool(self.source.toggle_fold_at_cursor())
            finally:
                self.source.setTextCursor(retained)
        else:
            changed = bool(self.source.toggle_fold_at_cursor())
        self.action_registry.refresh()
        return changed

    def _go_to_source_line(self) -> int | None:
        return open_go_to_line(self._active_source_editor(), self)

    def _open_command_palette(self) -> str | None:
        if self._command_palette_open:
            return None
        target = self._resolved_action_target()
        self._command_palette_open = True
        try:
            states = self._action_states(None, target)
            return open_command_palette(self, self.action_registry, states)
        finally:
            self._command_palette_open = False
            self.action_registry.refresh()

    def _reveal_selected_mapping_source(self) -> None:
        self._navigation_reveal_selected_mapping_source()

    def _reorder_document_tabs(self, order: object) -> None:
        if not self._commit_pending_identity():
            self._reset_document_tabs()
            return
        try:
            self.controller.reorder_documents(tuple(order))
        except Exception as exc:
            self._show_error("Could not reorder the source bundle", exc)
            self._reset_document_tabs()

    def _activate_bundle_search_match(
        self,
        document_id: str,
        qt_start: int,
        qt_end: int,
    ) -> None:
        self._navigation_activate_location(
            document_id,
            qt_start,
            qt_end,
            qt_positions=True,
        )

    def _activate_outline_symbol(
        self,
        document_id: str,
        start: int,
        end: int,
    ) -> None:
        self._navigation_activate_location(
            document_id,
            start,
            end,
            qt_positions=False,
        )

    def _update_breadcrumbs(self, *_args) -> None:
        self._breadcrumb_timer.start()

    def _navigate_breadcrumb(self, line: int, column: int) -> None:
        self._observer_navigate_breadcrumb(line, column)

    def _activate_history_entry(self, sequence: int) -> None:
        """Show one bounded terminal summary without replay authority."""

        self._navigation_activate_history(sequence)

    def _run_source_command(self, method_name: str) -> bool:
        method = getattr(self._active_source_editor(), method_name)
        changed = bool(method())
        self.action_registry.refresh()
        return changed

    def _active_source_editor(self):
        target = self._resolved_action_target()
        resolved = self._source_editor_from_target(target)
        if resolved is not None:
            return resolved
        if (
            self.source_secondary.isVisible()
            and self.source_secondary.hasFocus()
        ):
            return self.source_secondary
        return self.source

    def _source_editor_from_target(self, target):
        for editor in (self.source, self.source_secondary):
            if target is editor:
                return editor
            if isinstance(target, QWidget) and editor.isAncestorOf(target):
                return editor
        return None

    def _bind_active_source_buffer(self, active) -> None:
        document = self.source_buffers.document_for(active.document_id)
        large = large_file_mode_required(
            character_count=max(0, document.characterCount() - 1),
            line_count=document.blockCount(),
        )
        self.source.set_large_file_mode(large)
        self.source_secondary.set_large_file_mode(large)
        self.source.bind_text_document(document)
        self.source_secondary.bind_text_document(document)

    def _reset_document_tabs(self) -> None:
        snapshot = self.controller.snapshot
        self.document_tabs.set_documents(
            snapshot.documents,
            snapshot.active_document_id,
        )

    def _balance_source_splitter(self) -> None:
        extent = (
            self.source_splitter.width()
            if self.source_splitter.orientation() == Qt.Horizontal
            else self.source_splitter.height()
        )
        available = max(
            2,
            extent - self.source_splitter.handleWidth(),
        )
        first = available // 2
        self.source_splitter.setSizes(
            (first, available - first)
        )


__all__ = ["QtWorkspaceFeaturesMixin"]
