"""Qt adapter for bounded, undoable Python source-editor commands."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtGui import QTextCursor, QTextOption

from .source_editing import (
    SourceEditResult,
    duplicate_lines,
    indent_lines,
    move_lines_down,
    move_lines_up,
    outdent_lines,
    toggle_python_line_comment,
)


FOLD_BLOCK_LIMIT = 2_048
FOLD_TOTAL_BLOCK_LIMIT = 8_192
MAX_FOLDS = 128


def _python_offset(text: str, qt_offset: int) -> int:
    """Convert a clamped Qt UTF-16 position to a Python string offset."""

    target = max(0, int(qt_offset))
    if text.isascii():
        return min(len(text), target)
    units = 0
    for index, character in enumerate(text):
        width = 2 if ord(character) > 0xFFFF else 1
        if units + width > target:
            return index
        units += width
        if units == target:
            return index + 1
    return len(text)


def _qt_offset(text: str, python_offset: int) -> int:
    position = min(len(text), max(0, int(python_offset)))
    if text.isascii():
        return position
    return len(text[:position].encode("utf-16-le")) // 2


def _changed_span(before: str, after: str) -> tuple[int, int, int]:
    """Return common prefix, old suffix start, and new suffix start."""

    prefix = 0
    limit = min(len(before), len(after))
    while prefix < limit and before[prefix] == after[prefix]:
        prefix += 1
    old_suffix = len(before)
    new_suffix = len(after)
    while (
        old_suffix > prefix
        and new_suffix > prefix
        and before[old_suffix - 1] == after[new_suffix - 1]
    ):
        old_suffix -= 1
        new_suffix -= 1
    return prefix, old_suffix, new_suffix


def _indentation(text: str) -> int:
    return len(text) - len(text.lstrip(" \t"))


class SourceCommandMixin:
    """Editing, navigation, whitespace, and folding for ``CodeEditor``."""

    def _initialize_source_commands(
        self,
        *,
        highlighting_enabled: bool,
    ) -> None:
        self._highlighting_enabled = bool(highlighting_enabled)
        self._whitespace_visible = False
        self._folded_blocks: dict[int, tuple[object, ...]] = {}
        if not self._highlighting_enabled:
            self._highlighter.setDocument(None)

    @property
    def whitespace_visible(self) -> bool:
        return self._whitespace_visible

    def bind_text_document(self, document) -> None:
        """Bind a pre-existing Qt document while retaining editor behavior."""

        if document is self.document():
            return
        self.unfold_all()
        self._highlighter.setDocument(None)
        # QSyntaxHighlighter is initially parented to the editor's original
        # QTextDocument.  Reparent it before QPlainTextEdit releases that
        # document so shared-buffer rebinding cannot delete the highlighter.
        self._highlighter.setParent(self)
        super().setDocument(document)
        self._update_large_file_mode()
        if self._highlighting_enabled and not self.large_file_mode:
            self._highlighter.setDocument(document)
        self.clear_markers()
        self._apply_whitespace_option()
        self._update_viewport_margins()
        self._refresh_extra_selections()

    def duplicate_line_or_selection(self) -> bool:
        return self._apply_source_operation(duplicate_lines)

    def move_source_lines_up(self) -> bool:
        return self._apply_source_operation(move_lines_up)

    def move_source_lines_down(self) -> bool:
        return self._apply_source_operation(move_lines_down)

    def indent_source_lines(self) -> bool:
        return self._apply_source_operation(indent_lines)

    def outdent_source_lines(self) -> bool:
        return self._apply_source_operation(outdent_lines)

    def toggle_source_comment(self) -> bool:
        return self._apply_source_operation(toggle_python_line_comment)

    def _apply_source_operation(
        self,
        operation: Callable[[str, int, int], SourceEditResult],
    ) -> bool:
        if self.isReadOnly() or self.language != "python":
            return False
        before = self.toPlainText()
        active = self.textCursor()
        start = _python_offset(before, active.selectionStart())
        end = _python_offset(before, active.selectionEnd())
        result = operation(before, start, end)
        if result.text == before:
            return False
        prefix, old_suffix, new_suffix = _changed_span(
            before,
            result.text,
        )
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(_qt_offset(before, prefix))
        cursor.setPosition(
            _qt_offset(before, old_suffix),
            QTextCursor.KeepAnchor,
        )
        cursor.insertText(result.text[prefix:new_suffix])
        cursor.endEditBlock()
        selection = QTextCursor(self.document())
        selection.setPosition(
            _qt_offset(result.text, result.selection_start)
        )
        selection.setPosition(
            _qt_offset(result.text, result.selection_end),
            QTextCursor.KeepAnchor,
        )
        self.setTextCursor(selection)
        self.ensureCursorVisible()
        return True

    def go_to_line_number(self, line: int) -> int:
        """Go to a clamped one-based line without copying source text."""

        if isinstance(line, bool) or not isinstance(line, int):
            raise TypeError("line must be an integer")
        maximum = max(1, self.document().blockCount())
        resolved = min(maximum, max(1, line))
        block = self.document().findBlockByNumber(resolved - 1)
        cursor = QTextCursor(block)
        self.setTextCursor(cursor)
        self.centerCursor()
        self.setFocus()
        return resolved

    def set_whitespace_visible(self, visible: bool) -> None:
        enabled = bool(visible)
        if enabled == self._whitespace_visible:
            return
        self._whitespace_visible = enabled
        self._apply_whitespace_option()

    def _apply_whitespace_option(self) -> None:
        option = self.document().defaultTextOption()
        flags = option.flags()
        markers = (
            QTextOption.ShowTabsAndSpaces
            | QTextOption.ShowLineAndParagraphSeparators
        )
        option.setFlags(flags | markers if self._whitespace_visible else flags & ~markers)
        self.document().setDefaultTextOption(option)
        self.viewport().update()

    def toggle_fold_at_cursor(self) -> bool:
        """Fold or unfold one indentation region under absolute budgets."""

        if self.language != "python":
            return False
        start = self.textCursor().block()
        key = start.position()
        retained = self._folded_blocks.pop(key, None)
        if retained is not None:
            self._set_blocks_visible(retained, True)
            return True
        if (
            len(self._folded_blocks) >= MAX_FOLDS
            or sum(len(value) for value in self._folded_blocks.values())
            >= FOLD_TOTAL_BLOCK_LIMIT
        ):
            return False
        base = _indentation(start.text())
        block = start.next()
        candidates: list[object] = []
        found_body = False
        while block.isValid() and len(candidates) < FOLD_BLOCK_LIMIT:
            text = block.text()
            if text.strip():
                indent = _indentation(text)
                if indent <= base:
                    break
                found_body = True
            candidates.append(block)
            block = block.next()
        if not found_body:
            return False
        remaining = FOLD_TOTAL_BLOCK_LIMIT - sum(
            len(value) for value in self._folded_blocks.values()
        )
        retained = tuple(candidates[:remaining])
        if not retained:
            return False
        self._folded_blocks[key] = retained
        self._set_blocks_visible(retained, False)
        return True

    def unfold_all(self) -> None:
        for blocks in tuple(self._folded_blocks.values()):
            self._set_blocks_visible(blocks, True)
        self._folded_blocks.clear()

    def _set_blocks_visible(
        self,
        blocks: tuple[object, ...],
        visible: bool,
    ) -> None:
        first = None
        last = None
        for block in blocks:
            if not block.isValid():
                continue
            first = block.position() if first is None else first
            last = block.position() + block.length()
            block.setVisible(visible)
            block.setLineCount(1 if visible else 0)
        if first is not None and last is not None:
            self.document().markContentsDirty(first, max(1, last - first))
        self.viewport().update()
        self._update_viewport_margins()

    def _reset_source_command_state(self) -> None:
        if self._folded_blocks:
            self.unfold_all()


__all__ = [
    "FOLD_BLOCK_LIMIT",
    "FOLD_TOTAL_BLOCK_LIMIT",
    "MAX_FOLDS",
    "SourceCommandMixin",
]
