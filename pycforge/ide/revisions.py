from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from threading import Condition, RLock, Thread, current_thread
from time import monotonic
from typing import Callable, Sequence

from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
from pycforge.converter.core.canonicalization import canonicalize
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.fingerprint import Fingerprint, fingerprint
from pycforge.converter.core.request import (
    ConversionRequest,
    SourceBundle,
    SourceDocumentInput,
)

from .model import WorkspaceDocument
from .positions import TextPositionIndex, build_text_position_index


RevisionListener = Callable[["WorkspaceRevision"], None]
RevisionErrorListener = Callable[[int, BaseException], None]


class RevisionBuildError(ValueError):
    """Raised when an immutable workspace revision cannot be canonicalized."""

    def __init__(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        detail = "; ".join(
            f"{diagnostic.code}: {diagnostic.message}" for diagnostic in diagnostics
        )
        super().__init__(detail or "workspace revision could not be canonicalized")


@dataclass(frozen=True, slots=True)
class DocumentIndex:
    """Cached source-position facts for one immutable document text.

    ``line_starts`` contains Python string offsets. ``utf16_line_starts``
    contains offsets in UTF-16 code units, matching Qt cursor positions.
    Both tuples include the first line and add a new entry after every LF.
    """

    document_id: str
    module_id: str
    logical_name: str
    text_fingerprint: str
    source_fingerprint: str
    utf8_sha256: str
    utf8_size: int
    line_starts: tuple[int, ...]
    utf16_line_starts: tuple[int, ...]
    utf16_compatible: bool
    position_index: TextPositionIndex

    @property
    def line_count(self) -> int:
        return len(self.line_starts)


@dataclass(frozen=True, slots=True)
class WorkspaceRevision:
    """Fully authenticated, immutable source state ready for conversion."""

    generation: int
    active_document_id: str
    source_fingerprint: str
    bundle_fingerprint: str
    source_bundle: SourceBundle
    request: ConversionRequest
    request_fingerprint: Fingerprint
    resource_fingerprint: Fingerprint
    document_indexes: tuple[DocumentIndex, ...]
    total_utf8_size: int

    @property
    def active_index(self) -> DocumentIndex:
        for index in self.document_indexes:
            if index.document_id == self.active_document_id:
                return index
        raise LookupError("active document index is missing")

    @property
    def line_starts(self) -> tuple[int, ...]:
        """Cached Python offsets for the active document's line starts."""

        return self.active_index.line_starts

    @property
    def utf16_line_starts(self) -> tuple[int, ...]:
        """Cached Qt-compatible offsets for the active document's lines."""

        return self.active_index.utf16_line_starts

    @property
    def source_utf8_size(self) -> int:
        return self.active_index.utf8_size

    def index_for(self, document_id: str) -> DocumentIndex:
        for index in self.document_indexes:
            if index.document_id == document_id:
                return index
        raise KeyError(document_id)


@dataclass(frozen=True, slots=True)
class RevisionInput:
    """A cheap immutable capture; expensive facts are added by the service."""

    generation: int
    documents: tuple[WorkspaceDocument, ...]
    active_document_id: str


def source_fingerprint(text: str) -> str:
    """Return the exact workspace-source identity used by the controller."""

    return fingerprint("workspace-source", text).value


def conversion_order(
    documents: Sequence[WorkspaceDocument],
) -> tuple[WorkspaceDocument, ...]:
    primary = tuple(document for document in documents if document.is_primary)
    if len(primary) != 1:
        raise ValueError("workspace must contain exactly one primary document")
    return primary + tuple(document for document in documents if not document.is_primary)


def source_bundle_for(
    documents: Sequence[WorkspaceDocument],
) -> SourceBundle:
    ordered = conversion_order(documents)

    def source(document: WorkspaceDocument) -> SourceDocumentInput:
        return SourceDocumentInput(
            logical_name=document.logical_name,
            text=document.text,
            module_id=document.module_id,
        )

    return SourceBundle(
        primary=source(ordered[0]),
        companions=tuple(source(document) for document in ordered[1:]),
    )


def workspace_bundle_fingerprint(
    documents: Sequence[WorkspaceDocument],
) -> str:
    """Return the exact semantic bundle identity used by WorkspaceController."""

    ordered = conversion_order(documents)
    semantic = [
        {
            "module_id": document.module_id,
            "logical_name": document.logical_name,
            "text": document.text,
            "is_primary": index == 0,
        }
        for index, document in enumerate(ordered)
    ]
    return fingerprint("workspace-source-bundle", semantic).value


def _document_index(document: WorkspaceDocument) -> DocumentIndex:
    text = document.text
    encoded = text.encode("utf-8")
    positions = build_text_position_index(text)
    return DocumentIndex(
        document_id=document.document_id,
        module_id=document.module_id,
        logical_name=document.logical_name,
        text_fingerprint=fingerprint("workspace-document-text", text).value,
        source_fingerprint=source_fingerprint(text),
        utf8_sha256=sha256(encoded).hexdigest(),
        utf8_size=len(encoded),
        line_starts=positions.line_starts,
        utf16_line_starts=positions.utf16_line_starts,
        utf16_compatible=positions.utf16_compatible,
        position_index=positions,
    )


def build_workspace_revision(revision_input: RevisionInput) -> WorkspaceRevision:
    """Build all proportional revision facts on a non-GUI worker thread."""

    generation = revision_input.generation
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ValueError("revision generation must be a non-negative integer")
    documents = revision_input.documents
    if not documents:
        raise ValueError("workspace revision must contain at least one document")
    if any(not isinstance(document, WorkspaceDocument) for document in documents):
        raise TypeError("workspace revision documents must be WorkspaceDocument values")
    document_ids = tuple(document.document_id for document in documents)
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("workspace revision document IDs must be unique")
    if revision_input.active_document_id not in document_ids:
        raise ValueError("active document must belong to the workspace revision")

    active = next(
        document
        for document in documents
        if document.document_id == revision_input.active_document_id
    )
    bundle = source_bundle_for(documents)
    request = ConversionRequest(
        bundle,
        rule_set_version=DEFAULT_RULE_SET,
        renderer_version=DEFAULT_RENDERER,
    )
    canonical, diagnostics = canonicalize(request)
    if canonical is None:
        raise RevisionBuildError(diagnostics)

    indexes = tuple(_document_index(document) for document in documents)
    return WorkspaceRevision(
        generation=generation,
        active_document_id=revision_input.active_document_id,
        source_fingerprint=source_fingerprint(active.text),
        bundle_fingerprint=workspace_bundle_fingerprint(documents),
        source_bundle=canonical.request.source_bundle,
        request=canonical.request,
        request_fingerprint=canonical.request_fingerprint,
        resource_fingerprint=canonical.resource_fingerprint,
        document_indexes=indexes,
        total_utf8_size=sum(index.utf8_size for index in indexes),
    )


@dataclass(slots=True)
class _RevisionJob:
    submission: int
    revision_input: RevisionInput
    future: Future[WorkspaceRevision]


class WorkspaceRevisionService:
    """One-active, one-latest-pending immutable revision builder.

    The service deliberately owns one dedicated thread. Submissions only
    capture the already-immutable document tuple; source-proportional work is
    performed by the service thread. A newer submission replaces the pending
    job and retires an active job's publication authority.
    """

    def __init__(
        self,
        on_revision: RevisionListener | None = None,
        *,
        on_error: RevisionErrorListener | None = None,
        builder: Callable[[RevisionInput], WorkspaceRevision] = build_workspace_revision,
        thread_name: str = "pycforge-revision-index",
    ) -> None:
        self._on_revision = on_revision
        self._on_error = on_error
        self._builder = builder
        self._condition = Condition(RLock())
        self._active: _RevisionJob | None = None
        self._pending: _RevisionJob | None = None
        self._latest_submission = 0
        self._closed = False
        self._thread = Thread(
            target=self._run,
            name=thread_name,
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        generation: int,
        documents: Sequence[WorkspaceDocument],
        active_document_id: str,
    ) -> Future[WorkspaceRevision]:
        """Capture a revision request without traversing any document text."""

        revision_input = RevisionInput(
            generation=generation,
            documents=tuple(documents),
            active_document_id=active_document_id,
        )
        future: Future[WorkspaceRevision] = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError("workspace revision service is closed")
            self._latest_submission += 1
            job = _RevisionJob(self._latest_submission, revision_input, future)
            replaced = self._pending
            self._pending = job
            if replaced is not None:
                replaced.future.cancel()
            self._condition.notify()
        return future

    @property
    def active_generation(self) -> int | None:
        with self._condition:
            return (
                None
                if self._active is None
                else self._active.revision_input.generation
            )

    @property
    def pending_generation(self) -> int | None:
        with self._condition:
            return (
                None
                if self._pending is None
                else self._pending.revision_input.generation
            )

    @property
    def is_closed(self) -> bool:
        with self._condition:
            return self._closed

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait until neither an active nor pending computation remains."""

        deadline = None if timeout is None else monotonic() + timeout
        with self._condition:
            while self._active is not None or self._pending is not None:
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def close(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Retire publication immediately and optionally join the worker."""

        with self._condition:
            if not self._closed:
                self._closed = True
                pending = self._pending
                self._pending = None
                if pending is not None:
                    pending.future.cancel()
                self._condition.notify_all()
        if wait and current_thread() is not self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._pending is None and self._closed:
                    self._condition.notify_all()
                    return
                job = self._pending
                self._pending = None
                self._active = job
                self._condition.notify_all()

            if not job.future.set_running_or_notify_cancel():
                with self._condition:
                    if self._active is job:
                        self._active = None
                    self._condition.notify_all()
                continue

            revision: WorkspaceRevision | None = None
            failure: BaseException | None = None
            try:
                revision = self._builder(job.revision_input)
            except BaseException as exc:
                failure = exc

            with self._condition:
                if self._active is job:
                    self._active = None
                publishable = (
                    not self._closed
                    and job.submission == self._latest_submission
                    and self._pending is None
                )
                self._condition.notify_all()
            if failure is None:
                assert revision is not None
                if publishable and self._on_revision is not None:
                    try:
                        self._on_revision(revision)
                    except Exception:
                        pass
                job.future.set_result(revision)
            else:
                if publishable and self._on_error is not None:
                    try:
                        self._on_error(job.revision_input.generation, failure)
                    except Exception:
                        pass
                job.future.set_exception(failure)
