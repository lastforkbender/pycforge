"""Professional source editor widgets for the PyQt5 workspace.

The module deliberately has no dependency on the conversion pipeline.  It is
safe to import in headless installations: the public Qt classes remain
available as fail-fast placeholders when the optional dependency is absent.
"""

from __future__ import annotations

from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, replace
from itertools import islice
from typing import Iterable, Sequence

from .editor_lexical import lexical_protected_spans
from .visual_tokens import PYCFORGE_COLORS


# Enter the plain-text large-file path before the active 1,000,000-byte /
# 100,000-line resource ceiling.  The character threshold is deliberately
# conservative: a valid UTF-8 code point may occupy four bytes.
LARGE_FILE_CHARACTER_THRESHOLD = 250_000
LARGE_FILE_LINE_THRESHOLD = 80_000
LARGE_FILE_MARKER_STORAGE_LIMIT = 2_048
LARGE_FILE_EXTRA_SELECTION_LIMIT = 192
LARGE_FILE_RAIL_MARKER_LIMIT = 384
BRACKET_SCAN_LIMIT = 4_096
LARGE_FILE_BRACKET_SCAN_LIMIT = 1_024


@dataclass(frozen=True, slots=True)
class EditorMarker:
    """A stable editor-position range displayed in the text and overview rail.

    Qt text cursors count UTF-16 code units.  Public widget callers therefore
    convert source code-point offsets with :func:`qt_position_length` first.
    """

    start: int
    end: int
    kind: str = "search"
    message: str = ""
    marker_id: str = ""

    def normalized(self, text_length: int) -> "EditorMarker":
        """Return this marker clipped to a document of *text_length* characters."""

        limit = max(0, int(text_length))
        start = min(limit, max(0, int(self.start)))
        end = min(limit, max(start, int(self.end)))
        return replace(self, start=start, end=end)


def large_file_mode_required(*, character_count: int, line_count: int) -> bool:
    """Return whether editor work must use the bounded plain-text path.

    Counts come from the Qt document's constant-time metadata in live widgets.
    Keeping this policy helper Qt-free also makes the safety boundary available
    to headless callers and tests.
    """

    characters = max(0, int(character_count))
    lines = max(0, int(line_count))
    return (
        characters >= LARGE_FILE_CHARACTER_THRESHOLD
        or lines >= LARGE_FILE_LINE_THRESHOLD
    )


def _projection_indices(size: int, limit: int) -> tuple[int, ...]:
    """Return deterministic, evenly distributed indexes with both endpoints."""

    if limit < 0:
        raise ValueError("marker projection limit must not be negative")
    if size <= 0 or limit == 0:
        return ()
    if size <= limit:
        return tuple(range(size))
    if limit == 1:
        return (0,)
    return tuple(
        (index * (size - 1)) // (limit - 1)
        for index in range(limit)
    )


def bounded_marker_projection(
    markers: Sequence[EditorMarker],
    *,
    limit: int,
    focus_start: int | None = None,
    focus_end: int | None = None,
) -> tuple[EditorMarker, ...]:
    """Project marker data to a deterministic hard limit.

    When a focus range is supplied, intersecting markers are preferred before
    an evenly distributed overview sample.  The helper never scans source
    characters and never returns more than ``limit`` records.
    """

    maximum = int(limit)
    if maximum < 0:
        raise ValueError("marker projection limit must not be negative")
    values = tuple(markers)
    if len(values) <= maximum:
        return values
    if maximum == 0:
        return ()

    focused_indexes: list[int] = []
    if focus_start is not None or focus_end is not None:
        start = max(0, int(focus_start or 0))
        end = max(start, int(focus_end if focus_end is not None else start))
        focused_indexes = [
            index
            for index, marker in enumerate(values)
            if marker.end >= start and marker.start <= end
        ]
        if len(focused_indexes) >= maximum:
            selected = _projection_indices(len(focused_indexes), maximum)
            return tuple(values[focused_indexes[index]] for index in selected)

    selected_indexes = list(focused_indexes)
    selected_set = set(selected_indexes)
    remaining = maximum - len(selected_indexes)
    if remaining:
        for index in _projection_indices(len(values), remaining):
            if index not in selected_set:
                selected_indexes.append(index)
                selected_set.add(index)
        if len(selected_indexes) < maximum:
            for index in range(len(values)):
                if index in selected_set:
                    continue
                selected_indexes.append(index)
                selected_set.add(index)
                if len(selected_indexes) == maximum:
                    break
    return tuple(values[index] for index in selected_indexes[:maximum])


