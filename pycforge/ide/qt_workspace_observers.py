"""Source-structure observer support for the optional Qt workspace.

The observer receives only immutable strings already present in the explicit
SourceBundle.  Its results are presentation data: they cannot affect source
eligibility, conversion, generated C, or save authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from .qt_contract import qt_position_to_python_offset, qt_range
from .source_structure import (
    SourceStructureDocument,
    SourceStructureResult,
    breadcrumbs_for_position,
)


@dataclass(frozen=True, slots=True)
class _BreadcrumbLocation:
    """Shape consumed by ``BreadcrumbBar`` without retaining source text."""

    name: str
    line: int
    column: int
    kind: str


class QtWorkspaceObserverSupportMixin:
    """Internal structure submission, stale rejection, and breadcrumbs."""

    def _observer_invalidate(self) -> None:
        if getattr(self, "_workspace_features_closed", False):
            return
        self._breadcrumb_timer.stop()
        self._source_structure_service.cancel()
        self._expected_structure_generation = None
        self._expected_structure_key = None
        self._submitted_structure_key = None
        self._source_structure_result = None
        if hasattr(self, "outline"):
            self.outline.set_result(None)
        if hasattr(self, "breadcrumbs"):
            active = self.controller.snapshot.active_document
            self.breadcrumbs.set_locations(active.logical_name, ())

    def _observer_submit(self, snapshot) -> None:
        identity = (
            snapshot.revision_generation,
            snapshot.bundle_fingerprint,
        )
        if identity == self._submitted_structure_key:
            return
        key = snapshot.bundle_fingerprint
        self._submitted_structure_key = identity
        self._expected_structure_key = key
        self._source_structure_result = None
        self.outline.set_result(None)
        documents = tuple(
            SourceStructureDocument(
                item.document_id,
                item.module_id,
                item.logical_name,
                item.text,
            )
            for item in snapshot.documents
        )
        self._expected_structure_generation = (
            self._source_structure_service.submit(
                documents,
                workspace_key=key,
                callback=self.structure_ready.emit,
            )
        )

    def _observer_accept(self, result: object) -> None:
        if (
            self._workspace_features_closed
            or not isinstance(result, SourceStructureResult)
            or result.generation != self._expected_structure_generation
            or result.workspace_key != self._expected_structure_key
            or result.workspace_key
            != self.controller.snapshot.bundle_fingerprint
        ):
            return
        self._source_structure_result = result
        self.outline.set_result(result)
        self._observer_update_breadcrumbs()

    @staticmethod
    def _observer_workspace_key(snapshot) -> str:
        """Return the controller-authenticated workspace identity."""

        return snapshot.bundle_fingerprint

    def _observer_update_breadcrumbs(self) -> None:
        snapshot = self.controller.snapshot
        active = snapshot.active_document
        result = self._source_structure_result
        if (
            result is None
            or result.workspace_key != self._observer_workspace_key(snapshot)
        ):
            self.breadcrumbs.set_locations(active.logical_name, ())
            return
        if not any(
            symbol.document_id == active.document_id
            for symbol in result.symbols
        ):
            self.breadcrumbs.set_locations(active.logical_name, ())
            return
        position_index = self._observer_position_index(
            active.document_id
        )
        if position_index is None:
            self.breadcrumbs.set_locations(active.logical_name, ())
            return
        position = qt_position_to_python_offset(
            active.text,
            self._active_source_editor().textCursor().position(),
            position_index,
        )
        chain = breadcrumbs_for_position(
            result,
            active.document_id,
            position,
        )
        locations = tuple(
            _BreadcrumbLocation(
                symbol.name,
                symbol.start_line,
                symbol.start_column,
                symbol.kind,
            )
            for symbol in chain
            if symbol.kind != "Module"
        )
        self.breadcrumbs.set_locations(active.logical_name, locations)

    def _observer_navigate_breadcrumb(
        self,
        line: int,
        column: int,
    ) -> None:
        active = self.controller.snapshot.active_document
        position_index = self._observer_position_index(
            active.document_id
        )
        editor = self._active_source_editor()
        if position_index is None:
            editor.go_to_line_number(line)
            return
        offset = position_index.character_offset(line, column)
        position, _ = qt_range(
            active.text,
            offset,
            offset,
            position_index,
        )
        editor.go_to_position(position, position)
        editor.setFocus()

    def _observer_position_index(self, document_id: str):
        revision = self.controller.committed_revision
        if revision is None:
            return None
        try:
            return revision.index_for(document_id).position_index
        except KeyError:
            return None

__all__ = ["QtWorkspaceObserverSupportMixin"]
