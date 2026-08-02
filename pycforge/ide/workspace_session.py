"""Immutable, presentation-only document tab and split-pane state.

This module deliberately stores document identifiers only.  It cannot retain
source text, paths, conversion results, observer data, or other semantic
artifacts.  The controller remains the authority for the exact current set and
order of SourceBundle documents.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


MAX_EDITOR_PANES = 2
MAX_SESSION_DOCUMENTS = 64
MAX_DOCUMENT_ID_CHARS = 256


class SplitOrientation(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


def _document_ids(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("document IDs must be an iterable of complete IDs")
    records = tuple(values)
    if not records:
        raise ValueError("workspace session requires a document")
    if len(records) > MAX_SESSION_DOCUMENTS:
        raise ValueError(
            f"workspace session exceeds {MAX_SESSION_DOCUMENTS} documents"
        )
    for value in records:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > MAX_DOCUMENT_ID_CHARS
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("document IDs must be bounded printable text")
    if len(records) != len(set(records)):
        raise ValueError("workspace session document IDs must be unique")
    return records


def _orientation(value: SplitOrientation | str) -> SplitOrientation:
    try:
        return SplitOrientation(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("split orientation is invalid") from exc


@dataclass(frozen=True, slots=True)
class WorkspaceSession:
    """Exact tab order and at most two document-ID-only editor panes."""

    document_ids: tuple[str, ...]
    pane_document_ids: tuple[str, ...]
    active_pane: int = 0
    split_orientation: SplitOrientation = SplitOrientation.HORIZONTAL

    def __post_init__(self) -> None:
        documents = _document_ids(self.document_ids)
        if documents != self.document_ids:
            raise TypeError("document IDs must be a tuple")
        panes = self.pane_document_ids
        if not isinstance(panes, tuple) or not 1 <= len(panes) <= MAX_EDITOR_PANES:
            raise ValueError("workspace session must contain one or two panes")
        if any(document_id not in documents for document_id in panes):
            raise ValueError("every pane must show a current document")
        if (
            isinstance(self.active_pane, bool)
            or not isinstance(self.active_pane, int)
            or not 0 <= self.active_pane < len(panes)
        ):
            raise ValueError("active pane is outside the session")
        if not isinstance(self.split_orientation, SplitOrientation):
            raise TypeError("split orientation must be SplitOrientation")

    @property
    def active_document_id(self) -> str:
        return self.pane_document_ids[self.active_pane]

    @property
    def is_split(self) -> bool:
        return len(self.pane_document_ids) == MAX_EDITOR_PANES


def create_workspace_session(
    document_ids: Iterable[str],
    active_document_id: str | None = None,
) -> WorkspaceSession:
    """Create a one-pane session over the exact supplied tab order."""

    records = _document_ids(document_ids)
    active = records[0] if active_document_id is None else active_document_id
    if active not in records:
        raise ValueError("active document is not a current document")
    return WorkspaceSession(records, (active,))


def activate_document(
    session: WorkspaceSession,
    document_id: str,
    *,
    pane: int | None = None,
) -> WorkspaceSession:
    """Show a current document in one pane and make that pane active."""

    if not isinstance(session, WorkspaceSession):
        raise TypeError("session must be WorkspaceSession")
    if document_id not in session.document_ids:
        raise ValueError("cannot activate a document outside the current tabs")
    target = session.active_pane if pane is None else pane
    if (
        isinstance(target, bool)
        or not isinstance(target, int)
        or not 0 <= target < len(session.pane_document_ids)
    ):
        raise ValueError("target pane is outside the session")
    panes = list(session.pane_document_ids)
    panes[target] = document_id
    return replace(
        session,
        pane_document_ids=tuple(panes),
        active_pane=target,
    )


def activate_pane(
    session: WorkspaceSession,
    pane: int,
) -> WorkspaceSession:
    """Make an existing pane active without changing either pane document."""

    if not isinstance(session, WorkspaceSession):
        raise TypeError("session must be WorkspaceSession")
    if (
        isinstance(pane, bool)
        or not isinstance(pane, int)
        or not 0 <= pane < len(session.pane_document_ids)
    ):
        raise ValueError("target pane is outside the session")
    return replace(session, active_pane=pane)


def split_session(
    session: WorkspaceSession,
    orientation: SplitOrientation | str,
    *,
    document_id: str | None = None,
) -> WorkspaceSession:
    """Open or reorient the second pane, never creating a third pane."""

    if not isinstance(session, WorkspaceSession):
        raise TypeError("session must be WorkspaceSession")
    resolved = _orientation(orientation)
    target = session.active_document_id if document_id is None else document_id
    if target not in session.document_ids:
        raise ValueError("split document is not a current document")
    if session.is_split:
        panes = list(session.pane_document_ids)
        panes[session.active_pane] = target
        return replace(
            session,
            pane_document_ids=tuple(panes),
            split_orientation=resolved,
        )
    return WorkspaceSession(
        session.document_ids,
        (session.active_document_id, target),
        active_pane=1,
        split_orientation=resolved,
    )


def close_split(
    session: WorkspaceSession,
    *,
    keep_pane: int | None = None,
) -> WorkspaceSession:
    """Collapse to one pane, keeping the active pane unless specified."""

    if not isinstance(session, WorkspaceSession):
        raise TypeError("session must be WorkspaceSession")
    target = session.active_pane if keep_pane is None else keep_pane
    if (
        isinstance(target, bool)
        or not isinstance(target, int)
        or not 0 <= target < len(session.pane_document_ids)
    ):
        raise ValueError("pane to keep is outside the session")
    return WorkspaceSession(
        session.document_ids,
        (session.pane_document_ids[target],),
        active_pane=0,
        split_orientation=session.split_orientation,
    )


def reconcile_session(
    session: WorkspaceSession,
    current_document_ids: Iterable[str],
    *,
    active_document_id: str | None = None,
) -> WorkspaceSession:
    """Reconcile tabs and panes to the controller's exact current IDs.

    Existing pane choices survive when their document still exists.  A removed
    pane document is replaced by the requested active document.  The active
    pane always shows the controller-selected active document when one is
    supplied.
    """

    if not isinstance(session, WorkspaceSession):
        raise TypeError("session must be WorkspaceSession")
    current = _document_ids(current_document_ids)
    active = (
        session.active_document_id
        if active_document_id is None
        and session.active_document_id in current
        else current[0]
        if active_document_id is None
        else active_document_id
    )
    if active not in current:
        raise ValueError("active document is not a current document")
    panes = [
        document_id if document_id in current else active
        for document_id in session.pane_document_ids
    ]
    panes[session.active_pane] = active
    return WorkspaceSession(
        current,
        tuple(panes),
        active_pane=session.active_pane,
        split_orientation=session.split_orientation,
    )


__all__ = [
    "MAX_DOCUMENT_ID_CHARS",
    "MAX_EDITOR_PANES",
    "MAX_SESSION_DOCUMENTS",
    "SplitOrientation",
    "WorkspaceSession",
    "activate_document",
    "activate_pane",
    "close_split",
    "create_workspace_session",
    "reconcile_session",
    "split_session",
]
