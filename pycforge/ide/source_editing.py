"""Pure, immutable Python source-editing operations for the workspace.

The functions in this module know nothing about Qt, files, or conversion.
They accept one exact text value and an ordered selection, and return a new
text value with the exact selection to install in an editor.  Line endings are
preserved; a newly required line ending follows the surrounding document and
defaults to LF for an empty single-line document.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass


INDENT_WIDTH = 4


@dataclass(frozen=True, slots=True)
class SourceEditResult:
    """One complete immutable result of a source-editing operation."""

    text: str
    selection_start: int
    selection_end: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("edited source must be text")
        for name, value in (
            ("selection_start", self.selection_start),
            ("selection_end", self.selection_end),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not (
            0 <= self.selection_start <= self.selection_end <= len(self.text)
        ):
            raise ValueError("edited source selection is outside the text")

    @property
    def selection(self) -> tuple[int, int]:
        return self.selection_start, self.selection_end


@dataclass(frozen=True, slots=True)
class _Line:
    start: int
    content: str
    newline: str

    @property
    def content_end(self) -> int:
        return self.start + len(self.content)

    @property
    def end(self) -> int:
        return self.content_end + len(self.newline)


def _selection(text: str, start: int, end: int) -> tuple[int, int]:
    if not isinstance(text, str):
        raise TypeError("source must be text")
    for name, value in (("selection start", start), ("selection end", end)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
    limit = len(text)
    first = min(limit, max(0, start))
    last = min(limit, max(0, end))
    return (first, last) if first <= last else (last, first)


def _lines(text: str) -> tuple[_Line, ...]:
    records: list[_Line] = []
    start = 0
    while True:
        newline_at = text.find("\n", start)
        if newline_at < 0:
            records.append(_Line(start, text[start:], ""))
            break
        content_end = (
            newline_at - 1
            if newline_at > start and text[newline_at - 1] == "\r"
            else newline_at
        )
        records.append(
            _Line(
                start,
                text[start:content_end],
                text[content_end : newline_at + 1],
            )
        )
        start = newline_at + 1
        if start == len(text):
            records.append(_Line(start, "", ""))
            break
    return tuple(records)


def _line_index(records: tuple[_Line, ...], offset: int) -> int:
    starts = tuple(line.start for line in records)
    return max(0, min(len(records) - 1, bisect_right(starts, offset) - 1))


def _selected_line_indexes(
    records: tuple[_Line, ...],
    start: int,
    end: int,
) -> tuple[int, int]:
    first = _line_index(records, start)
    if end > start and end == records[_line_index(records, end)].start:
        last = max(first, _line_index(records, end) - 1)
    else:
        last = _line_index(records, end)
    return first, max(first, last)


def _render(
    contents: tuple[str, ...],
    records: tuple[_Line, ...],
) -> str:
    return "".join(
        content + record.newline
        for content, record in zip(contents, records, strict=True)
    )


def _preferred_newline(text: str, offset: int) -> str:
    before = text.rfind("\n", 0, offset)
    if before >= 0:
        return "\r\n" if before > 0 and text[before - 1] == "\r" else "\n"
    after = text.find("\n", offset)
    if after >= 0:
        return "\r\n" if after > 0 and text[after - 1] == "\r" else "\n"
    return "\n"


def _map_point(
    old_records: tuple[_Line, ...],
    new_records: tuple[_Line, ...],
    offset: int,
    column_mapper,
) -> int:
    index = _line_index(old_records, offset)
    column = offset - old_records[index].start
    mapped = column_mapper(index, column)
    new_line = new_records[index]
    return new_line.start + min(
        len(new_line.content) + len(new_line.newline),
        max(0, mapped),
    )


def duplicate_lines(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Duplicate every line touched by the selection.

    A non-empty selection is recreated over the duplicate.  An empty selection
    places the caret at the same column in the duplicated line.  If the
    duplicated block has no terminal newline, one matching the surrounding
    document is inserted between the original and duplicate.
    """

    start, end = _selection(text, selection_start, selection_end)
    records = _lines(text)
    first, last = _selected_line_indexes(records, start, end)
    block_start = records[first].start
    block_end = records[last].end
    block = text[block_start:block_end]
    if records[last].newline:
        insertion = block
        duplicate_start = block_end
    else:
        separator = _preferred_newline(text, block_end)
        insertion = separator + block
        duplicate_start = block_end + len(separator)
    edited = text[:block_end] + insertion + text[block_end:]
    shift = duplicate_start - block_start
    return SourceEditResult(edited, start + shift, end + shift)


