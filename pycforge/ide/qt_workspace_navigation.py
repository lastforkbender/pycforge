"""Navigation support for Phase 15C Qt observer surfaces."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QWidget

from .qt_contract import qt_range


class QtWorkspaceNavigationSupportMixin:
    """Internal bounded navigation for search, outline, mappings, and history."""

    def _navigation_activate_location(
        self,
        document_id: str,
        start: int,
        end: int,
        *,
        qt_positions: bool,
    ) -> None:
        pending = bool(getattr(self, "_source_sync_pending", False))
        if not self._commit_pending_identity():
            return
        if pending:
            self.statusBar().showMessage(
                "Source observations were refreshed; choose the result again.",
                6000,
            )
            return
        document = next(
            (
                item
                for item in self.controller.snapshot.documents
                if item.document_id == document_id
            ),
            None,
        )
        if document is None:
            self.toast.show_message(
                "The selected source document is no longer open.",
                "warning",
            )
            return
        if not qt_positions:
            position_index = self._observer_position_index(document_id)
            start, end = qt_range(
                document.text,
                start,
                end,
                position_index,
            )
        if self.controller.snapshot.active_document_id != document_id:
            try:
                self.controller.select_document(document_id)
            except Exception as exc:
                self._show_error("Could not select the source module", exc)
                return
        QTimer.singleShot(
            0,
            lambda identifier=document_id, first=start, last=end:
            self._navigation_reveal_if_current(identifier, first, last),
        )

    def _navigation_reveal_if_current(
        self,
        document_id: str,
        start: int,
        end: int,
    ) -> None:
        if self.controller.snapshot.active_document_id != document_id:
            return
        editor = self._active_source_editor()
        editor.go_to_position(start, end)
        editor.setFocus()

    def _navigation_mapping_source_location(
        self,
        mapping: dict[str, Any],
    ):
        snapshot = self.controller.snapshot
        node_ids = mapping.get("source_node_ids", ())
        if isinstance(node_ids, str):
            node_ids = (node_ids,)
        elif isinstance(node_ids, (tuple, list)):
            node_ids = tuple(node_ids)
        else:
            node_ids = ()
        direct = mapping.get("source_node_id")
        if isinstance(direct, str):
            node_ids += (direct,)

        result = self._source_structure_result
        symbol = (
            next(
                (
                    item
                    for item in result.symbols
                    if item.node_id in node_ids
                ),
                None,
            )
            if (
                result is not None
                and result.workspace_key
                == self._observer_workspace_key(snapshot)
            )
            else None
        )
        if symbol is not None:
            document = next(
                (
                    item
                    for item in snapshot.documents
                    if item.document_id == symbol.document_id
                ),
                None,
            )
            return document, symbol

        module_id = mapping.get("module_id")
        logical_name = mapping.get("logical_source_name")
        document_id = mapping.get("source_document_id")
        document = next(
            (
                item
                for item in snapshot.documents
                if item.module_id == module_id
                or item.logical_name == logical_name
                or item.document_id == document_id
            ),
            None,
        )
        return document, None

    def _navigation_reveal_selected_mapping_source(self) -> None:
        item = self.mappings.tree.currentItem()
        mapping = item.data(0, Qt.UserRole) if item is not None else None
        if not isinstance(mapping, dict):
            return
        document, symbol = self._navigation_mapping_source_location(mapping)
        if document is None:
            self.toast.show_message(
                "This mapping has no source module in the open bundle.",
                "warning",
            )
            return
        if symbol is not None:
            self._navigation_activate_location(
                document.document_id,
                symbol.start,
                symbol.end,
                qt_positions=False,
            )
        else:
            self._navigation_activate_location(
                document.document_id,
                0,
                0,
                qt_positions=True,
            )
        self.statusBar().showMessage(
            f"Source mapping — {document.logical_name}",
            8000,
        )

    def _navigation_show_panel(
        self,
        widget: QWidget,
        focus_widget: QWidget,
        *,
        select_all: bool = False,
    ) -> None:
        self._set_details_visible(True)
        self.tabs.setCurrentWidget(widget)
        focus_widget.setFocus()
        if select_all:
            focus_widget.selectAll()
        QTimer.singleShot(0, self._balance_main_splitter)
        self.action_registry.refresh()

    def _navigation_activate_history(self, sequence: int) -> None:
        entry = next(
            (
                item
                for item in self.controller.snapshot.conversion_history
                if item.request_sequence == sequence
            ),
            None,
        )
        if entry is None:
            self.statusBar().showMessage(
                "The selected session entry is no longer available.",
                6000,
            )
            return
        message = (
            f"Request {entry.request_sequence} — "
            f"{entry.status.replace('-', ' ').title()} · "
            f"{entry.completed_stage_count}/{entry.total_stage_count} stages · "
            f"{entry.diagnostic_count} diagnostics"
        )
        self.statusBar().showMessage(message, 9000)


__all__ = ["QtWorkspaceNavigationSupportMixin"]
