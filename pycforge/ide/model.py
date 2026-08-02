from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeAlias

from .session_history import ConversionHistoryEntry


MAX_WORKSPACE_DOCUMENTS = 64
PreferenceValue: TypeAlias = str | int | float | bool | None


class WorkspaceState(str, Enum):
    EMPTY = "empty"
    CONVERTING = "converting"
    CANCEL_REQUESTED = "cancel-requested"
    CONVERTED = "converted"
    WARNING = "warning"
    APPROXIMATION = "approximation"
    REJECTED = "rejected"
    CANCELED = "canceled"
    FAILED = "failed"
    STALE = "stale"
    OBSERVER_INCOMPLETE = "observer-incomplete"


PUBLISHABLE_STATES = frozenset(
    {
        WorkspaceState.CONVERTED,
        WorkspaceState.WARNING,
        WorkspaceState.APPROXIMATION,
        WorkspaceState.OBSERVER_INCOMPLETE,
    }
)


@dataclass(frozen=True, slots=True)
class WorkspaceDocument:
    """One immutable document in a bounded workspace bundle.

    ``path`` is deliberately a string rather than a :class:`~pathlib.Path` so
    snapshots remain composed of plain, persistence-friendly values.
    """

    document_id: str
    module_id: str
    logical_name: str
    text: str = ""
    path: str | None = None
    is_primary: bool = False
    dirty: bool = False


def initial_document() -> WorkspaceDocument:
    return WorkspaceDocument(
        document_id="doc-main",
        module_id="main",
        logical_name="main.py",
        is_primary=True,
    )


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    # Compatibility mirrors for the active document.  New code should prefer
    # ``active_document`` and ``bundle_fingerprint``.
    source_text: str = ""
    source_fingerprint: str = ""
    documents: tuple[WorkspaceDocument, ...] = field(
        default_factory=lambda: (initial_document(),)
    )
    active_document_id: str = "doc-main"
    bundle_fingerprint: str = ""
    linked_c_path: str | None = None
    linked_c_path_is_default: bool = True
    preferences: tuple[tuple[str, PreferenceValue], ...] = ()

    generated_c: str | None = None
    state: WorkspaceState = WorkspaceState.EMPTY
    diagnostics: tuple[dict[str, Any], ...] = ()
    summary: tuple[tuple[str, str], ...] = ()
    decision_trace: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
    conversion_summary: dict[str, Any] | None = None
    mappings: tuple[dict[str, Any], ...] = ()
    conversion_history: tuple[ConversionHistoryEntry, ...] = ()
    revision_generation: int = 0
    revision_authenticated: bool = True
    request_sequence: int = 0
    result_source_fingerprint: str | None = None
    result_bundle_fingerprint: str | None = None
    result_revision_generation: int | None = None
    result_state: WorkspaceState | None = None
    stale_reason: str | None = None
    worker_failure_reason: str | None = None
    active_stage: str | None = None
    completed_stages: int = 0
    total_stages: int = 0

    @property
    def active_document(self) -> WorkspaceDocument:
        for document in self.documents:
            if document.document_id == self.active_document_id:
                return document
        # Controller invariants make this unreachable.  Raising here is safer
        # than silently presenting a different document to a view.
        raise LookupError("active workspace document is missing")

    @property
    def primary_document(self) -> WorkspaceDocument:
        for document in self.documents:
            if document.is_primary:
                return document
        raise LookupError("primary workspace document is missing")

    @property
    def can_convert(self) -> bool:
        return bool(
            self.documents
            and self.revision_authenticated
            and self.bundle_fingerprint
            and self.state
            not in {WorkspaceState.CONVERTING, WorkspaceState.CANCEL_REQUESTED}
        )

    @property
    def can_cancel(self) -> bool:
        return self.state is WorkspaceState.CONVERTING

    @property
    def can_save_python(self) -> bool:
        return bool(self.documents)

    @property
    def can_save_c(self) -> bool:
        result_fingerprint = (
            self.result_bundle_fingerprint or self.result_source_fingerprint
        )
        return bool(
            self.generated_c is not None
            and self.state in PUBLISHABLE_STATES
            and result_fingerprint == self.bundle_fingerprint
            and self.result_revision_generation == self.revision_generation
        )

    @property
    def can_add_document(self) -> bool:
        return len(self.documents) < MAX_WORKSPACE_DOCUMENTS

    @property
    def can_remove_document(self) -> bool:
        return len(self.documents) > 1

    def preference_data(self) -> dict[str, PreferenceValue]:
        return dict(self.preferences)


@dataclass(slots=True)
class WorkspaceStore:
    snapshot: WorkspaceSnapshot = field(default_factory=WorkspaceSnapshot)

    def replace(self, snapshot: WorkspaceSnapshot) -> None:
        self.snapshot = snapshot