def normalize_markers(
    ranges: Iterable[EditorMarker | Sequence[int]],
    *,
    text_length: int,
    kind: str,
    limit: int | None = None,
) -> tuple[EditorMarker, ...]:
    """Normalize public marker input without requiring a Qt installation."""

    maximum = None if limit is None else int(limit)
    if maximum is not None and maximum < 0:
        raise ValueError("marker projection limit must not be negative")
    if maximum == 0:
        return ()
    if maximum is not None and isinstance(ranges, SequenceABC):
        indexes = _projection_indices(len(ranges), maximum)
        source: Iterable[EditorMarker | Sequence[int]] = (
            ranges[index] for index in indexes
        )
    elif maximum is not None:
        source = islice(ranges, maximum)
    else:
        source = ranges

    normalized: list[EditorMarker] = []
    for item in source:
        if isinstance(item, EditorMarker):
            marker = item if item.kind else replace(item, kind=kind)
        else:
            values = tuple(item)
            if len(values) != 2:
                raise ValueError("editor ranges must contain exactly start and end")
            marker = EditorMarker(int(values[0]), int(values[1]), kind=kind)
        marker = marker.normalized(text_length)
        if marker.end > marker.start:
            normalized.append(marker)
    return tuple(normalized)


def qt_position_length(text: str) -> int:
    """Return the number of UTF-16 code units used by a Qt text cursor."""

    if not isinstance(text, str):
        raise TypeError("editor text must be a string")
    return len(text.encode("utf-16-le")) // 2


try:
    from PyQt5.QtCore import QRect, Qt, pyqtSignal
    from PyQt5.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QKeySequence,
        QLinearGradient,
        QPainter,
        QPen,
        QTextCharFormat,
        QTextCursor,
        QTextFormat,
    )
    from PyQt5.QtWidgets import QPlainTextEdit, QTextEdit
    from .editor_commands_qt import SourceCommandMixin
    from .editor_sidebars import _LineNumberArea, _QuantumRail
    from .editor_syntax import PyCForgeSyntaxHighlighter
except ImportError as exc:  # pragma: no cover - exercised in the headless build
    QT_AVAILABLE = False
    _QT_ERROR = exc
else:
    QT_AVAILABLE = True
    _QT_ERROR = None