def _move_lines(
    text: str,
    selection_start: int,
    selection_end: int,
    *,
    direction: int,
) -> SourceEditResult:
    start, end = _selection(text, selection_start, selection_end)
    records = _lines(text)
    first, last = _selected_line_indexes(records, start, end)
    if direction < 0 and first == 0:
        return SourceEditResult(text, start, end)
    if direction > 0 and last >= len(records) - 1:
        return SourceEditResult(text, start, end)

    contents = [line.content for line in records]
    count = last - first + 1
    if direction < 0:
        moved = contents[first : last + 1]
        previous = contents[first - 1]
        contents[first - 1 : last + 1] = [*moved, previous]
        new_first = first - 1
    else:
        moved = contents[first : last + 1]
        following = contents[last + 1]
        contents[first : last + 2] = [following, *moved]
        new_first = first + 1

    edited = _render(tuple(contents), records)
    new_records = _lines(edited)
    old_block_start = records[first].start
    old_block_end = records[last].end
    new_block_start = new_records[new_first].start
    new_block_end = new_records[new_first + count - 1].end
    relative_start = start - old_block_start
    relative_end = end - old_block_start
    new_block_length = new_block_end - new_block_start
    return SourceEditResult(
        edited,
        new_block_start + min(new_block_length, relative_start),
        new_block_start + min(new_block_length, relative_end),
    )


def move_lines_up(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Move the selected logical lines one position earlier."""

    return _move_lines(
        text,
        selection_start,
        selection_end,
        direction=-1,
    )


def move_lines_down(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Move the selected logical lines one position later."""

    return _move_lines(
        text,
        selection_start,
        selection_end,
        direction=1,
    )


def _rewrite_selected_lines(
    text: str,
    selection_start: int,
    selection_end: int,
    rewrite,
) -> SourceEditResult:
    start, end = _selection(text, selection_start, selection_end)
    old_records = _lines(text)
    first, last = _selected_line_indexes(old_records, start, end)
    contents = [line.content for line in old_records]
    mappers = [lambda column: column for _line in old_records]
    for index in range(first, last + 1):
        contents[index], mappers[index] = rewrite(contents[index])
    edited = _render(tuple(contents), old_records)
    new_records = _lines(edited)
    return SourceEditResult(
        edited,
        _map_point(
            old_records,
            new_records,
            start,
            lambda index, column: mappers[index](column),
        ),
        _map_point(
            old_records,
            new_records,
            end,
            lambda index, column: mappers[index](column),
        ),
    )


def indent_lines(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Indent selected source by four spaces.

    Blank lines inside a multi-line selection remain blank.  An empty
    selection on a blank line inserts one indentation unit at the caret.
    """

    prefix = " " * INDENT_WIDTH
    start, end = _selection(text, selection_start, selection_end)
    indent_empty_caret_line = start == end

    def rewrite(content: str):
        if not content and not indent_empty_caret_line:
            return content, lambda column: column
        return prefix + content, lambda column: column + INDENT_WIDTH

    return _rewrite_selected_lines(
        text,
        start,
        end,
        rewrite,
    )


def outdent_lines(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Remove one leading tab or up to four leading spaces per selected line."""

    def rewrite(content: str):
        if content.startswith("\t"):
            removed = 1
        else:
            removed = min(
                INDENT_WIDTH,
                len(content) - len(content.lstrip(" ")),
            )
        if not removed:
            return content, lambda column: column

        def map_column(column: int) -> int:
            return max(0, column - removed)

        return content[removed:], map_column

    return _rewrite_selected_lines(
        text,
        selection_start,
        selection_end,
        rewrite,
    )


def toggle_python_line_comment(
    text: str,
    selection_start: int,
    selection_end: int,
) -> SourceEditResult:
    """Comment or uncomment every non-blank selected Python line."""

    start, end = _selection(text, selection_start, selection_end)
    records = _lines(text)
    first, last = _selected_line_indexes(records, start, end)
    selected = records[first : last + 1]
    nonblank = tuple(line for line in selected if line.content.strip())
    uncomment = bool(nonblank) and all(
        line.content[len(line.content) - len(line.content.lstrip()) :].startswith(
            "#"
        )
        for line in nonblank
    )

    def rewrite(content: str):
        if not content.strip():
            return content, lambda column: column
        indent = len(content) - len(content.lstrip())
        if uncomment:
            removed = 2 if content[indent:].startswith("# ") else 1

            def map_column(column: int) -> int:
                if column <= indent:
                    return column
                return indent + max(0, column - indent - removed)

            return content[:indent] + content[indent + removed :], map_column

        def map_column(column: int) -> int:
            return column if column < indent else column + 2

        return content[:indent] + "# " + content[indent:], map_column

    return _rewrite_selected_lines(text, start, end, rewrite)


def clamped_go_to_line_offset(text: str, line: int) -> int:
    """Return the start offset of a one-based line, clamped to the document."""

    if not isinstance(text, str):
        raise TypeError("source must be text")
    if isinstance(line, bool) or not isinstance(line, int):
        raise TypeError("line must be an integer")
    records = _lines(text)
    index = min(len(records) - 1, max(0, line - 1))
    return records[index].start


go_to_line_offset = clamped_go_to_line_offset


__all__ = [
    "INDENT_WIDTH",
    "SourceEditResult",
    "clamped_go_to_line_offset",
    "duplicate_lines",
    "go_to_line_offset",
    "indent_lines",
    "move_lines_down",
    "move_lines_up",
    "outdent_lines",
    "toggle_python_line_comment",
]
