"""Qt-free lexical protection used by the optional syntax highlighter."""

from __future__ import annotations


def lexical_protected_spans(
    text: str, language: str
) -> tuple[tuple[tuple[int, int], ...], int | None]:
    """Lex strings and the first real line comment without overlap."""

    if language not in {"python", "c"}:
        raise ValueError("syntax language must be 'python' or 'c'")
    strings: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        if language == "python" and text[index] == "#":
            return tuple(strings), index
        if language == "c" and text.startswith("//", index):
            return tuple(strings), index
        quote = text[index]
        if quote not in {"'", '"'}:
            index += 1
            continue
        delimiter = quote
        if language == "python" and text.startswith(
            quote * 3, index
        ):
            delimiter = quote * 3
        start = index
        index += len(delimiter)
        while index < len(text):
            if text[index] == "\\":
                index = min(len(text), index + 2)
                continue
            if text.startswith(delimiter, index):
                index += len(delimiter)
                break
            index += 1
        strings.append((start, index))
    return tuple(strings), None


__all__ = ["lexical_protected_spans"]
