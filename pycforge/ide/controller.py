from __future__ import annotations

import math
import re
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Callable, Mapping, Sequence

from pycforge.converter.core.stage_artifact import freeze_value
from pycforge.converter.io.atomic_writer import AtomicWriter

from .model import (
    MAX_WORKSPACE_DOCUMENTS,
    PreferenceValue,
    WorkspaceDocument,
    WorkspaceSnapshot,
    WorkspaceState,
    WorkspaceStore,
)
from .io_service import WorkspaceIOService
from .positions import TextPositionIndex, TextPositionIndexService
from .controller_conversion import ConversionControllerMixin
from .controller_io import AsyncIOControllerMixin
from .revisions import (
    RevisionBuildError,
    RevisionInput,
    WorkspaceRevision,
    WorkspaceRevisionService,
    build_workspace_revision,
    source_fingerprint,
    workspace_bundle_fingerprint,
)
from .supervisor import (
    ProcessConversionSupervisor,
)


SnapshotListener = Callable[[WorkspaceSnapshot], None]
_MODULE_SEGMENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_DOCUMENT_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")


class WorkspaceController(
    ConversionControllerMixin,
    AsyncIOControllerMixin,
):
    """Headless, race-safe controller for a bounded Phase 12 source bundle."""

    def __init__(
        self,
        *,
        supervisor: ProcessConversionSupervisor | None = None,
        io_service: WorkspaceIOService | None = None,
        writer: AtomicWriter | None = None,
    ) -> None:
        self._supervisor = supervisor or ProcessConversionSupervisor()
        self._owns_supervisor = supervisor is None
        self._io_service = io_service or WorkspaceIOService()
        self._owns_io_service = io_service is None
        self._writer = writer or AtomicWriter()
        self._store = WorkspaceStore()
        initial = self._store.snapshot
        initial_revision = build_workspace_revision(
            RevisionInput(
                generation=0,
                documents=initial.documents,
                active_document_id=initial.active_document_id,
            )
        )
        self._store.replace(
            replace(
                initial,
                source_fingerprint=initial_revision.source_fingerprint,
                bundle_fingerprint=initial_revision.bundle_fingerprint,
                revision_generation=initial_revision.generation,
                revision_authenticated=True,
            )
        )
        self._listeners: list[SnapshotListener] = []
        self._lock = RLock()
        self._request_sequence = 0
        self._revision_generation = 0
        self._document_sequence = 1
        self._current_revision = initial_revision
        self._result_output_index: (
            tuple[str, TextPositionIndex] | None
        ) = None
        self._output_index_generation = 0
        self._closed = False
        self._output_index_service = TextPositionIndexService(
            self._accept_output_index
        )
        self._revision_future: Future[WorkspaceRevision] | None = None
        self._revision_service = WorkspaceRevisionService(
            self._accept_revision,
            on_error=self._reject_revision,
        )

    @property
    def snapshot(self) -> WorkspaceSnapshot:
        return self._store.snapshot

    @property
    def committed_revision(self) -> WorkspaceRevision | None:
        with self._lock:
            if (
                not self.snapshot.revision_authenticated
                or self._current_revision.generation
                != self.snapshot.revision_generation
            ):
                return None
            return self._current_revision

    @property
    def result_output_index(self) -> TextPositionIndex | None:
        """Return cached positions for the exact retained generated-C string."""

        with self._lock:
            cached = self._result_output_index
            if (
                cached is None
                or cached[0] is not self.snapshot.generated_c
            ):
                return None
            return cached[1]

    def _accept_output_index(
        self,
        generation: int,
        text: str,
        index: TextPositionIndex,
    ) -> None:
        with self._lock:
            if (
                self._closed
                or generation != self._output_index_generation
                or text is not self.snapshot.generated_c
            ):
                return
            self._result_output_index = (text, index)
            # The immutable snapshot remains exact; republishing only tells
            # presentation observers that deferred position facts are ready.
            self._publish(self.snapshot)

    def subscribe(self, listener: SnapshotListener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: SnapshotListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _publish(self, snapshot: WorkspaceSnapshot) -> None:
        self._store.replace(snapshot)
        for listener in tuple(self._listeners):
            try:
                listener(snapshot)
            except Exception:
                # Views are observers and cannot compromise conversion custody.
                pass

    @staticmethod
    def source_fingerprint(text: str) -> str:
        return source_fingerprint(text)

    @classmethod
    def workspace_bundle_fingerprint(
        cls,
        documents: Sequence[WorkspaceDocument],
    ) -> str:
        return workspace_bundle_fingerprint(documents)

    @staticmethod
    def _validate_module_id(value: object) -> bool:
        if not isinstance(value, str) or not value:
            return False
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        parts = value.split(".")
        return bool(
            len(encoded) <= 255
            and 1 <= len(parts) <= 16
            and all(_MODULE_SEGMENT.fullmatch(part) for part in parts)
        )

    @staticmethod
    def _validate_logical_name(value: object) -> bool:
        if not isinstance(value, str) or not value:
            return False
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        path = PurePosixPath(value)
        return bool(
            path.parts
            and path.as_posix() == value
            and not value.startswith("/")
            and "\\" not in value
            and ".." not in path.parts
            and not any(ord(character) < 32 for character in value)
        )

    @classmethod
    def _validate_documents(cls, documents: Sequence[WorkspaceDocument]) -> None:
        if not 1 <= len(documents) <= MAX_WORKSPACE_DOCUMENTS:
            raise ValueError("workspace must contain between 1 and 64 documents")
        if sum(item.is_primary for item in documents) != 1:
            raise ValueError("workspace must contain exactly one primary document")

        document_ids: list[str] = []
        module_ids: list[str] = []
        logical_names: list[str] = []
        paths: list[str] = []
        for document in documents:
            if not isinstance(document, WorkspaceDocument):
                raise TypeError("workspace documents must be WorkspaceDocument values")
            if not _DOCUMENT_ID.fullmatch(document.document_id):
                raise ValueError("document ID is not a canonical workspace identifier")
            if not cls._validate_module_id(document.module_id):
                raise ValueError("module ID must be a canonical lowercase dotted identifier")
            if not cls._validate_logical_name(document.logical_name):
                raise ValueError("logical name must be a canonical relative logical path")
            if not isinstance(document.text, str):
                raise TypeError("document text must be a string")
            if document.path is not None:
                if not isinstance(document.path, str) or not document.path or "\0" in document.path:
                    raise ValueError("document path must be a non-empty path string")
                paths.append(document.path)
            document_ids.append(document.document_id)
            module_ids.append(document.module_id)
            logical_names.append(document.logical_name)

        if len(document_ids) != len(set(document_ids)):
            raise ValueError("workspace document IDs must be unique")
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("workspace module IDs must be unique")
        if len(logical_names) != len(set(logical_names)):
            raise ValueError("workspace logical names must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("workspace file paths must be unique")

    @staticmethod
    def _path_text(path: Path | str) -> str:
        value = str(Path(path))
        if not value or "\0" in value:
            raise ValueError("path must be non-empty")
        return value

    def _next_document_id(self) -> str:
        existing = {item.document_id for item in self.snapshot.documents}
        while True:
            self._document_sequence += 1
            candidate = f"doc-{self._document_sequence:04d}"
            if candidate not in existing:
                return candidate

    @staticmethod
    def _semantic_documents_changed(
        old: Sequence[WorkspaceDocument],
        new: Sequence[WorkspaceDocument],
    ) -> bool:
        if len(old) != len(new):
            return True
        return any(
            before.document_id != after.document_id
            or before.module_id != after.module_id
            or before.logical_name != after.logical_name
            or before.is_primary != after.is_primary
            or before.text is not after.text
            for before, after in zip(old, new)
        )

    def _mutate_documents(
        self,
        documents: Sequence[WorkspaceDocument],
        *,
        active_document_id: str,
        reason: str,
        linked_c_path: str | None | object = Ellipsis,
        linked_c_path_is_default: bool | object = Ellipsis,
    ) -> WorkspaceSnapshot:
        candidate = tuple(documents)
        self._validate_documents(candidate)
        if active_document_id not in {item.document_id for item in candidate}:
            raise ValueError("active document must belong to the workspace")

        old = self.snapshot
        active = next(item for item in candidate if item.document_id == active_document_id)
        semantic_changed = self._semantic_documents_changed(old.documents, candidate)
        if not semantic_changed:
            state = old.state
            stale_reason = old.stale_reason
        elif old.generated_c is not None:
            state = WorkspaceState.STALE
            stale_reason = reason
        else:
            # A semantic edit starts a new, not-yet-converted revision.  Prior
            # rejection or observer records must not remain authoritative for
            # the new text merely because no generated C exists yet.
            state = WorkspaceState.EMPTY
            stale_reason = None

        if semantic_changed:
            # A request is identified by both its source fingerprint and its
            # generation.  Advancing the generation on every semantic edit
            # prevents an A -> B -> A edit from making an obsolete result for
            # A look current again, even when a converter ignores cancellation.
            self._revision_generation += 1
            if old.state in {
                WorkspaceState.CONVERTING,
                WorkspaceState.CANCEL_REQUESTED,
            }:
                self._supervisor.cancel(old.request_sequence)

        if semantic_changed:
            current_source_fingerprint = ""
        else:
            try:
                current_source_fingerprint = self._current_revision.index_for(
                    active.document_id
                ).source_fingerprint
            except KeyError:
                current_source_fingerprint = old.source_fingerprint

        updated = replace(
            old,
            documents=candidate,
            active_document_id=active_document_id,
            source_text=active.text,
            source_fingerprint=current_source_fingerprint,
            bundle_fingerprint=("" if semantic_changed else old.bundle_fingerprint),
            revision_generation=self._revision_generation,
            revision_authenticated=(
                False if semantic_changed else old.revision_authenticated
            ),
            state=state,
            stale_reason=stale_reason,
            worker_failure_reason=None if semantic_changed else old.worker_failure_reason,
            diagnostics=() if semantic_changed else old.diagnostics,
            summary=() if semantic_changed else old.summary,
            decision_trace=None if semantic_changed else old.decision_trace,
            telemetry=None if semantic_changed else old.telemetry,
            conversion_summary=None if semantic_changed else old.conversion_summary,
            mappings=(
                old.mappings
                if not semantic_changed or old.generated_c is not None
                else ()
            ),
            active_stage=None if semantic_changed else old.active_stage,
            completed_stages=0 if semantic_changed else old.completed_stages,
            total_stages=0 if semantic_changed else old.total_stages,
            linked_c_path=(
                old.linked_c_path if linked_c_path is Ellipsis else linked_c_path
            ),
            linked_c_path_is_default=(
                old.linked_c_path_is_default
                if linked_c_path_is_default is Ellipsis
                else bool(linked_c_path_is_default)
            ),
        )
        self._publish(updated)
        if semantic_changed:
            self._revision_future = self._revision_service.submit(
                self._revision_generation,
                candidate,
                active_document_id,
            )
        return updated

    def _accept_revision(self, revision: WorkspaceRevision) -> None:
        with self._lock:
            current = self.snapshot
            if (
                self._closed
                or revision.generation != self._revision_generation
                or revision.generation != current.revision_generation
            ):
                return
            self._current_revision = revision
            try:
                active_source = revision.index_for(
                    current.active_document_id
                ).source_fingerprint
            except KeyError:
                return
            self._publish(
                replace(
                    current,
                    source_fingerprint=active_source,
                    bundle_fingerprint=revision.bundle_fingerprint,
                    revision_authenticated=True,
                    worker_failure_reason=None,
                )
            )

    def _reject_revision(self, generation: int, error: BaseException) -> None:
        with self._lock:
            current = self.snapshot
            if self._closed or generation != current.revision_generation:
                return
            diagnostics: tuple[dict, ...] = ()
            if isinstance(error, RevisionBuildError):
                diagnostics = tuple(
                    freeze_value(item.to_dict()) for item in error.diagnostics
                )
            self._publish(
                replace(
                    current,
                    revision_authenticated=False,
                    state=WorkspaceState.REJECTED,
                    diagnostics=diagnostics,
                    stale_reason=(
                        "revision-authentication-failed"
                        if current.generated_c is not None
                        else None
                    ),
                    worker_failure_reason="revision-authentication-failed",
                )
            )

    def _replace_document(
        self,
        document_id: str,
        replacement: WorkspaceDocument,
        *,
        reason: str,
        active_document_id: str | None = None,
        linked_c_path: str | None | object = Ellipsis,
        linked_c_path_is_default: bool | object = Ellipsis,
    ) -> WorkspaceSnapshot:
        documents = list(self.snapshot.documents)
        for index, document in enumerate(documents):
            if document.document_id == document_id:
                documents[index] = replacement
                break
        else:
            raise KeyError(f"unknown workspace document: {document_id}")
        return self._mutate_documents(
            documents,
            active_document_id=active_document_id or self.snapshot.active_document_id,
            reason=reason,
            linked_c_path=linked_c_path,
            linked_c_path_is_default=linked_c_path_is_default,
        )

    def set_source(self, text: str) -> None:
        """Compatibility alias: update the active document's source text."""

        with self._lock:
            active = self.snapshot.active_document
            self.update_document(active.document_id, text)

    def update_document(self, document_id: str, text: str) -> WorkspaceDocument:
        with self._lock:
            document = self._document(document_id)
            if not isinstance(text, str):
                raise TypeError("document text must be a string")
            if text == document.text:
                return document
            replacement = replace(document, text=text, dirty=True)
            self._replace_document(
                document_id,
                replacement,
                reason="source-changed",
            )
            return replacement

    def add_document(
        self,
        module_id: str,
        logical_name: str,
        text: str = "",
        *,
        path: Path | str | None = None,
        document_id: str | None = None,
        make_active: bool = True,
        is_primary: bool = False,
        dirty: bool | None = None,
    ) -> WorkspaceDocument:
        with self._lock:
            if len(self.snapshot.documents) >= MAX_WORKSPACE_DOCUMENTS:
                raise ValueError("workspace already contains the maximum 64 documents")
            identifier = document_id or self._next_document_id()
            path_text = None if path is None else self._path_text(path)
            document = WorkspaceDocument(
                document_id=identifier,
                module_id=module_id,
                logical_name=logical_name,
                text=text,
                path=path_text,
                is_primary=is_primary,
                dirty=bool(text) if dirty is None and path is None else bool(dirty),
            )
            documents = list(self.snapshot.documents)
            if is_primary:
                documents = [replace(item, is_primary=False) for item in documents]
            documents.append(document)
            linked: str | None | object = Ellipsis
            linked_default: bool | object = Ellipsis
            if is_primary and self.snapshot.linked_c_path_is_default:
                linked = self._default_c_path(document)
                linked_default = True
            self._mutate_documents(
                documents,
                active_document_id=(
                    document.document_id if make_active else self.snapshot.active_document_id
                ),
                reason="document-added",
                linked_c_path=linked,
                linked_c_path_is_default=linked_default,
            )
            return document

    def remove_document(self, document_id: str) -> WorkspaceDocument:
        with self._lock:
            if len(self.snapshot.documents) == 1:
                raise ValueError("the final workspace document cannot be removed")
            removed = self._document(document_id)
            old_documents = list(self.snapshot.documents)
            removed_index = old_documents.index(removed)
            documents = [item for item in old_documents if item.document_id != document_id]
            if removed.is_primary:
                documents[0] = replace(documents[0], is_primary=True)
            if self.snapshot.active_document_id == document_id:
                active_index = min(removed_index, len(documents) - 1)
                active_document_id = documents[active_index].document_id
            else:
                active_document_id = self.snapshot.active_document_id
            linked: str | None | object = Ellipsis
            linked_default: bool | object = Ellipsis
            if removed.is_primary and self.snapshot.linked_c_path_is_default:
                linked = self._default_c_path(documents[0])
                linked_default = True
            self._mutate_documents(
                documents,
                active_document_id=active_document_id,
                reason="document-removed",
                linked_c_path=linked,
                linked_c_path_is_default=linked_default,
            )
            return removed

    def select_document(self, document_id: str) -> WorkspaceDocument:
        with self._lock:
            selected = self._document(document_id)
            old = self.snapshot
            self._publish(
                replace(
                    old,
                    active_document_id=document_id,
                    source_text=selected.text,
                    source_fingerprint=(
                        self._current_revision.index_for(
                            selected.document_id
                        ).source_fingerprint
                        if old.revision_authenticated
                        else ""
                    ),
                )
            )
            return selected

    def reorder_documents(self, document_ids: Sequence[str]) -> None:
        with self._lock:
            identifiers = tuple(document_ids)
            current = {item.document_id: item for item in self.snapshot.documents}
            if len(identifiers) != len(current) or set(identifiers) != set(current):
                raise ValueError("document order must be an exact workspace permutation")
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("document order contains duplicate document IDs")
            self._mutate_documents(
                [current[item] for item in identifiers],
                active_document_id=self.snapshot.active_document_id,
                reason="documents-reordered",
            )

    def set_document_identity(
        self,
        document_id: str,
        *,
        module_id: str | None = None,
        logical_name: str | None = None,
        is_primary: bool | None = None,
    ) -> WorkspaceDocument:
        with self._lock:
            document = self._document(document_id)
            replacement = replace(
                document,
                module_id=document.module_id if module_id is None else module_id,
                logical_name=(
                    document.logical_name if logical_name is None else logical_name
                ),
                is_primary=document.is_primary if is_primary is None else is_primary,
            )
            documents = list(self.snapshot.documents)
            if is_primary is True:
                documents = [replace(item, is_primary=False) for item in documents]
            elif is_primary is False and document.is_primary:
                raise ValueError("select another primary document before clearing this one")
            for index, item in enumerate(documents):
                if item.document_id == document_id:
                    documents[index] = replacement
                    break
            linked: str | None | object = Ellipsis
            linked_default: bool | object = Ellipsis
            if is_primary is True and self.snapshot.linked_c_path_is_default:
                linked = self._default_c_path(replacement)
                linked_default = True
            self._mutate_documents(
                documents,
                active_document_id=self.snapshot.active_document_id,
                reason=(
                    "primary-document-changed"
                    if is_primary is not None and replacement.is_primary != document.is_primary
                    else "document-identity-changed"
                ),
                linked_c_path=linked,
                linked_c_path_is_default=linked_default,
            )
            return replacement

    def set_primary_document(self, document_id: str) -> WorkspaceDocument:
        return self.set_document_identity(document_id, is_primary=True)

    def _document(self, document_id: str) -> WorkspaceDocument:
        for document in self.snapshot.documents:
            if document.document_id == document_id:
                return document
        raise KeyError(f"unknown workspace document: {document_id}")

    @staticmethod
    def _module_id_for_path(path: Path) -> str:
        candidate = re.sub(r"[^a-z0-9_]+", "_", path.stem.lower()).strip("_")
        if not candidate or not candidate[0].isalpha():
            candidate = f"module_{candidate}" if candidate else "module"
        return candidate[:63]

    def open_document(
        self,
        path: Path | str,
        *,
        module_id: str | None = None,
        logical_name: str | None = None,
        document_id: str | None = None,
        make_active: bool = True,
        is_primary: bool = False,
    ) -> WorkspaceDocument:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
        return self._apply_opened_document(
            source_path,
            text,
            module_id=module_id,
            logical_name=logical_name,
            document_id=document_id,
            make_active=make_active,
            is_primary=is_primary,
        )

    def _apply_opened_document(
        self,
        source_path: Path,
        text: str,
        *,
        module_id: str | None,
        logical_name: str | None,
        document_id: str | None,
        make_active: bool,
        is_primary: bool,
    ) -> WorkspaceDocument:
        if document_id is None:
            # Opening the first file replaces the pristine untitled document;
            # subsequent opens extend the bundle.  This keeps the common
            # single-file path unsurprising without weakening explicit tabs.
            with self._lock:
                pristine = (
                    len(self.snapshot.documents) == 1
                    and not self.snapshot.active_document.text
                    and self.snapshot.active_document.path is None
                    and not self.snapshot.active_document.dirty
                )
                if pristine:
                    document_id = self.snapshot.active_document_id
                    module_id = module_id or self._module_id_for_path(source_path)
                    logical_name = logical_name or source_path.name
            if document_id is None:
                return self.add_document(
                    module_id or self._module_id_for_path(source_path),
                    logical_name or source_path.name,
                    text,
                    path=source_path,
                    make_active=make_active,
                    is_primary=is_primary,
                    dirty=False,
                )

        with self._lock:
            document = self._document(document_id)
            replacement = replace(
                document,
                module_id=document.module_id if module_id is None else module_id,
                logical_name=(
                    document.logical_name if logical_name is None else logical_name
                ),
                text=text,
                path=self._path_text(source_path),
                dirty=False,
            )
            linked: str | None | object = Ellipsis
            linked_default: bool | object = Ellipsis
            if document.is_primary and self.snapshot.linked_c_path_is_default:
                linked = self._default_c_path(replacement)
                linked_default = True
            self._replace_document(
                document_id,
                replacement,
                reason="document-opened",
                active_document_id=(
                    document_id if make_active else self.snapshot.active_document_id
                ),
                linked_c_path=linked,
                linked_c_path_is_default=linked_default,
            )
            return replacement

    def open_python(self, path: Path) -> str:
        """Compatibility operation: open into the active document."""

        opened = self.open_document(
            path,
            document_id=self.snapshot.active_document_id,
            make_active=True,
        )
        return opened.text

    def save_document(
        self,
        document_id: str | None = None,
        path: Path | str | None = None,
    ) -> str:
        with self._lock:
            identifier = document_id or self.snapshot.active_document_id
            document = self._document(identifier)
            destination = (
                self._path_text(path)
                if path is not None
                else document.path
            )
            if destination is None:
                raise ValueError("document has no linked Python path")
            replacement = replace(document, path=destination, dirty=False)
            candidate = tuple(
                replacement if item.document_id == identifier else item
                for item in self.snapshot.documents
            )
            # Save As must be transactional with respect to workspace path
            # ownership.  Validate the prospective snapshot before the atomic
            # writer is allowed to create a temporary or replace a destination.
            self._validate_documents(candidate)
            self._writer.write_text(Path(destination), document.text)
            linked: str | None | object = Ellipsis
            linked_default: bool | object = Ellipsis
            if document.is_primary and self.snapshot.linked_c_path_is_default:
                linked = self._default_c_path(replacement)
                linked_default = True
            self._replace_document(
                identifier,
                replacement,
                reason="document-saved",
                linked_c_path=linked,
                linked_c_path_is_default=linked_default,
            )
            return destination

    def save_python(self, path: Path) -> None:
        self.save_document(self.snapshot.active_document_id, path)

    @staticmethod
    def _default_c_path(document: WorkspaceDocument) -> str | None:
        if document.path is None:
            return None
        return str(Path(document.path).with_suffix(".c"))

    def link_generated_c(self, path: Path | str | None = None) -> str:
        with self._lock:
            if path is None:
                destination = self._default_c_path(self.snapshot.primary_document)
                if destination is None:
                    raise ValueError("primary document has no linked Python path")
                is_default = True
            else:
                destination = self._path_text(path)
                is_default = False
            self._publish(
                replace(
                    self.snapshot,
                    linked_c_path=destination,
                    linked_c_path_is_default=is_default,
                )
            )
            return destination

    def _require_publishable_c(self) -> str:
        snapshot = self.snapshot
        if snapshot.generated_c is None:
            raise ValueError("no complete generated C result is available")
        if not snapshot.can_save_c:
            raise ValueError("generated C is stale or not publishable for the current bundle")
        return snapshot.generated_c

    def save_generated_c(self, path: Path) -> None:
        with self._lock:
            generated_c = self._require_publishable_c()
            destination = self._path_text(path)
            self._writer.write_text(Path(destination), generated_c)
            self._publish(
                replace(
                    self.snapshot,
                    linked_c_path=destination,
                    linked_c_path_is_default=False,
                )
            )

    def save_generated_c_linked(self) -> str:
        with self._lock:
            generated_c = self._require_publishable_c()
            destination = self.snapshot.linked_c_path
            is_default = self.snapshot.linked_c_path_is_default
            if destination is None:
                destination = self._default_c_path(self.snapshot.primary_document)
                if destination is None:
                    raise ValueError("generated C has no linked output path")
                is_default = True
            self._writer.write_text(Path(destination), generated_c)
            self._publish(
                replace(
                    self.snapshot,
                    linked_c_path=destination,
                    linked_c_path_is_default=is_default,
                )
            )
            return destination

    def set_preference(self, key: str, value: PreferenceValue) -> None:
        with self._lock:
            self._validate_preference(key, value)
            values = self.snapshot.preference_data()
            values[key] = value
            self._publish(replace(self.snapshot, preferences=tuple(sorted(values.items()))))

    def restore_preferences(
        self,
        values: Mapping[str, PreferenceValue],
    ) -> None:
        if not isinstance(values, Mapping):
            raise TypeError("workspace preferences must be a mapping")
        normalized: dict[str, PreferenceValue] = {}
        for key, value in values.items():
            self._validate_preference(key, value)
            normalized[key] = value
        with self._lock:
            self._publish(
                replace(self.snapshot, preferences=tuple(sorted(normalized.items())))
            )

    @staticmethod
    def _validate_preference(key: object, value: object) -> None:
        if not isinstance(key, str) or not key or any(ord(char) < 32 for char in key):
            raise ValueError("preference key must be a non-empty printable string")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise TypeError("preference value must be a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("preference float must be finite")

    def navigate_source_to_output(self, source_node_id: str) -> tuple[dict, ...]:
        return tuple(
            mapping
            for mapping in self.snapshot.mappings
            if source_node_id in tuple(mapping.get("source_node_ids", ()))
            or mapping.get("source_node_id") == source_node_id
        )

    def close(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.cancel()
        self._revision_service.close(wait=wait, timeout=2.0 if wait else None)
        self._output_index_service.close(
            wait=wait,
            timeout=2.0 if wait else None,
        )
        if self._owns_io_service:
            self._io_service.close(wait=wait, timeout=2.0 if wait else None)
        if self._owns_supervisor:
            self._supervisor.close(wait=wait, timeout=2.25 if wait else None)
