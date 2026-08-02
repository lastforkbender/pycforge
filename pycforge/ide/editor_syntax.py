"""Deterministic PyQt5 syntax highlighting for PyCForge editors."""

from __future__ import annotations

from PyQt5.QtCore import QRegularExpression
from PyQt5.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QSyntaxHighlighter,
)

from .editor_lexical import lexical_protected_spans
from .visual_tokens import PYCFORGE_COLORS


_PYTHON_KEYWORDS = (
    "and", "as", "assert", "async", "await", "break", "case", "class",
    "continue", "def", "del", "elif", "else", "except", "False",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "match", "None", "nonlocal", "not", "or", "pass", "raise",
    "return", "True", "try", "while", "with", "yield",
)
_PYTHON_BUILTINS = (
    "abs", "all", "any", "bool", "bytes", "dict", "enumerate", "float",
    "int", "len", "list", "max", "min", "object", "print", "range",
    "reversed", "set", "str", "sum", "tuple", "type", "zip",
)
_C_KEYWORDS = (
    "_Alignas", "_Alignof", "_Atomic", "_Bool", "_Complex", "_Generic",
    "_Imaginary", "_Noreturn", "_Static_assert", "_Thread_local", "auto",
    "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
)


def _format(
    color: str,
    *,
    bold: bool = False,
    italic: bool = False,
) -> QTextCharFormat:
    value = QTextCharFormat()
    value.setForeground(QColor(color))
    if bold:
        value.setFontWeight(QFont.DemiBold)
    value.setFontItalic(italic)
    return value


class PyCForgeSyntaxHighlighter(QSyntaxHighlighter):
    """Deterministic Python/C highlighter tuned for a dark source surface."""

    _COLORS = {
        "keyword": PYCFORGE_COLORS.blue_bright,
        "builtin": PYCFORGE_COLORS.success,
        "type": PYCFORGE_COLORS.success_bright,
        "number": PYCFORGE_COLORS.warm_bright,
        "string": PYCFORGE_COLORS.warning_bright,
        "comment": PYCFORGE_COLORS.text_disabled,
        "decorator": PYCFORGE_COLORS.violet_bright,
        "function": PYCFORGE_COLORS.text,
        "preprocessor": PYCFORGE_COLORS.violet,
    }

    def __init__(self, document, language: str = "python") -> None:
        super().__init__(document)
        self._language = "python"
        self._rules: tuple[
            tuple[QRegularExpression, QTextCharFormat], ...
        ] = ()
        self.set_language(language)

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        normalized = str(language).strip().lower()
        if normalized in {"py", "python3"}:
            normalized = "python"
        elif normalized in {"c11", "c99", "h", "header"}:
            normalized = "c"
        if normalized not in {"python", "c"}:
            raise ValueError(
                "syntax language must be 'python' or 'c'"
            )
        self._language = normalized
        self._rules = self._build_rules(normalized)
        self.rehighlight()

    @classmethod
    def _build_rules(
        cls, language: str
    ) -> tuple[tuple[QRegularExpression, QTextCharFormat], ...]:
        keyword_source = (
            _PYTHON_KEYWORDS
            if language == "python"
            else _C_KEYWORDS
        )
        keyword = r"\b(?:" + "|".join(keyword_source) + r")\b"
        rules: list[
            tuple[QRegularExpression, QTextCharFormat]
        ] = [
            (
                QRegularExpression(keyword),
                _format(cls._COLORS["keyword"], bold=True),
            ),
            (
                QRegularExpression(
                    r"\b(?:0[xX][0-9a-fA-F]+|0[bB][01]+|"
                    r"0[oO][0-7]+|(?:\d+(?:\.\d*)?|\.\d+)"
                    r"(?:[eE][+-]?\d+)?)\b"
                ),
                _format(cls._COLORS["number"]),
            ),
        ]
        if language == "python":
            rules.extend(
                [
                    (
                        QRegularExpression(
                            r"\b(?:"
                            + "|".join(_PYTHON_BUILTINS)
                            + r")\b"
                        ),
                        _format(cls._COLORS["builtin"]),
                    ),
                    (
                        QRegularExpression(r"^\s*@[^\s(]+"),
                        _format(cls._COLORS["decorator"]),
                    ),
                    (
                        QRegularExpression(
                            r"\b(?:def|class)\s+([A-Za-z_]\w*)"
                        ),
                        _format(
                            cls._COLORS["function"], bold=True
                        ),
                    ),
                ]
            )
        else:
            rules.extend(
                [
                    (
                        QRegularExpression(
                            r"\b(?:bool|int\d+_t|uint\d+_t|"
                            r"size_t|ptrdiff_t)\b"
                        ),
                        _format(cls._COLORS["type"]),
                    ),
                    (
                        QRegularExpression(
                            r"^\s*#\s*[A-Za-z_]+.*$"
                        ),
                        _format(cls._COLORS["preprocessor"]),
                    ),
                ]
            )
        return tuple(rules)

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for expression, char_format in self._rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    char_format,
                )
        strings, comment_start = self._protected_spans(text)
        for start, end in strings:
            self.setFormat(
                start,
                end - start,
                _format(self._COLORS["string"]),
            )
        if comment_start is not None:
            self.setFormat(
                comment_start,
                len(text) - comment_start,
                _format(
                    self._COLORS["comment"], italic=True
                ),
            )
        if self._language == "python":
            self._highlight_multiline(text, "'''", "'''", 1)
            self._highlight_multiline(text, '"""', '"""', 2)
        else:
            self._highlight_multiline(text, "/*", "*/", 1)

    def _protected_spans(
        self, text: str
    ) -> tuple[tuple[tuple[int, int], ...], int | None]:
        return lexical_protected_spans(text, self._language)

    def _highlight_multiline(
        self,
        text: str,
        opener: str,
        closer: str,
        state: int,
    ) -> None:
        if self.previousBlockState() == state:
            start = 0
        else:
            start = text.find(opener)
        while start >= 0:
            search_from = (
                start
                if self.previousBlockState() == state
                else start + len(opener)
            )
            end = text.find(closer, search_from)
            if end < 0:
                self.setCurrentBlockState(state)
                length = len(text) - start
            else:
                length = end - start + len(closer)
            role = (
                "string"
                if self._language == "python"
                else "comment"
            )
            self.setFormat(
                start,
                length,
                _format(
                    self._COLORS[role],
                    italic=role == "comment",
                ),
            )
            if end < 0:
                break
            start = text.find(opener, start + length)


__all__ = ["PyCForgeSyntaxHighlighter"]
