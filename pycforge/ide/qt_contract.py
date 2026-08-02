"""Headless-safe value and position contracts shared by the Qt workspace.

This module deliberately contains no direct PyQt imports.  Keeping the
bounded settings readers' constants and source-position translations here
lets the desktop modules remain cohesive without weakening defensive
``pycforge.ide.qt`` import safety if an installation is damaged.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Any

from .editor import qt_position_length
from .positions import TextPositionIndex


SETTINGS_SCHEMA_VERSION = 1
MAX_SETTINGS_BLOB_BYTES = 1_048_576
MAX_SETTINGS_PATH_CHARS = 4096
MAX_RECENT_PATHS = 10
SETTINGS_ORGANIZATION = "PyCForge"
SETTINGS_APPLICATION = "PyCForge"
PRESENTATION_SETTING_KEYS = (
    "window/geometry",
    "window/state",
    "splitter/workspace",
    "splitter/editors",
    "splitter/main",
    "splitter/source",
    "view/bundle",
    "view/generated_c",
    "view/details",
    "view/source_split",
    "view/whitespace",
    "workspace/last_directory",
    "workspace/recent_paths",
)


def coerce_settings_schema_version(value: Any) -> int | None:
    """Return a bounded decimal settings version or ``None``."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if (
        isinstance(value, str)
        and len(value) <= 16
        and value.isascii()
        and value.isdigit()
    ):
        return int(value)
    return None


def line_column_offset(
    text: str,
    line: int,
    column: int,
    index: TextPositionIndex | None = None,
) -> int:
    """Translate a one-based line and zero-based column to a character offset."""

    if index is not None and index.text_length == len(text):
        return index.character_offset(line, column)
    if not isinstance(line, int) or not isinstance(column, int):
        return 0
    if line < 1:
        return 0
    lines = text.splitlines(keepends=True)
    if not lines:
        return 0
    if line > len(lines):
        return len(text)
    prefix = sum(len(value) for value in lines[: line - 1])
    return min(len(text), prefix + min(max(0, column), len(lines[line - 1])))


def diagnostic_character_range(
    diagnostic: dict[str, Any],
    text: str,
    index: TextPositionIndex | None = None,
) -> tuple[int, int]:
    """Return a clipped character range for a serialized diagnostic."""

    span = diagnostic.get("source_span") or {}
    start_data = span.get("start") or {}
    end_data = span.get("end") or {}
    start = start_data.get("offset")
    end = end_data.get("offset")
    if not isinstance(start, int):
        start = line_column_offset(
            text,
            start_data.get("line", 1),
            start_data.get("column", 0),
            index,
        )
    if not isinstance(end, int):
        end = line_column_offset(
            text,
            end_data.get("line", start_data.get("line", 1)),
            end_data.get("column", start_data.get("column", 0) + 1),
            index,
        )
    start = min(len(text), max(0, start))
    end = min(len(text), max(start, end))
    if end == start and start < len(text):
        end += 1
    return start, end


def mapping_character_range(
    mapping: dict[str, Any],
    text: str,
    index: TextPositionIndex | None = None,
) -> tuple[int, int]:
    """Return a renderer mapping range without confusing UTF-8 bytes and chars."""

    start = line_column_offset(
        text,
        mapping.get("start_line", 1),
        mapping.get("start_column", 0),
        index,
    )
    end = line_column_offset(
        text,
        mapping.get("end_line", mapping.get("start_line", 1)),
        mapping.get("end_column", mapping.get("start_column", 0)),
        index,
    )
    if end == start and start < len(text):
        end += 1
    return start, end


def python_offset_to_qt_position(
    text: str,
    offset: int,
    index: TextPositionIndex | None = None,
) -> int:
    """Convert a Python code-point offset to a Qt UTF-16 cursor position."""

    if not isinstance(offset, int):
        raise TypeError("source offset must be an integer")
    clipped = min(len(text), max(0, offset))
    if index is not None and index.text_length == len(text):
        return index.qt_position(text, clipped)
    return qt_position_length(text[:clipped])


def qt_position_to_python_offset(
    text: str,
    position: int,
    index: TextPositionIndex | None = None,
) -> int:
    """Convert a clamped Qt UTF-16 position to a Python code-point offset."""

    if not isinstance(position, int):
        raise TypeError("Qt source position must be an integer")
    target = max(0, position)
    if index is not None and index.text_length == len(text):
        if index.utf16_compatible:
            return min(len(text), target)
        line_number = max(
            0, bisect_right(index.utf16_line_starts, target) - 1
        )
        start = index.line_starts[line_number]
        end = (
            index.line_starts[line_number + 1]
            if line_number + 1 < index.line_count
            else len(text)
        )
        target -= index.utf16_line_starts[line_number]
    else:
        start, end = 0, len(text)
    units = 0
    offset = start
    for character in text[start:end]:
        width = 2 if ord(character) > 0xFFFF else 1
        if units + width > target:
            break
        units += width
        offset += 1
        if units == target:
            break
    return offset


def qt_range(
    text: str,
    start: int,
    end: int,
    index: TextPositionIndex | None = None,
) -> tuple[int, int]:
    if index is not None and index.text_length == len(text):
        return index.qt_range(text, start, end)
    return (
        python_offset_to_qt_position(text, start, index),
        python_offset_to_qt_position(text, end, index),
    )


__all__ = [
    "MAX_RECENT_PATHS",
    "MAX_SETTINGS_BLOB_BYTES",
    "MAX_SETTINGS_PATH_CHARS",
    "PRESENTATION_SETTING_KEYS",
    "SETTINGS_APPLICATION",
    "SETTINGS_ORGANIZATION",
    "SETTINGS_SCHEMA_VERSION",
    "coerce_settings_schema_version",
    "diagnostic_character_range",
    "line_column_offset",
    "mapping_character_range",
    "python_offset_to_qt_position",
    "qt_position_to_python_offset",
    "qt_range",
]
