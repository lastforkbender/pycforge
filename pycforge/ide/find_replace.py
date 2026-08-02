"""Keyboard-oriented find and replace controls for :mod:`pycforge.ide.editor`."""

from __future__ import annotations

import re
from typing import Any
from weakref import finalize

from .editor import CodeEditor, EditorMarker
from .search_service import (
    AsyncLiteralSearchService,
    DEFAULT_MATCH_LIMIT,
    LiteralSearchResult,
)
from .theme import pycforge_icon_path


def find_literal_ranges(
    text: str,
    query: str,
    *,
    match_case: bool = False,
    whole_word: bool = False,
) -> tuple[tuple[int, int], ...]:
    """Return deterministic, non-overlapping literal matches.

    This pure helper is also the headless reference for the widget's search
    semantics.  ``whole_word`` follows source-identifier boundaries: letters,
    digits and underscores are word characters.
    """

    if not query:
        return ()
    expression = re.escape(query)
    if whole_word:
        expression = rf"(?<!\w){expression}(?!\w)"
    flags = 0 if match_case else re.IGNORECASE
    return tuple(match.span() for match in re.finditer(expression, text, flags))


try:
    from PyQt5.QtCore import QEvent, QTimer, Qt, pyqtSignal
    from PyQt5.QtGui import QIcon, QTextCursor
    from PyQt5.QtWidgets import (
        QCheckBox,
        QGridLayout,
        QLabel,
        QLineEdit,
        QSizePolicy,
        QToolButton,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised in the headless build
    QT_AVAILABLE = False
    _QT_ERROR = exc
else:
    QT_AVAILABLE = True
    _QT_ERROR = None


if QT_AVAILABLE:
    class FindReplaceBar(QWidget):
        """A compact find/replace bar attachable to any :class:`CodeEditor`."""

        closed = pyqtSignal()
        matchActivated = pyqtSignal(int, int, int)
        replacementsMade = pyqtSignal(int)
        _searchCompleted = pyqtSignal(object)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._editor: CodeEditor | None = None
            self._matches: tuple[tuple[int, int], ...] = ()
            self._match_total = 0
            self._matches_truncated = False
            self._markers_published = False
            self._active_index = -1
            self._replace_visible = False
            self._search_active = False
            self._search_pending = False
            self._search_generation = 0
            self._action_registry: Any | None = None
            self._search_service = AsyncLiteralSearchService(
                match_limit=DEFAULT_MATCH_LIMIT
            )
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.setInterval(150)
            self.setObjectName("findReplaceBar")
            self.setProperty("role", "find-bar")
            self.setAccessibleName("Find and replace")
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            self.find_edit = QLineEdit(self)
            self.find_edit.setPlaceholderText("Find in source")
            self.find_edit.setClearButtonEnabled(True)
            self.find_edit.setAccessibleName("Find text")
            self.find_edit.installEventFilter(self)
            self.replace_edit = QLineEdit(self)
            self.replace_edit.setPlaceholderText("Replace with")
            self.replace_edit.setClearButtonEnabled(True)
            self.replace_edit.setAccessibleName("Replacement text")

            self.previous_button = self._button(
                "Previous",
                "Previous match (Shift+F3)",
                "previous-match",
                icon_only=True,
            )
            self.next_button = self._button(
                "Next",
                "Next match (F3)",
                "next-match",
                icon_only=True,
            )
            self.replace_button = self._button(
                "Replace",
                "Replace selected match",
                "replace",
            )
            self.replace_all_button = self._button(
                "Replace All",
                "Replace every match",
                "replace",
            )
            self.close_button = self._button(
                "Close",
                "Close find and replace (Escape)",
                "close",
                icon_only=True,
            )
            self.match_case = QCheckBox("Match case", self)
            self.match_case.setAccessibleName("Match case")
            self.whole_word = QCheckBox("Whole word", self)
            self.whole_word.setAccessibleName("Match whole word")
            self.result_label = QLabel("No search", self)
            self.result_label.setMinimumWidth(78)
            self.result_label.setAlignment(Qt.AlignCenter)
            self.result_label.setAccessibleName("Search result count")

            layout = QGridLayout(self)
            layout.setContentsMargins(8, 5, 8, 5)
            layout.setHorizontalSpacing(5)
            layout.setVerticalSpacing(4)
            layout.addWidget(self.find_edit, 0, 0, 1, 3)
            layout.addWidget(self.previous_button, 0, 3)
            layout.addWidget(self.next_button, 0, 4)
            layout.addWidget(self.match_case, 0, 5)
            layout.addWidget(self.whole_word, 0, 6)
            layout.addWidget(self.result_label, 0, 7)
            layout.addWidget(self.close_button, 0, 8)
            layout.addWidget(self.replace_edit, 1, 0, 1, 3)
            layout.addWidget(self.replace_button, 1, 3)
            layout.addWidget(self.replace_all_button, 1, 4)
            layout.setColumnStretch(0, 1)

            self.find_edit.textChanged.connect(self._schedule_refresh)
            self.find_edit.returnPressed.connect(self.next_match)
            self.replace_edit.returnPressed.connect(self.replace_current)
            self.previous_button.clicked.connect(self.previous_match)
            self.next_button.clicked.connect(self.next_match)
            self.replace_button.clicked.connect(self.replace_current)
            self.replace_all_button.clicked.connect(self.replace_all)
            self.close_button.clicked.connect(self.close_bar)
            self.match_case.toggled.connect(self._schedule_refresh)
            self.whole_word.toggled.connect(self._schedule_refresh)
            self._search_timer.timeout.connect(self._submit_search)
            self._searchCompleted.connect(self._apply_search_result)
            search_service = self._search_service
            # QObject destruction is not a safe point for a Python callback.
            # Retain a wrapper-lifetime fallback without capturing this widget.
            self._search_service_finalizer = finalize(
                self,
                search_service.close,
            )

            self.set_replace_visible(False)
            self.hide()

        def _button(
            self,
            text: str,
            tooltip: str,
            icon_name: str,
            *,
            icon_only: bool = False,
        ) -> QToolButton:
            button = QToolButton(self)
            button.setIcon(
                QIcon(str(pycforge_icon_path(icon_name)))
            )
            button.setText("" if icon_only else text)
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setProperty("role", "find-control")
            button.setToolButtonStyle(
                Qt.ToolButtonIconOnly
                if icon_only
                else Qt.ToolButtonTextBesideIcon
            )
            if icon_only:
                button.setObjectName("IconButton")
            button.setAutoRaise(True)
            return button

        def bind_action_registry(self, registry: Any) -> None:
            """Move commands and widget-scoped shortcuts into *registry*."""

            self._action_registry = registry
            bindings = (
                (
                    "search.previous_match",
                    self.previous_button,
                    self.previous_match,
                ),
                (
                    "search.next_match",
                    self.next_button,
                    self.next_match,
                ),
                (
                    "search.replace_current",
                    self.replace_button,
                    self.replace_current,
                ),
                (
                    "search.replace_all",
                    self.replace_all_button,
                    self.replace_all,
                ),
                (
                    "search.close",
                    self.close_button,
                    self.close_bar,
                ),
            )
            for action_id, button, handler in bindings:
                try:
                    button.clicked.disconnect(handler)
                except (RuntimeError, TypeError):
                    pass
                registry.register_handler(action_id, handler)
                registry.bind_tool_button(action_id, button)
                registry.attach_to_widget(action_id, self)

        @property
        def editor(self) -> CodeEditor | None:
            return self._editor

        @property
        def match_count(self) -> int:
            return self._match_total

        @property
        def stored_match_count(self) -> int:
            return len(self._matches)

        @property
        def matches_truncated(self) -> bool:
            return self._matches_truncated

        @property
        def active_match_index(self) -> int:
            return self._active_index

        def attach_editor(self, editor: CodeEditor | None) -> None:
            """Attach to *editor*, disconnecting cleanly from any previous editor."""

            if editor is self._editor:
                return
            if self._editor is not None:
                try:
                    self._editor.textChanged.disconnect(self._schedule_refresh)
                    self._editor.findRequested.disconnect(self.open_find)
                    self._editor.markerActivated.disconnect(self._marker_activated)
                except (RuntimeError, TypeError):
                    pass
                if self._markers_published:
                    self._editor.set_search_ranges(())
                    self._markers_published = False
            self._editor = editor
            if editor is not None:
                editor.textChanged.connect(self._schedule_refresh)
                editor.findRequested.connect(self.open_find)
                editor.markerActivated.connect(self._marker_activated)
            self.set_replace_visible(self._replace_visible)
            self._schedule_refresh()

        def open_find(self, show_replace: bool = False) -> None:
            self._search_active = True
            self.set_replace_visible(show_replace)
            self.show()
            self.raise_()
            self.find_edit.setFocus(Qt.ShortcutFocusReason)
            self.find_edit.selectAll()
            self._schedule_refresh()

        def close_bar(self) -> None:
            self._search_active = False
            self._search_timer.stop()
            self._search_generation = self._search_service.cancel()
            self._search_pending = False
            self._matches = ()
            self._match_total = 0
            self._matches_truncated = False
            self._active_index = -1
            self.hide()
            if self._editor is not None:
                self._editor.setFocus(Qt.ShortcutFocusReason)
            self._sync_editor_markers()
            self.closed.emit()

        def close_service(self) -> None:
            """Stop pending search work before the containing window retires."""

            self._search_active = False
            self._search_pending = False
            self._search_timer.stop()
            self._search_service.close()

        def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
            if (
                watched is self.find_edit
                and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and event.modifiers() & Qt.ShiftModifier
            ):
                self.previous_match()
                return True
            return super().eventFilter(watched, event)

        def set_replace_visible(self, visible: bool) -> None:
            self._replace_visible = bool(visible)
            enabled = self._editor is not None and not self._editor.isReadOnly()
            for widget in (self.replace_edit, self.replace_button, self.replace_all_button):
                widget.setVisible(self._replace_visible)
                widget.setEnabled(enabled)

        def _schedule_refresh(self, *_args) -> None:
            """Invalidate stale work and debounce the next immutable snapshot."""

            self._search_timer.stop()
            self._search_generation = self._search_service.cancel()
            self._matches = ()
            self._match_total = 0
            self._matches_truncated = False
            self._active_index = -1
            query_ready = (
                self._search_active
                and self._editor is not None
                and bool(self.find_edit.text())
            )
            self._search_pending = query_ready
            self._sync_editor_markers()
            if query_ready:
                self._search_timer.start()

        def _submit_search(self) -> None:
            """Capture the current editor snapshot after the debounce interval."""

            if (
                not self._search_active
                or self._editor is None
                or not self.find_edit.text()
            ):
                self._search_pending = False
                self._sync_editor_markers()
                return
            self._search_pending = True
            self._search_generation = self._search_service.submit(
                self._editor.toPlainText(),
                self.find_edit.text(),
                match_case=self.match_case.isChecked(),
                whole_word=self.whole_word.isChecked(),
                callback=self._searchCompleted.emit,
            )

        def _apply_search_result(self, result: LiteralSearchResult) -> None:
            """Publish a fresh worker result on the Qt event-loop thread."""

            if (
                not self._search_active
                or result.generation != self._search_generation
                or self._editor is None
            ):
                return
            cursor_position = self._editor.textCursor().selectionStart()
            self._matches = result.ranges
            self._match_total = result.total_count
            self._matches_truncated = result.truncated
            self._search_pending = False
            if self._matches:
                self._active_index = next(
                    (
                        index
                        for index, (start, _end) in enumerate(self._matches)
                        if start >= cursor_position
                    ),
                    0,
                )
            else:
                self._active_index = -1
            self._sync_editor_markers()

        def _sync_editor_markers(self) -> None:
            if self._editor is not None and self._search_active:
                markers = tuple(
                    EditorMarker(
                        start,
                        end,
                        kind="search",
                        message=f"Match {index + 1} of {self._match_total}",
                        marker_id=f"search:{index}",
                    )
                    for index, (start, end) in enumerate(self._matches)
                )
                self._editor.set_search_ranges(markers, self._active_index)
                self._markers_published = bool(markers)
            elif self._editor is not None and self._markers_published:
                self._editor.set_search_ranges(())
                self._markers_published = False
            has_matches = bool(self._matches)
            self.previous_button.setEnabled(has_matches)
            self.next_button.setEnabled(has_matches)
            writable = self._editor is not None and not self._editor.isReadOnly()
            self.replace_button.setEnabled(has_matches and writable)
            self.replace_all_button.setEnabled(
                has_matches and writable and not self._matches_truncated
            )
            if self._matches_truncated:
                self.replace_all_button.setToolTip(
                    "Narrow the search before Replace All; the match view is capped"
                )
            else:
                self.replace_all_button.setToolTip("Replace every match")
            if self._search_pending:
                label = "Searching\u2026"
            elif not self.find_edit.text():
                label = "No search"
            elif not has_matches:
                label = "0 matches"
            elif self._matches_truncated:
                label = (
                    f"{self._active_index + 1} / {len(self._matches)} shown"
                    f" \u00b7 {self._match_total} total"
                )
            else:
                label = f"{self._active_index + 1} / {self._match_total}"
            self.result_label.setText(label)
            self.result_label.setAccessibleDescription(label)
            if self._action_registry is not None:
                self._action_registry.refresh()

        def next_match(self) -> bool:
            return self._move_match(1)

        def previous_match(self) -> bool:
            return self._move_match(-1)

        def _move_match(self, delta: int) -> bool:
            if not self._matches or self._editor is None:
                return False
            self._active_index = (self._active_index + delta) % len(self._matches)
            self._select_active_match()
            return True

        def _select_active_match(self) -> None:
            if self._editor is None or not (0 <= self._active_index < len(self._matches)):
                return
            start, end = self._matches[self._active_index]
            self._editor.go_to_position(start, end, focus=False)
            self._sync_editor_markers()
            self.matchActivated.emit(self._active_index, start, end)

        def _marker_activated(self, kind: str, marker_id: str, _start: int) -> None:
            if kind != "search" or not marker_id.startswith("search:"):
                return
            try:
                index = int(marker_id.partition(":")[2])
            except ValueError:
                return
            if 0 <= index < len(self._matches):
                self._active_index = index
                self._select_active_match()

        def replace_current(self) -> bool:
            if (
                self._editor is None
                or self._editor.isReadOnly()
                or not (0 <= self._active_index < len(self._matches))
            ):
                return False
            start, end = self._matches[self._active_index]
            cursor = QTextCursor(self._editor.document())
            cursor.beginEditBlock()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(self.replace_edit.text())
            cursor.endEditBlock()
            self._editor.setTextCursor(cursor)
            self._schedule_refresh()
            self.replacementsMade.emit(1)
            return True

        def replace_all(self) -> int:
            if (
                self._editor is None
                or self._editor.isReadOnly()
                or not self._matches
                or self._matches_truncated
            ):
                return 0
            count = len(self._matches)
            group = QTextCursor(self._editor.document())
            group.beginEditBlock()
            for start, end in reversed(self._matches):
                cursor = QTextCursor(self._editor.document())
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.insertText(self.replace_edit.text())
            group.endEditBlock()
            self._schedule_refresh()
            self.replacementsMade.emit(count)
            return count


else:
    class FindReplaceBar:
        """Headless placeholder retaining a predictable public API."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PyQt5 is required for find and replace widgets") from _QT_ERROR


__all__ = ["FindReplaceBar", "QT_AVAILABLE", "find_literal_ranges"]
