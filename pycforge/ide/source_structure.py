"""Bounded source outline and breadcrumb observers for open documents.

Structure is derived from the converter's declared Python 3.11 parser and
normalizer, but remains presentation-only.  Invalid source, observer failure,
or a superseded request produces no converter fact and cannot change source
eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable, Iterable

from pycforge.converter.frontend.normalizer import PythonNormalizer
from pycforge.converter.frontend.parser import Python311ParserAdapter
from pycforge.converter.frontend.source_document import SourceDocument
from pycforge.converter.ir.python_ir import python_ir_reference_ids


MAX_STRUCTURE_DOCUMENTS = 64
MAX_OUTLINE_SYMBOLS = 4_096
MAX_OUTLINE_DEPTH = 64
MAX_OUTLINE_NAME_CHARS = 256
MAX_OUTLINE_TEXT_CHARS = 256 * 1024
MAX_STRUCTURE_DOCUMENT_ID_CHARS = 128
MAX_STRUCTURE_MODULE_ID_CHARS = 255
MAX_STRUCTURE_LOGICAL_NAME_CHARS = 4_096
MAX_STRUCTURE_WORKSPACE_KEY_CHARS = 256

DEFAULT_OUTLINE_DEPTH = 32
DEFAULT_OUTLINE_NAME_CHARS = 160
DEFAULT_OUTLINE_TEXT_CHARS = 128 * 1024
_SYMBOL_KINDS = frozenset(
    {"Module", "ClassDef", "FunctionDef", "AsyncFunctionDef"}
)


@dataclass(frozen=True, slots=True)
class SourceStructureDocument:
    """One already-open source document captured by an observer request."""

    document_id: str
    module_id: str
    logical_name: str
    text: str


@dataclass(frozen=True, slots=True)
class OutlineSymbol:
    """One flat, parent-linked outline record with code-point positions."""

    document_id: str
    module_id: str
    logical_name: str
    node_id: str
    parent_node_id: str | None
    kind: str
    name: str
    detail: str
    depth: int
    start: int
    end: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True, slots=True)
class SourceStructureResult:
    """A bounded, non-authoritative structure snapshot."""

    generation: int
    workspace_key: str
    symbols: tuple[OutlineSymbol, ...]
    total_symbol_count: int
    invalid_document_ids: tuple[str, ...]
    observer_failed_document_ids: tuple[str, ...]
    truncated: bool
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _Candidate:
    node_id: str
    raw_parent_id: str | None
    kind: str
    name: str
    start: int
    end: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


def _captured_documents(
    documents: Iterable[SourceStructureDocument],
) -> tuple[SourceStructureDocument, ...]:
    records = tuple(documents)
    if not 1 <= len(records) <= MAX_STRUCTURE_DOCUMENTS:
        raise ValueError("structure requires between 1 and 64 open documents")
    document_ids: list[str] = []
    module_ids: list[str] = []
    logical_names: list[str] = []
    for document in records:
        if not isinstance(document, SourceStructureDocument):
            raise TypeError(
                "structure documents must be SourceStructureDocument values"
            )
        for label, value, maximum in (
            (
                "document ID",
                document.document_id,
                MAX_STRUCTURE_DOCUMENT_ID_CHARS,
            ),
            (
                "module ID",
                document.module_id,
                MAX_STRUCTURE_MODULE_ID_CHARS,
            ),
            (
                "logical name",
                document.logical_name,
                MAX_STRUCTURE_LOGICAL_NAME_CHARS,
            ),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > maximum
            ):
                raise ValueError(f"structure {label} must be non-empty text")
        if not isinstance(document.text, str):
            raise TypeError("structure document text must be a string")
        document_ids.append(document.document_id)
        module_ids.append(document.module_id)
        logical_names.append(document.logical_name)
    for label, values in (
        ("document IDs", document_ids),
        ("module IDs", module_ids),
        ("logical names", logical_names),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"structure {label} must be unique")
    return records


def _bounded_int(
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


def _clipped_name(value: str, budget: int) -> tuple[str, bool]:
    if len(value) <= budget:
        return value, False
    if budget == 1:
        return "\N{HORIZONTAL ELLIPSIS}", True
    return value[: budget - 1] + "\N{HORIZONTAL ELLIPSIS}", True


def _span_values(
    span: object,
    *,
    text_length: int,
) -> tuple[int, int, int, int, int, int] | None:
    if not isinstance(span, dict):
        return None
    start = span.get("start")
    end = span.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return None
    values = (
        start.get("offset"),
        end.get("offset"),
        start.get("line"),
        start.get("column"),
        end.get("line"),
        end.get("column"),
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    start_offset, end_offset, start_line, start_column, end_line, end_column = values
    if (
        start_offset < 0
        or end_offset < start_offset
        or end_offset > text_length
        or start_line < 1
        or end_line < start_line
        or start_column < 0
        or end_column < 0
    ):
        return None
    return (
        start_offset,
        end_offset,
        start_line,
        start_column,
        end_line,
        end_column,
    )


def _document_candidates(
    document: SourceStructureDocument,
) -> tuple[_Candidate, ...]:
    source = SourceDocument.create(document.logical_name, document.text)
    tree = Python311ParserAdapter().parse(source, "3.11")
    normalized = PythonNormalizer().normalize(tree, source)
    known = {node.node_id for node in normalized.nodes}
    parents: dict[str, str] = {}
    for node in normalized.nodes:
        for field_name, value in node.fields:
            for child_id in python_ir_reference_ids(
                node.kind, field_name, value, known
            ):
                parents.setdefault(child_id, node.node_id)

    candidates: list[_Candidate] = []
    for node in normalized.nodes:
        if node.kind not in _SYMBOL_KINDS:
            continue
        if node.kind == "Module":
            candidates.append(
                _Candidate(
                    node.node_id,
                    None,
                    node.kind,
                    document.module_id,
                    0,
                    len(document.text),
                    1,
                    0,
                    document.text.count("\n") + 1,
                    0,
                )
            )
            continue
        fields = dict(node.fields)
        name = fields.get("name")
        if not isinstance(name, str) or not name:
            continue
        values = _span_values(
            node.provenance.source_span,
            text_length=len(document.text),
        )
        if values is None:
            continue
        candidates.append(
            _Candidate(
                node.node_id,
                parents.get(node.node_id),
                node.kind,
                name,
                *values,
            )
        )
    candidate_ids = {candidate.node_id for candidate in candidates}
    resolved: list[_Candidate] = []
    for candidate in candidates:
        parent = candidate.raw_parent_id
        seen: set[str] = set()
        while parent is not None and parent not in candidate_ids:
            if parent in seen:
                parent = None
                break
            seen.add(parent)
            parent = parents.get(parent)
        resolved.append(
            _Candidate(
                candidate.node_id,
                parent,
                candidate.kind,
                candidate.name,
                candidate.start,
                candidate.end,
                candidate.start_line,
                candidate.start_column,
                candidate.end_line,
                candidate.end_column,
            )
        )
    return tuple(resolved)


def _nearest_symbol_parents(
    candidates: tuple[_Candidate, ...],
) -> tuple[dict[str, str | None], dict[str, int]]:
    candidate_ids = {candidate.node_id for candidate in candidates}
    raw_parents = {
        candidate.node_id: candidate.raw_parent_id
        for candidate in candidates
    }
    parents: dict[str, str | None] = {}
    for candidate in candidates:
        parent = candidate.raw_parent_id
        seen: set[str] = set()
        while parent is not None and parent not in candidate_ids:
            if parent in seen:
                parent = None
                break
            seen.add(parent)
            parent = raw_parents.get(parent)
        parents[candidate.node_id] = parent

    depths: dict[str, int] = {}

    def depth_for(node_id: str) -> int:
        if node_id in depths:
            return depths[node_id]
        chain: list[str] = []
        current: str | None = node_id
        seen: set[str] = set()
        while current is not None and current not in depths:
            if current in seen:
                for item in chain:
                    depths[item] = 0
                return 0
            seen.add(current)
            chain.append(current)
            current = parents.get(current)
        depth = depths.get(current, -1) + 1
        for item in reversed(chain):
            depths[item] = depth
            depth += 1
        return depths[node_id]

    for candidate in candidates:
        depth_for(candidate.node_id)
    return parents, depths


def build_source_structure(
    documents: Iterable[SourceStructureDocument],
    *,
    generation: int = 0,
    workspace_key: str = "",
    max_symbols: int = MAX_OUTLINE_SYMBOLS,
    max_depth: int = DEFAULT_OUTLINE_DEPTH,
    max_name_chars: int = DEFAULT_OUTLINE_NAME_CHARS,
    max_text_chars: int = DEFAULT_OUTLINE_TEXT_CHARS,
    cancelled: Callable[[], bool] | None = None,
) -> SourceStructureResult | None:
    """Build an inert structure projection from captured open text only."""

    started = monotonic()
    records = _captured_documents(documents)
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise TypeError("structure generation must be an integer")
    if generation < 0:
        raise ValueError("structure generation must be non-negative")
    if not isinstance(workspace_key, str):
        raise TypeError("workspace key must be a string")
    if len(workspace_key) > MAX_STRUCTURE_WORKSPACE_KEY_CHARS:
        raise ValueError("workspace key exceeds the observer identity limit")
    max_symbols = _bounded_int(
        max_symbols, name="max_symbols", maximum=MAX_OUTLINE_SYMBOLS
    )
    max_depth = _bounded_int(
        max_depth, name="max_depth", maximum=MAX_OUTLINE_DEPTH
    )
    max_name_chars = _bounded_int(
        max_name_chars,
        name="max_name_chars",
        maximum=MAX_OUTLINE_NAME_CHARS,
    )
    max_text_chars = _bounded_int(
        max_text_chars,
        name="max_text_chars",
        maximum=MAX_OUTLINE_TEXT_CHARS,
    )
    is_cancelled = cancelled or (lambda: False)
    symbols: list[OutlineSymbol] = []
    invalid: list[str] = []
    observer_failed: list[str] = []
    total_symbols = 0
    text_chars = 0
    truncated = False
    output_full = False

    for document in records:
        if is_cancelled():
            return None
        try:
            candidates = _document_candidates(document)
        except (
            SyntaxError,
            UnicodeError,
            ValueError,
            RecursionError,
        ):
            invalid.append(document.document_id)
            continue
        except Exception:
            observer_failed.append(document.document_id)
            continue
        if is_cancelled():
            return None
        parents, depths = _nearest_symbol_parents(candidates)
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.start,
                depths[item.node_id],
                item.end,
                item.kind,
                item.node_id,
            ),
        )
        total_symbols += len(ordered)
        stored_ids = {symbol.node_id for symbol in symbols}
        for candidate in ordered:
            depth = depths[candidate.node_id]
            if depth > max_depth:
                truncated = True
                continue
            name, name_truncated = _clipped_name(
                candidate.name, max_name_chars
            )
            truncated = truncated or name_truncated
            detail = {
                "Module": "module",
                "ClassDef": "class",
                "FunctionDef": "function",
                "AsyncFunctionDef": "async function",
            }[candidate.kind]
            parent_id = parents[candidate.node_id]
            if parent_id is not None and parent_id not in stored_ids:
                truncated = True
                continue
            required_text = len(name) + len(detail)
            if (
                output_full
                or len(symbols) >= max_symbols
                or text_chars + required_text > max_text_chars
            ):
                output_full = True
                truncated = True
                continue
            symbols.append(
                OutlineSymbol(
                    document.document_id,
                    document.module_id,
                    document.logical_name,
                    candidate.node_id,
                    parent_id,
                    candidate.kind,
                    name,
                    detail,
                    depth,
                    candidate.start,
                    candidate.end,
                    candidate.start_line,
                    candidate.start_column,
                    candidate.end_line,
                    candidate.end_column,
                )
            )
            stored_ids.add(candidate.node_id)
            text_chars += required_text

    return SourceStructureResult(
        generation,
        workspace_key,
        tuple(symbols),
        total_symbols,
        tuple(invalid),
        tuple(observer_failed),
        truncated,
        monotonic() - started,
    )


def breadcrumbs_for_position(
    result: SourceStructureResult,
    document_id: str,
    position: int,
) -> tuple[OutlineSymbol, ...]:
    """Return the root-to-leaf symbol chain containing a code-point offset."""

    if not isinstance(result, SourceStructureResult):
        raise TypeError("result must be a SourceStructureResult")
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("document ID must be non-empty text")
    if isinstance(position, bool) or not isinstance(position, int):
        raise TypeError("breadcrumb position must be an integer")
    if position < 0:
        raise ValueError("breadcrumb position must be non-negative")

    by_id = {
        symbol.node_id: symbol
        for symbol in result.symbols
        if symbol.document_id == document_id
    }
    containing = [
        symbol
        for symbol in by_id.values()
        if (
            symbol.start <= position < max(symbol.start + 1, symbol.end)
            or (
                symbol.kind == "Module"
                and position == symbol.end
            )
        )
    ]
    if not containing:
        return ()
    current = max(
        containing,
        key=lambda item: (
            item.depth,
            item.start,
            -(item.end - item.start),
        ),
    )
    chain: list[OutlineSymbol] = []
    seen: set[str] = set()
    while current.node_id not in seen:
        seen.add(current.node_id)
        chain.append(current)
        if current.parent_node_id is None:
            break
        parent = by_id.get(current.parent_node_id)
        if parent is None:
            break
        current = parent
    return tuple(reversed(chain))


def __getattr__(name: str):
    if name == "AsyncSourceStructureService":
        from .source_structure_async import AsyncSourceStructureService

        return AsyncSourceStructureService
    raise AttributeError(name)


__all__ = [
    "AsyncSourceStructureService",
    "MAX_OUTLINE_DEPTH",
    "MAX_OUTLINE_NAME_CHARS",
    "MAX_OUTLINE_SYMBOLS",
    "MAX_OUTLINE_TEXT_CHARS",
    "OutlineSymbol",
    "SourceStructureDocument",
    "SourceStructureResult",
    "breadcrumbs_for_position",
    "build_source_structure",
]
