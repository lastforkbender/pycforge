from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

from .io_service import FileRead
from .model import WorkspaceDocument


class AsyncIOControllerMixin:
    """Non-blocking file operations for the PyQt-facing controller API."""

    def open_document_async(
        self,
        path: Path | str,
        *,
        module_id: str | None = None,
        logical_name: str | None = None,
        document_id: str | None = None,
        make_active: bool = True,
        is_primary: bool = False,
    ) -> Future[WorkspaceDocument]:
        source_path = Path(path)
        with self._lock:
            expected_generation = self.snapshot.revision_generation
        read = self._io_service.read_text(source_path)
        public: Future[WorkspaceDocument] = Future()

        def finished(completed: Future[FileRead]) -> None:
            try:
                value = completed.result()
                with self._lock:
                    if self._closed:
                        raise RuntimeError("workspace controller is closed")
                    if (
                        document_id is not None
                        and self.snapshot.revision_generation
                        != expected_generation
                    ):
                        raise RuntimeError(
                            "workspace changed while the file was opening"
                        )
                opened = self._apply_opened_document(
                    source_path,
                    value.text,
                    module_id=module_id,
                    logical_name=logical_name,
                    document_id=document_id,
                    make_active=make_active,
                    is_primary=is_primary,
                )
            except BaseException as exc:
                public.set_exception(exc)
            else:
                public.set_result(opened)

        read.add_done_callback(finished)
        return public

    def save_document_async(
        self,
        document_id: str | None = None,
        path: Path | str | None = None,
    ) -> Future[str]:
        with self._lock:
            identifier = document_id or self.snapshot.active_document_id
            document = self._document(identifier)
            destination = (
                self._path_text(path) if path is not None else document.path
            )
            if destination is None:
                raise ValueError("document has no linked Python path")
            prospective = replace(document, path=destination)
            candidate = tuple(
                prospective if item.document_id == identifier else item
                for item in self.snapshot.documents
            )
            self._validate_documents(candidate)
            saved_text = document.text
            original_path = document.path

        def guard() -> bool:
            with self._lock:
                if self._closed:
                    return False
                try:
                    current = self._document(identifier)
                except KeyError:
                    return False
                return bool(
                    current.path == original_path
                    and all(
                        item.document_id == identifier
                        or item.path != destination
                        for item in self.snapshot.documents
                    )
                )

        operation = self._io_service.write_text(
            destination,
            saved_text,
            before_replace=guard,
        )
        public: Future[str] = Future()

        def finished(completed: Future[str]) -> None:
            try:
                written = completed.result()
                with self._lock:
                    current = self._document(identifier)
                    replacement = replace(
                        current,
                        path=written,
                        dirty=current.text != saved_text,
                    )
                    linked: str | None | object = Ellipsis
                    linked_default: bool | object = Ellipsis
                    if (
                        current.is_primary
                        and self.snapshot.linked_c_path_is_default
                    ):
                        linked = self._default_c_path(replacement)
                        linked_default = True
                    self._replace_document(
                        identifier,
                        replacement,
                        reason="document-saved",
                        linked_c_path=linked,
                        linked_c_path_is_default=linked_default,
                    )
            except BaseException as exc:
                public.set_exception(exc)
            else:
                public.set_result(written)

        operation.add_done_callback(finished)
        return public

    def save_generated_c_linked_async(self) -> Future[str]:
        with self._lock:
            generated_c = self._require_publishable_c()
            snapshot = self.snapshot
            destination = snapshot.linked_c_path
            is_default = snapshot.linked_c_path_is_default
            if destination is None:
                destination = self._default_c_path(snapshot.primary_document)
                if destination is None:
                    raise ValueError("generated C has no linked output path")
                is_default = True
            expected = (
                snapshot.revision_generation,
                snapshot.bundle_fingerprint,
                snapshot.result_revision_generation,
                snapshot.result_bundle_fingerprint,
                generated_c,
            )

        def guard() -> bool:
            with self._lock:
                current = self.snapshot
                return bool(
                    not self._closed
                    and current.can_save_c
                    and (
                        current.revision_generation,
                        current.bundle_fingerprint,
                        current.result_revision_generation,
                        current.result_bundle_fingerprint,
                        current.generated_c,
                    )
                    == expected
                )

        operation = self._io_service.write_text(
            destination,
            generated_c,
            before_replace=guard,
        )
        public: Future[str] = Future()

        def finished(completed: Future[str]) -> None:
            try:
                written = completed.result()
                with self._lock:
                    self._publish(
                        replace(
                            self.snapshot,
                            linked_c_path=written,
                            linked_c_path_is_default=is_default,
                        )
                    )
            except BaseException as exc:
                public.set_exception(exc)
            else:
                public.set_result(written)

        operation.add_done_callback(finished)
        return public

    def observe_linked_file_async(self, path: Path | str) -> Future[FileRead]:
        return self._io_service.observe_text(path)


__all__ = ["AsyncIOControllerMixin"]
