"""Bounded literal search over an explicitly captured source bundle.

This module is independent of Qt and performs no file-system access.  A search
request owns immutable strings supplied by the caller; linked document paths
are deliberately absent from the input contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from threading import Condition, Thread, current_thread
from time import monotonic
from typing import Callable, Iterable


MAX_BUNDLE_DOCUMENTS = 64
MAX_BUNDLE_MATCHES = 5_000
MAX_QUERY_CHARS = 4_096
MAX_PREVIEW_CHARS = 512
MAX_DOCUMENT_ID_CHARS = 128
MAX_LOGICAL_NAME_CHARS = 4_096
DEFAULT_PREVIEW_CHARS = 240
DEFAULT_SCAN_CHUNK = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkspaceSearchDocument:
    """One already-open document captured for a search request."""

    document_id: str
    logical_name: str
    text: str


@dataclass(frozen=True, slots=True)
class BundleSearchMatch:
    """One literal match with explicit Python and Qt position contracts.

    ``start`` and ``end`` are Python code-point offsets. ``qt_start`` and
    ``qt_end`` are UTF-16 code-unit offsets suitable for a Qt text cursor.
    """

    document_id: str
    logical_name: str
    document_ordinal: int
    start: int
    end: int
    qt_start: int
    qt_end: int
    preview: str


@dataclass(frozen=True, slots=True)
class BundleSearchResult:
    """A globally bounded search result.

    When ``truncated`` is true, ``total_count`` is a lower bound of
    ``MAX_BUNDLE_MATCHES + 1``.  Scanning stops at that first omitted match so
    a broad query cannot create unbounded background work merely to count.
    """

    generation: int
    matches: tuple[BundleSearchMatch, ...]
    total_count: int
    truncated: bool
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _BundleSearchRequest:
    generation: int
    documents: tuple[WorkspaceSearchDocument, ...]
    query: str
    match_case: bool
    whole_word: bool
    callback: Callable[[BundleSearchResult], None]


def _captured_documents(
    documents: Iterable[WorkspaceSearchDocument],
) -> tuple[WorkspaceSearchDocument, ...]:
    records = tuple(documents)
    if not 1 <= len(records) <= MAX_BUNDLE_DOCUMENTS:
        raise ValueError("search requires between 1 and 64 open documents")
    document_ids: list[str] = []
    logical_names: list[str] = []
    for document in records:
        if not isinstance(document, WorkspaceSearchDocument):
            raise TypeError(
                "search documents must be WorkspaceSearchDocument values"
            )
        if (
            not isinstance(document.document_id, str)
            or not document.document_id
            or len(document.document_id) > MAX_DOCUMENT_ID_CHARS
        ):
            raise ValueError("search document ID must be non-empty text")
        if (
            not isinstance(document.logical_name, str)
            or not document.logical_name
            or len(document.logical_name) > MAX_LOGICAL_NAME_CHARS
        ):
            raise ValueError("search logical name must be non-empty text")
        if not isinstance(document.text, str):
            raise TypeError("search document text must be a string")
        document_ids.append(document.document_id)
        logical_names.append(document.logical_name)
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("search document IDs must be unique")
    if len(logical_names) != len(set(logical_names)):
        raise ValueError("search logical names must be unique")
    return records


def _positive_bounded_int(
    value: object,
    *,
    name: str,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def _bounded_preview(
    text: str,
    start: int,
    end: int,
    budget: int,
) -> str:
    """Return one bounded, single-line context window."""

    left = max(0, start - budget // 3)
    right = min(len(text), left + budget)
    if right - left < budget:
        left = max(0, right - budget)
    value = text[left:right].replace("\r", " ").replace("\n", " ")
    if left:
        value = "\N{HORIZONTAL ELLIPSIS}" + value[1:]
    if right < len(text) and value:
        value = value[:-1] + "\N{HORIZONTAL ELLIPSIS}"
    # Replacements above preserve length, but retain a final fail-closed cap.
    return value[:budget]


def search_closed_documents(
    documents: Iterable[WorkspaceSearchDocument],
    query: str,
    *,
    generation: int = 0,
    match_case: bool = False,
    whole_word: bool = False,
    match_limit: int = MAX_BUNDLE_MATCHES,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    scan_chunk: int = DEFAULT_SCAN_CHUNK,
    cancelled: Callable[[], bool] | None = None,
) -> BundleSearchResult | None:
    """Synchronously search captured documents without consulting the host.

    The returned match sequence is in bundle order and then source order.
    ``None`` means the caller's generation was cancelled before publication.
    """

    started = monotonic()
    records = _captured_documents(documents)
    if not isinstance(query, str):
        raise TypeError("search query must be a string")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(
            f"search query exceeds the {MAX_QUERY_CHARS}-character limit"
        )
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise TypeError("search generation must be an integer")
    if generation < 0:
        raise ValueError("search generation must be non-negative")
    match_limit = _positive_bounded_int(
        match_limit,
        name="match_limit",
        maximum=MAX_BUNDLE_MATCHES,
    )
    preview_chars = _positive_bounded_int(
        preview_chars,
        name="preview_chars",
        maximum=MAX_PREVIEW_CHARS,
    )
    scan_chunk = _positive_bounded_int(
        scan_chunk,
        name="scan_chunk",
        maximum=4 * 1024 * 1024,
    )
    is_cancelled = cancelled or (lambda: False)
    if is_cancelled():
        return None
    if not query:
        return BundleSearchResult(
            generation, (), 0, False, monotonic() - started
        )

    expression = re.escape(query)
    if whole_word:
        expression = rf"(?<!\w){expression}(?!\w)"
    pattern = re.compile(expression, 0 if match_case else re.IGNORECASE)
    matches: list[BundleSearchMatch] = []
    total_count = 0

    for ordinal, document in enumerate(records):
        if is_cancelled():
            return None
        text = document.text
        if len(query) > len(text):
            continue
        ownership_width = max(scan_chunk, len(query) + 1)
        ownership_start = 0
        last_match_end = 0
        codepoint_position = 0
        qt_position = 0
        matches_since_check = 0

        while ownership_start < len(text):
            if is_cancelled():
                return None
            ownership_end = min(
                len(text), ownership_start + ownership_width
            )
            search_start = max(ownership_start, last_match_end)
            search_end = min(
                len(text),
                ownership_end + len(query) + (1 if whole_word else 0),
            )
            for found in pattern.finditer(text, search_start, search_end):
                start, end = found.span()
                if start >= ownership_end:
                    break
                total_count += 1
                if total_count > match_limit:
                    return BundleSearchResult(
                        generation,
                        tuple(matches),
                        total_count,
                        True,
                        monotonic() - started,
                    )
                qt_position += _utf16_units(
                    text[codepoint_position:start]
                )
                qt_start = qt_position
                qt_position += _utf16_units(text[start:end])
                matches.append(
                    BundleSearchMatch(
                        document.document_id,
                        document.logical_name,
                        ordinal,
                        start,
                        end,
                        qt_start,
                        qt_position,
                        _bounded_preview(
                            text, start, end, preview_chars
                        ),
                    )
                )
                codepoint_position = end
                last_match_end = end
                matches_since_check += 1
                if matches_since_check >= 256:
                    matches_since_check = 0
                    if is_cancelled():
                        return None
            ownership_start = ownership_end

    return BundleSearchResult(
        generation,
        tuple(matches),
        total_count,
        False,
        monotonic() - started,
    )


class AsyncBundleSearchService:
    """One-active, one-latest-pending search with stale-result suppression."""

    def __init__(
        self,
        *,
        match_limit: int = MAX_BUNDLE_MATCHES,
        preview_chars: int = DEFAULT_PREVIEW_CHARS,
        scan_chunk: int = DEFAULT_SCAN_CHUNK,
    ) -> None:
        self._match_limit = _positive_bounded_int(
            match_limit,
            name="match_limit",
            maximum=MAX_BUNDLE_MATCHES,
        )
        self._preview_chars = _positive_bounded_int(
            preview_chars,
            name="preview_chars",
            maximum=MAX_PREVIEW_CHARS,
        )
        self._scan_chunk = _positive_bounded_int(
            scan_chunk,
            name="scan_chunk",
            maximum=4 * 1024 * 1024,
        )
        self._condition = Condition()
        self._generation = 0
        self._active_generation: int | None = None
        self._pending: _BundleSearchRequest | None = None
        self._closed = False
        self._worker = Thread(
            target=self._worker_main,
            name="pycforge-bundle-search",
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
        documents: Iterable[WorkspaceSearchDocument],
        query: str,
        *,
        match_case: bool = False,
        whole_word: bool = False,
        callback: Callable[[BundleSearchResult], None],
    ) -> int:
        records = _captured_documents(documents)
        if not isinstance(query, str):
            raise TypeError("search query must be a string")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(
                f"search query exceeds the {MAX_QUERY_CHARS}-character limit"
            )
        if not callable(callback):
            raise TypeError("search callback must be callable")
        with self._condition:
            if self._closed:
                raise RuntimeError("bundle search service is closed")
            self._generation += 1
            generation = self._generation
            self._pending = _BundleSearchRequest(
                generation,
                records,
                query,
                bool(match_case),
                bool(whole_word),
                callback,
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
                result = search_closed_documents(
                    request.documents,
                    request.query,
                    generation=request.generation,
                    match_case=request.match_case,
                    whole_word=request.whole_word,
                    match_limit=self._match_limit,
                    preview_chars=self._preview_chars,
                    scan_chunk=self._scan_chunk,
                    cancelled=lambda: self._is_cancelled(
                        request.generation
                    ),
                )
            except Exception:
                # A non-authoritative observer defect must not retire the
                # service or publish a plausible partial result.
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
                    # Presentation observers cannot retire the sole worker.
                    pass


__all__ = [
    "AsyncBundleSearchService",
    "BundleSearchMatch",
    "BundleSearchResult",
    "DEFAULT_PREVIEW_CHARS",
    "MAX_BUNDLE_DOCUMENTS",
    "MAX_BUNDLE_MATCHES",
    "WorkspaceSearchDocument",
    "search_closed_documents",
]