if QT_AVAILABLE:
    # Accessibility contract implemented by editor_sidebars:
    # self.setObjectName("QuantumVisibilityRail")
    # self.setFocusPolicy(Qt.StrongFocus)
    # self.setAccessibleDescription(

    def _token_color(value: str, alpha: int | None = None) -> QColor:
        color = QColor(value)
        if alpha is not None:
            color.setAlpha(max(0, min(255, int(alpha))))
        return color


    class CodeEditor(SourceCommandMixin, QPlainTextEdit):
        """Source editor with syntax, line numbers, selection layers and minimap rail."""

        findRequested = pyqtSignal(bool)
        markerActivated = pyqtSignal(str, str, int)
        largeFileModeChanged = pyqtSignal(bool)

        _RAIL_COLORS = {
            "search": _token_color(PYCFORGE_COLORS.warning),
            "diagnostic": _token_color(PYCFORGE_COLORS.error),
            "warning": _token_color(PYCFORGE_COLORS.warm),
            "info": _token_color(PYCFORGE_COLORS.blue),
            "mapping": _token_color(PYCFORGE_COLORS.success),
        }

        def __init__(
            self,
            parent=None,
            *,
            language: str = "python",
            highlighting: bool = True,
        ) -> None:
            super().__init__(parent)
            self._line_area = _LineNumberArea(self)
            self._quantum_rail = _QuantumRail(self)
            self._highlighter = PyCForgeSyntaxHighlighter(self.document(), language)
            self._search_markers: tuple[EditorMarker, ...] = ()
            self._diagnostic_markers: tuple[EditorMarker, ...] = ()
            self._mapping_markers: tuple[EditorMarker, ...] = ()
            self._rail_marker_cache: tuple[EditorMarker, ...] = ()
            self._active_search_index = -1
            self._large_file_mode = False
            self._large_file_mode_requested = False
            self._initialize_source_commands(
                highlighting_enabled=highlighting
            )

            fixed = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            fixed.setStyleHint(QFont.Monospace)
            fixed.setPointSize(max(10, fixed.pointSize()))
            self.setFont(fixed)
            self.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
            self.setFrameStyle(0)
            self.setCenterOnScroll(True)
            self.setProperty("role", "code-editor")
            self.setAccessibleName("Source code editor")

            self.blockCountChanged.connect(self._update_viewport_margins)
            self.updateRequest.connect(self._update_side_areas)
            self.cursorPositionChanged.connect(self._refresh_extra_selections)
            self.textChanged.connect(self._document_changed)
            self.verticalScrollBar().valueChanged.connect(self._quantum_rail.update)
            self._update_viewport_margins()
            self._refresh_extra_selections()

        @property
        def language(self) -> str:
            return self._highlighter.language

        @property
        def large_file_mode(self) -> bool:
            """Whether bounded plain-text rendering is currently active."""

            return self._large_file_mode

        def set_large_file_mode(self, enabled: bool) -> None:
            """Request or release the editor's bounded large-file path.

            ``True`` explicitly enters large-file mode.  ``False`` releases
            that request, but threshold-sized documents remain protected by
            automatic detection; callers cannot accidentally re-enable a
            whole-document highlighter at the maximum-input envelope.
            """

            requested = bool(enabled)
            if requested == self._large_file_mode_requested:
                return
            self._large_file_mode_requested = requested
            if self._update_large_file_mode():
                self._refresh_extra_selections()
                self._quantum_rail.markers_changed()

        def set_language(self, language: str) -> None:
            self._highlighter.set_language(language)

        def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt API
            """Replace source text without first highlighting a huge document."""

            if isinstance(text, str):
                incoming_large = large_file_mode_required(
                    character_count=len(text),
                    line_count=text.count("\n") + 1,
                )
                if incoming_large or self._large_file_mode_requested:
                    self._apply_large_file_mode(True)
            super().setPlainText(text)

        def _document_text_length(self) -> int:
            """Return Qt's UTF-16 text length without copying the document."""

            return max(0, int(self.document().characterCount()) - 1)

        def _update_large_file_mode(self) -> bool:
            required = self._large_file_mode_requested or large_file_mode_required(
                character_count=self._document_text_length(),
                line_count=self.document().blockCount(),
            )
            return self._apply_large_file_mode(required)

        def _apply_large_file_mode(self, enabled: bool) -> bool:
            active = bool(enabled)
            if active == self._large_file_mode:
                return False
            self._large_file_mode = active
            if active:
                # Detaching the highlighter is the deterministic plain-text
                # fallback.  It prevents Qt from scheduling proportional
                # whole-document work after edits or language changes.
                self._highlighter.setDocument(None)
                self._cap_large_file_markers()
            else:
                self._highlighter.setDocument(self.document())
            self._rebuild_rail_marker_cache()
            self.largeFileModeChanged.emit(active)
            return True

        def line_number_area_width(self) -> int:
            digits = max(2, len(str(max(1, self.blockCount()))))
            return 14 + self.fontMetrics().horizontalAdvance("9") * digits

        def _update_viewport_margins(self, _count: int | None = None) -> None:
            self.setViewportMargins(
                self.line_number_area_width(), 0, self._quantum_rail.WIDTH, 0
            )

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            contents = self.contentsRect()
            left_width = self.line_number_area_width()
            self._line_area.setGeometry(
                QRect(contents.left(), contents.top(), left_width, contents.height())
            )
            self._quantum_rail.setGeometry(
                QRect(
                    contents.right() - self._quantum_rail.WIDTH + 1,
                    contents.top(),
                    self._quantum_rail.WIDTH,
                    contents.height(),
                )
            )

        def _update_side_areas(self, rect, dy: int) -> None:
            if dy:
                self._line_area.scroll(0, dy)
            else:
                self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
            if rect.contains(self.viewport().rect()):
                self._update_viewport_margins()
            self._quantum_rail.update()

        def paint_line_number_area(self, event) -> None:
            painter = QPainter(self._line_area)
            gradient = QLinearGradient(0, 0, self._line_area.width(), 0)
            gradient.setColorAt(
                0.0, _token_color(PYCFORGE_COLORS.void)
            )
            gradient.setColorAt(
                1.0, _token_color(PYCFORGE_COLORS.surface_raised)
            )
            painter.fillRect(event.rect(), gradient)
            painter.setPen(_token_color(PYCFORGE_COLORS.border))
            painter.drawLine(
                self._line_area.width() - 1,
                event.rect().top(),
                self._line_area.width() - 1,
                event.rect().bottom(),
            )
            block = self.firstVisibleBlock()
            number = block.blockNumber()
            top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
            bottom = top + round(self.blockBoundingRect(block).height())
            current = self.textCursor().blockNumber()
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    painter.setPen(
                        _token_color(PYCFORGE_COLORS.blue_bright)
                        if number == current
                        else _token_color(PYCFORGE_COLORS.text_disabled)
                    )
                    painter.drawText(
                        0,
                        top,
                        self._line_area.width() - 8,
                        self.fontMetrics().height(),
                        Qt.AlignRight,
                        str(number + 1),
                    )
                block = block.next()
                top = bottom
                bottom = top + round(self.blockBoundingRect(block).height())
                number += 1

        def go_to_line_at_y(self, y: int) -> None:
            cursor = self.cursorForPosition(self.viewport().rect().topLeft())
            block = self.firstVisibleBlock()
            while block.isValid():
                top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
                bottom = top + self.blockBoundingRect(block).height()
                if top <= y < bottom:
                    cursor.setPosition(block.position())
                    self.setTextCursor(cursor)
                    self.setFocus()
                    return
                block = block.next()

        def _document_changed(self) -> None:
            self._reset_source_command_state()
            self._update_large_file_mode()
            text_length = self._document_text_length()
            active_marker = self._active_search_marker()
            self._search_markers = tuple(
                marker for marker in (m.normalized(text_length) for m in self._search_markers)
                if marker.end > marker.start
            )
            if active_marker is not None:
                active_marker = active_marker.normalized(text_length)
                if active_marker.end <= active_marker.start:
                    active_marker = None
            # Diagnostics and source mappings describe a particular conversion
            # snapshot.  An edit invalidates them instead of leaving a plausible
            # but incorrect underline attached to shifted text.
            self._diagnostic_markers = ()
            self._mapping_markers = ()
            self._search_markers = self._bounded_search_markers(
                self._search_markers,
                active_marker,
            )
            self._rebuild_rail_marker_cache()
            self._refresh_extra_selections()
            self._quantum_rail.markers_changed()

        def set_search_ranges(
            self,
            ranges: Iterable[EditorMarker | Sequence[int]],
            active_index: int = -1,
        ) -> None:
            active_input = None
            if (
                isinstance(ranges, SequenceABC)
                and 0 <= active_index < len(ranges)
            ):
                active_input = ranges[active_index]
            self._search_markers = normalize_markers(
                ranges,
                text_length=self._document_text_length(),
                kind="search",
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
            )
            active_marker = None
            if active_input is not None:
                active_values = normalize_markers(
                    (active_input,),
                    text_length=self._document_text_length(),
                    kind="search",
                )
                if active_values:
                    active_marker = active_values[0]
            elif 0 <= active_index < len(self._search_markers):
                active_marker = self._search_markers[active_index]
            self._search_markers = self._bounded_search_markers(
                self._search_markers,
                active_marker,
            )
            self._rebuild_rail_marker_cache()
            self._refresh_extra_selections()
            self._quantum_rail.markers_changed()

        def set_diagnostic_ranges(
            self, ranges: Iterable[EditorMarker | Sequence[int]]
        ) -> None:
            self._diagnostic_markers = normalize_markers(
                ranges,
                text_length=self._document_text_length(),
                kind="diagnostic",
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
            )
            self._rebuild_rail_marker_cache()
            self._refresh_extra_selections()
            self._quantum_rail.markers_changed()

        def set_mapping_ranges(
            self, ranges: Iterable[EditorMarker | Sequence[int]]
        ) -> None:
            self._mapping_markers = normalize_markers(
                ranges,
                text_length=self._document_text_length(),
                kind="mapping",
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
            )
            self._rebuild_rail_marker_cache()
            self._refresh_extra_selections()
            self._quantum_rail.markers_changed()

        def clear_markers(self) -> None:
            self._search_markers = ()
            self._diagnostic_markers = ()
            self._mapping_markers = ()
            self._active_search_index = -1
            self._rebuild_rail_marker_cache()
            self._refresh_extra_selections()
            self._quantum_rail.markers_changed()

        def markers(self, kind: str | None = None) -> tuple[EditorMarker, ...]:
            values = self._search_markers + self._diagnostic_markers + self._mapping_markers
            if kind is None:
                return values
            return tuple(marker for marker in values if marker.kind == kind)

        def _active_search_marker(self) -> EditorMarker | None:
            if 0 <= self._active_search_index < len(self._search_markers):
                return self._search_markers[self._active_search_index]
            return None

        def _bounded_search_markers(
            self,
            markers: Sequence[EditorMarker],
            active_marker: EditorMarker | None,
        ) -> tuple[EditorMarker, ...]:
            projected = bounded_marker_projection(
                markers,
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
                focus_start=active_marker.start if active_marker is not None else None,
                focus_end=active_marker.end if active_marker is not None else None,
            )
            if active_marker is not None and active_marker not in projected:
                projected = (
                    projected[:-1] + (active_marker,)
                    if len(projected) >= LARGE_FILE_MARKER_STORAGE_LIMIT
                    else projected + (active_marker,)
                )
            self._active_search_index = (
                projected.index(active_marker)
                if active_marker in projected
                else -1
            )
            return projected

        def _cap_large_file_markers(self) -> None:
            active_marker = self._active_search_marker()
            self._search_markers = self._bounded_search_markers(
                self._search_markers,
                active_marker,
            )
            self._diagnostic_markers = bounded_marker_projection(
                self._diagnostic_markers,
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
            )
            self._mapping_markers = bounded_marker_projection(
                self._mapping_markers,
                limit=LARGE_FILE_MARKER_STORAGE_LIMIT,
            )

        def _rebuild_rail_marker_cache(self) -> None:
            markers = self.markers()
            if len(markers) <= LARGE_FILE_RAIL_MARKER_LIMIT:
                self._rail_marker_cache = markers
                return
            per_layer = max(1, LARGE_FILE_RAIL_MARKER_LIMIT // 3)
            active_marker = self._active_search_marker()
            search = bounded_marker_projection(
                self._search_markers,
                limit=per_layer,
                focus_start=active_marker.start if active_marker is not None else None,
                focus_end=active_marker.end if active_marker is not None else None,
            )
            diagnostics = bounded_marker_projection(
                self._diagnostic_markers,
                limit=per_layer,
            )
            mappings = bounded_marker_projection(
                self._mapping_markers,
                limit=per_layer,
            )
            self._rail_marker_cache = search + diagnostics + mappings

        def _rail_markers(self) -> tuple[EditorMarker, ...]:
            """Return the bounded projection used by rail paint/navigation."""

            return self._rail_marker_cache

        def _selection(self, marker: EditorMarker, char_format: QTextCharFormat):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.document())
            selection.cursor.setPosition(marker.start)
            selection.cursor.setPosition(marker.end, QTextCursor.KeepAnchor)
            selection.format = char_format
            return selection

        def _viewport_projection_bounds(self) -> tuple[int, int]:
            """Return the visible block range plus a small deterministic margin."""

            first = self.firstVisibleBlock()
            last = self.cursorForPosition(self.viewport().rect().bottomRight()).block()
            if not first.isValid() or not last.isValid():
                position = self.textCursor().position()
                return position, position
            for _ in range(24):
                previous = first.previous()
                if not previous.isValid():
                    break
                first = previous
            for _ in range(24):
                following = last.next()
                if not following.isValid():
                    break
                last = following
            return (
                max(0, first.position()),
                min(
                    self._document_text_length(),
                    last.position() + max(0, last.length()),
                ),
            )

        def _extra_marker_projection(
            self,
            markers: Sequence[EditorMarker],
            *,
            limit: int,
            include: EditorMarker | None = None,
        ) -> tuple[EditorMarker, ...]:
            if len(markers) <= limit:
                return tuple(markers)
            start, end = self._viewport_projection_bounds()
            projected = bounded_marker_projection(
                markers,
                limit=limit,
                focus_start=start,
                focus_end=end,
            )
            if include is not None and include not in projected:
                projected = (
                    projected[:-1] + (include,)
                    if len(projected) >= limit
                    else projected + (include,)
                )
            return projected

        def _refresh_extra_selections(self) -> None:
            selections = []
            current = QTextEdit.ExtraSelection()
            current.format.setBackground(
                _token_color(PYCFORGE_COLORS.selection, 150)
            )
            current.format.setProperty(QTextFormat.FullWidthSelection, True)
            current.cursor = self.textCursor()
            current.cursor.clearSelection()
            selections.append(current)

            bracket_positions = self._bracket_positions()
            for position in bracket_positions:
                bracket = QTextEdit.ExtraSelection()
                bracket.cursor = QTextCursor(self.document())
                bracket.cursor.setPosition(position)
                bracket.cursor.setPosition(position + 1, QTextCursor.KeepAnchor)
                bracket.format.setBackground(
                    _token_color(
                        PYCFORGE_COLORS.violet_dim
                        if len(bracket_positions) == 2
                        else PYCFORGE_COLORS.error_dim
                    )
                )
                bracket.format.setForeground(
                    _token_color(PYCFORGE_COLORS.text)
                )
                selections.append(bracket)

            per_layer = max(1, LARGE_FILE_EXTRA_SELECTION_LIMIT // 3)
            active_marker = self._active_search_marker()
            search_markers = self._extra_marker_projection(
                self._search_markers,
                limit=per_layer,
                include=active_marker,
            )
            mapping_markers = self._extra_marker_projection(
                self._mapping_markers,
                limit=per_layer,
            )
            diagnostic_markers = self._extra_marker_projection(
                self._diagnostic_markers,
                limit=per_layer,
            )
            for marker in search_markers:
                char_format = QTextCharFormat()
                char_format.setBackground(
                    _token_color(
                        PYCFORGE_COLORS.warning,
                        190 if marker == active_marker else 90,
                    )
                )
                char_format.setForeground(
                    _token_color(PYCFORGE_COLORS.text)
                )
                selections.append(self._selection(marker, char_format))
            for marker in mapping_markers:
                char_format = QTextCharFormat()
                char_format.setBackground(
                    _token_color(PYCFORGE_COLORS.success, 38)
                )
                char_format.setUnderlineColor(
                    _token_color(PYCFORGE_COLORS.success)
                )
                char_format.setUnderlineStyle(QTextCharFormat.SingleUnderline)
                selections.append(self._selection(marker, char_format))
            for marker in diagnostic_markers:
                char_format = QTextCharFormat()
                color = self._RAIL_COLORS.get(marker.kind, self._RAIL_COLORS["diagnostic"])
                char_format.setUnderlineColor(color)
                char_format.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                selections.append(self._selection(marker, char_format))
            self.setExtraSelections(selections)

        def _bracket_positions(self) -> tuple[int, ...]:
            """Return the bracket at the caret and its deterministic partner."""

            pairs = {"(": ")", "[": "]", "{": "}"}
            reverse = {value: key for key, value in pairs.items()}
            limit = max(0, self.document().characterCount() - 1)
            cursor_position = min(limit, self.textCursor().position())

            def character(position: int) -> str:
                if 0 <= position < limit:
                    return str(self.document().characterAt(position))
                return ""

            at_cursor = character(cursor_position)
            before_cursor = character(cursor_position - 1)
            if at_cursor in pairs or at_cursor in reverse:
                origin = cursor_position
                token = at_cursor
            elif before_cursor in pairs or before_cursor in reverse:
                origin = cursor_position - 1
                token = before_cursor
            else:
                return ()

            if token in pairs:
                opener, closer, direction = token, pairs[token], 1
            else:
                opener, closer, direction = reverse[token], token, -1
            depth = 1
            position = origin + direction
            scan_limit = (
                LARGE_FILE_BRACKET_SCAN_LIMIT
                if self._large_file_mode
                else BRACKET_SCAN_LIMIT
            )
            scanned = 0
            while 0 <= position < limit and scanned < scan_limit:
                candidate = character(position)
                if candidate == (opener if direction > 0 else closer):
                    depth += 1
                elif candidate == (closer if direction > 0 else opener):
                    depth -= 1
                    if depth == 0:
                        return (origin, position)
                position += direction
                scanned += 1
            return (origin,)

        def _marker_rail_y(self, marker: EditorMarker) -> int:
            block_count = max(1, self.document().blockCount())
            block = self.document().findBlock(marker.start).blockNumber()
            usable = max(1, self._quantum_rail.height() - 4)
            return 2 + round((block / max(1, block_count - 1)) * usable)

        def paint_quantum_rail(self, event) -> None:
            painter = QPainter(self._quantum_rail)
            gradient = QLinearGradient(0, 0, self._quantum_rail.width(), 0)
            gradient.setColorAt(
                0.0, _token_color(PYCFORGE_COLORS.surface)
            )
            gradient.setColorAt(
                0.55, _token_color(PYCFORGE_COLORS.surface_active)
            )
            gradient.setColorAt(
                1.0, _token_color(PYCFORGE_COLORS.void)
            )
            painter.fillRect(event.rect(), gradient)
            painter.setPen(
                QPen(
                    _token_color(PYCFORGE_COLORS.border_strong, 100),
                    1,
                )
            )
            painter.drawLine(1, event.rect().top(), 1, event.rect().bottom())

            selected_marker = self._quantum_rail.selected_marker()
            for marker in self._rail_markers():
                color = self._RAIL_COLORS.get(marker.kind, self._RAIL_COLORS["diagnostic"])
                painter.setPen(QPen(color, 4 if marker is selected_marker else 2))
                y = self._marker_rail_y(marker)
                inset = 2 if marker is selected_marker else 4
                painter.drawLine(inset, y, self._quantum_rail.width() - inset, y)

            bar = self.verticalScrollBar()
            total = max(1, bar.maximum() + bar.pageStep())
            height = max(10, round(self._quantum_rail.height() * bar.pageStep() / total))
            travel = max(0, self._quantum_rail.height() - height)
            top = 0 if bar.maximum() == 0 else round(travel * bar.value() / bar.maximum())
            painter.setPen(
                QPen(_token_color(PYCFORGE_COLORS.blue_bright), 1)
            )
            painter.setBrush(
                _token_color(PYCFORGE_COLORS.blue, 40)
            )
            painter.drawRoundedRect(2, top, self._quantum_rail.width() - 5, height, 2, 2)
            if self._quantum_rail.hasFocus():
                painter.setBrush(Qt.NoBrush)
                painter.setPen(
                    QPen(
                        _token_color(PYCFORGE_COLORS.focus_ring),
                        1,
                        Qt.DotLine,
                    )
                )
                painter.drawRect(self._quantum_rail.rect().adjusted(0, 0, -1, -1))

        def marker_near_rail_position(self, y: int) -> EditorMarker | None:
            candidates = sorted(
                (
                    (abs(self._marker_rail_y(marker) - y), marker)
                    for marker in self._rail_markers()
                ),
                key=lambda item: (item[0], item[1].start, item[1].kind),
            )
            if candidates and candidates[0][0] <= 5:
                return candidates[0][1]
            return None

        def activate_rail_position(self, y: int) -> None:
            marker = self.marker_near_rail_position(y)
            if marker is not None:
                self.activate_rail_marker(marker)
                return
            height = max(1, self._quantum_rail.height() - 1)
            bar = self.verticalScrollBar()
            bar.setValue(round(bar.maximum() * min(height, max(0, y)) / height))

        def activate_rail_marker(
            self,
            marker: EditorMarker,
            *,
            focus: bool = True,
        ) -> None:
            """Navigate to *marker* and publish the same event as pointer activation."""

            self.go_to_position(marker.start, marker.end, focus=focus)
            self.markerActivated.emit(marker.kind, marker.marker_id, marker.start)

        def go_to_position(
            self,
            start: int,
            end: int | None = None,
            *,
            focus: bool = True,
        ) -> None:
            limit = self._document_text_length()
            cursor = QTextCursor(self.document())
            cursor.setPosition(min(limit, max(0, int(start))))
            if end is not None:
                cursor.setPosition(min(limit, max(cursor.position(), int(end))), QTextCursor.KeepAnchor)
            self.setTextCursor(cursor)
            self.centerCursor()
            if focus:
                self.setFocus()

        def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
            if event.matches(QKeySequence.Find):
                self.findRequested.emit(False)
                event.accept()
                return
            if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_H:
                self.findRequested.emit(True)
                event.accept()
                return
            super().keyPressEvent(event)


else:
    class _QtRequired:
        """Headless placeholder retaining a predictable public API."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PyQt5 is required for editor widgets") from _QT_ERROR


    class PyCForgeSyntaxHighlighter(_QtRequired):
        pass


    class CodeEditor(_QtRequired):
        pass


__all__ = [
    "BRACKET_SCAN_LIMIT",
    "CodeEditor",
    "EditorMarker",
    "LARGE_FILE_BRACKET_SCAN_LIMIT",
    "LARGE_FILE_CHARACTER_THRESHOLD",
    "LARGE_FILE_EXTRA_SELECTION_LIMIT",
    "LARGE_FILE_LINE_THRESHOLD",
    "LARGE_FILE_MARKER_STORAGE_LIMIT",
    "LARGE_FILE_RAIL_MARKER_LIMIT",
    "QT_AVAILABLE",
    "PyCForgeSyntaxHighlighter",
    "bounded_marker_projection",
    "large_file_mode_required",
    "lexical_protected_spans",
    "normalize_markers",
    "qt_position_length",
]
