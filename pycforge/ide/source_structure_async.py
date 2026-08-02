"""Latest-wins worker for :mod:`pycforge.ide.source_structure`."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, Thread, current_thread
from typing import Callable, Iterable

from .source_structure import (
    DEFAULT_OUTLINE_DEPTH,
    DEFAULT_OUTLINE_NAME_CHARS,
    DEFAULT_OUTLINE_TEXT_CHARS,
    MAX_OUTLINE_DEPTH,
    MAX_OUTLINE_NAME_CHARS,
    MAX_OUTLINE_SYMBOLS,
    MAX_OUTLINE_TEXT_CHARS,
    MAX_STRUCTURE_WORKSPACE_KEY_CHARS,
    SourceStructureDocument,
    SourceStructureResult,
    _bounded_int,
    _captured_documents,
    build_source_structure,
)


@dataclass(frozen=True, slots=True)
class _StructureRequest:
    generation: int
    workspace_key: str
    documents: tuple[SourceStructureDocument, ...]
    callback: Callable[[SourceStructureResult], None]


class AsyncSourceStructureService:
    """One-active, one-latest structure observer with stale suppression."""

    def __init__(
        self,
        *,
        max_symbols: int = MAX_OUTLINE_SYMBOLS,
        max_depth: int = DEFAULT_OUTLINE_DEPTH,
        max_name_chars: int = DEFAULT_OUTLINE_NAME_CHARS,
        max_text_chars: int = DEFAULT_OUTLINE_TEXT_CHARS,
    ) -> None:
        self._max_symbols = _bounded_int(
            max_symbols, name="max_symbols", maximum=MAX_OUTLINE_SYMBOLS
        )
        self._max_depth = _bounded_int(
            max_depth, name="max_depth", maximum=MAX_OUTLINE_DEPTH
        )
        self._max_name_chars = _bounded_int(
            max_name_chars,
            name="max_name_chars",
            maximum=MAX_OUTLINE_NAME_CHARS,
        )
        self._max_text_chars = _bounded_int(
            max_text_chars,
            name="max_text_chars",
            maximum=MAX_OUTLINE_TEXT_CHARS,
        )
        self._condition = Condition()
        self._generation = 0
        self._active_generation: int | None = None
        self._pending: _StructureRequest | None = None
        self._closed = False
        self._worker = Thread(
            target=self._worker_main,
            name="pycforge-source-structure",
            daemon=True,
        )
        self._worker.start()

    @property
    def worker_is_daemon(self) -> bool:
        return self._worker.daemon

    @property
    def active_generation(self) -> int | None:
        with self._condition:
            return self._active_generation

    @property
    def pending_generation(self) -> int | None:
        with self._condition:
            return (
                self._pending.generation
                if self._pending is not None
                else None
            )

    @property
    def is_closed(self) -> bool:
        with self._condition:
            return self._closed

    def submit(
        self,
        documents: Iterable[SourceStructureDocument],
        *,
        workspace_key: str,
        callback: Callable[[SourceStructureResult], None],
    ) -> int:
        records = _captured_documents(documents)
        if not isinstance(workspace_key, str):
            raise TypeError("workspace key must be a string")
        if len(workspace_key) > MAX_STRUCTURE_WORKSPACE_KEY_CHARS:
            raise ValueError("workspace key exceeds the observer identity limit")
        if not callable(callback):
            raise TypeError("structure callback must be callable")
        with self._condition:
            if self._closed:
                raise RuntimeError("source structure service is closed")
            self._generation += 1
            generation = self._generation
            self._pending = _StructureRequest(
                generation, workspace_key, records, callback
            )
            self._condition.notify()
            return generation

    def cancel(self) -> int:
        with self._condition:
            if self._closed:
                return self._generation
            self._generation += 1
            self._pending = None
            self._condition.notify()
            return self._generation

    def close(self, *, wait_seconds: float = 0.05) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._pending = None
            self._condition.notify_all()
        if wait_seconds > 0 and current_thread() is not self._worker:
            self._worker.join(timeout=wait_seconds)

    def _is_cancelled(self, generation: int) -> bool:
        with self._condition:
            return self._closed or generation != self._generation

    def _worker_main(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                request = self._pending
                self._pending = None
                assert request is not None
                self._active_generation = request.generation

            try:
                result = build_source_structure(
                    request.documents,
                    generation=request.generation,
                    workspace_key=request.workspace_key,
                    max_symbols=self._max_symbols,
                    max_depth=self._max_depth,
                    max_name_chars=self._max_name_chars,
                    max_text_chars=self._max_text_chars,
                    cancelled=lambda: self._is_cancelled(
                        request.generation
                    ),
                )
            except Exception:
                # Structure is an observer; failure cannot retire future work
                # or publish an unauthenticated partial outline.
                result = None

            with self._condition:
                if self._active_generation == request.generation:
                    self._active_generation = None
                deliver = (
                    result is not None
                    and not self._closed
                    and request.generation == self._generation
                )
            if deliver:
                try:
                    request.callback(result)
                except Exception:
                    # Observer callbacks are outside structure authority.
                    pass


__all__ = ["AsyncSourceStructureService"]
