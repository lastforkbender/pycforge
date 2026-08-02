"""Bounded background literal search for the optional PyQt workspace.

The service in this module is deliberately independent of Qt.  It owns one
daemon worker thread and one replaceable pending request, so rapid editor or
query changes cannot build an unbounded queue.  Results contain Qt-compatible
UTF-16 positions, but only a bounded prefix of the matches is retained.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from threading import Condition, Thread
from time import monotonic
from typing import Callable


DEFAULT_MATCH_LIMIT = 5_000
DEFAULT_SCAN_CHUNK = 64 * 1024


@dataclass(frozen=True, slots=True)
class LiteralSearchResult:
    """The bounded result of one immutable literal-search request."""

    generation: int
    ranges: tuple[tuple[int, int], ...]
    total_count: int
    elapsed_seconds: float

    @property
    def truncated(self) -> bool:
        return self.total_count > len(self.ranges)


@dataclass(frozen=True, slots=True)
class _SearchRequest:
    generation: int
    text: str
    query: str
    match_case: bool
    whole_word: bool
    callback: Callable[[LiteralSearchResult], None]


def _qt_ranges(
    text: str, ranges: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, int], ...]:
    """Convert ordered Python code-point ranges to Qt UTF-16 positions."""

    converted: list[tuple[int, int]] = []
    codepoint_position = 0
    qt_position = 0
    for start, end in ranges:
        qt_position += len(text[codepoint_position:start].encode("utf-16-le")) // 2
        qt_start = qt_position
        qt_position += len(text[start:end].encode("utf-16-le")) // 2
        converted.append((qt_start, qt_position))
        codepoint_position = end
    return tuple(converted)


def _bounded_literal_search(
    request: _SearchRequest,
    *,
    match_limit: int,
    scan_chunk: int,
    cancelled: Callable[[], bool],
) -> LiteralSearchResult | None:
    """Scan an immutable request in cancellable windows.

    Searching bounded windows instead of invoking one full-document regex
    search gives the supervisor a cancellation point even when the document
    contains no matches.  Window ownership is based on match start positions;
    an overlap large enough for the literal and its word-boundary lookahead
    preserves the same non-overlapping semantics as ``re.finditer``.
    """

    started = monotonic()
    if cancelled():
        return None
    if not request.query or len(request.query) > len(request.text):
        return LiteralSearchResult(request.generation, (), 0, monotonic() - started)

    expression = re.escape(request.query)
    if request.whole_word:
        expression = rf"(?<!\w){expression}(?!\w)"
    flags = 0 if request.match_case else re.IGNORECASE
    pattern = re.compile(expression, flags)

    stored: list[tuple[int, int]] = []
    total_count = 0
    text_length = len(request.text)
    # Avoid repeatedly scanning a very large literal through small overlapping
    # windows.  Ordinary queries retain the 64 KiB cancellation granularity.
    ownership_width = max(scan_chunk, len(request.query) + 1)
    ownership_start = 0
    last_match_end = 0
    matches_since_cancel_check = 0

    while ownership_start < text_length:
        if cancelled():
            return None
        ownership_end = min(text_length, ownership_start + ownership_width)
        search_start = max(ownership_start, last_match_end)
        # Include enough right context for a match that begins in this window
        # plus one code point for the whole-word lookahead.
        search_end = min(
            text_length,
            ownership_end + len(request.query) + (1 if request.whole_word else 0),
        )
        for match in pattern.finditer(request.text, search_start, search_end):
            start, end = match.span()
            if start >= ownership_end:
                break
            total_count += 1
            if len(stored) < match_limit:
                stored.append((start, end))
            last_match_end = end
            matches_since_cancel_check += 1
            if matches_since_cancel_check >= 256:
                matches_since_cancel_check = 0
                if cancelled():
                    return None
        ownership_start = ownership_end

    return LiteralSearchResult(
        request.generation,
        _qt_ranges(request.text, tuple(stored)),
        total_count,
        monotonic() - started,
    )


class AsyncLiteralSearchService:
    """Latest-wins literal search with one daemon worker and bounded results."""

    def __init__(
        self,
        *,
        match_limit: int = DEFAULT_MATCH_LIMIT,
        scan_chunk: int = DEFAULT_SCAN_CHUNK,
    ) -> None:
        if isinstance(match_limit, bool) or not isinstance(match_limit, int):
            raise TypeError("match_limit must be an integer")
        if isinstance(scan_chunk, bool) or not isinstance(scan_chunk, int):
            raise TypeError("scan_chunk must be an integer")
        if match_limit <= 0:
            raise ValueError("match_limit must be positive")
        if scan_chunk <= 0:
            raise ValueError("scan_chunk must be positive")
        self._match_limit = match_limit
        self._scan_chunk = scan_chunk
        self._condition = Condition()
        self._generation = 0
        self._active_generation: int | None = None
        self._pending: _SearchRequest | None = None
        self._closed = False
        self._worker = Thread(
            target=self._worker_main,
            name="pycforge-literal-search",
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
            return self._pending.generation if self._pending is not None else None

    def submit(
        self,
        text: str,
        query: str,
        *,
        match_case: bool = False,
        whole_word: bool = False,
        callback: Callable[[LiteralSearchResult], None],
    ) -> int:
        """Replace the pending request and return its monotonic generation."""

        if not isinstance(text, str) or not isinstance(query, str):
            raise TypeError("text and query must be strings")
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._condition:
            if self._closed:
                raise RuntimeError("search service is closed")
            self._generation += 1
            generation = self._generation
            self._pending = _SearchRequest(
                generation,
                text,
                query,
                bool(match_case),
                bool(whole_word),
                callback,
            )
            self._condition.notify()
            return generation

    def cancel(self) -> int:
        """Cancel the active generation and discard the pending request."""

        with self._condition:
            if self._closed:
                return self._generation
            self._generation += 1
            self._pending = None
            self._condition.notify()
            return self._generation

    def close(self, *, wait_seconds: float = 0.05) -> None:
        """Stop accepting work and cooperatively end the daemon worker."""

        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._pending = None
            self._condition.notify()
        if wait_seconds > 0:
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

            result = _bounded_literal_search(
                request,
                match_limit=self._match_limit,
                scan_chunk=self._scan_chunk,
                cancelled=lambda: self._is_cancelled(request.generation),
            )

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
                    # A disappearing Qt receiver or a consumer callback must
                    # not retire the sole search worker.
                    continue


__all__ = [
    "AsyncLiteralSearchService",
    "DEFAULT_MATCH_LIMIT",
    "DEFAULT_SCAN_CHUNK",
    "LiteralSearchResult",
]
