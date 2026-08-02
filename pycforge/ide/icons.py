"""Headless-safe catalogue for PyCForge's packaged vector iconography."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Mapping


PYCFORGE_ICON_FILES: Mapping[str, str] = MappingProxyType(
    {
        "about": "about.svg",
        "add-document": "add-document.svg",
        "brand-mark": "brand-mark.svg",
        "cancel": "cancel.svg",
        "check": "check.svg",
        "chevron-right": "chevron-right.svg",
        "close": "close.svg",
        "collapse-all": "collapse-all.svg",
        "command-palette": "command-palette.svg",
        "convert": "convert.svg",
        "copy": "copy.svg",
        "cut": "cut.svg",
        "decision-trace": "decision-trace.svg",
        "details": "details.svg",
        "diagnostics": "diagnostics.svg",
        "duplicate-line": "duplicate-line.svg",
        "exit": "exit.svg",
        "expand-all": "expand-all.svg",
        "find": "find.svg",
        "bundle-search": "bundle-search.svg",
        "go-to-line": "go-to-line.svg",
        "go-to-output": "go-to-output.svg",
        "go-to-source": "go-to-source.svg",
        "history": "history.svg",
        "indent": "indent.svg",
        "link-c": "link-c.svg",
        "mappings": "mappings.svg",
        "module": "module.svg",
        "move-down": "move-down.svg",
        "move-line-down": "move-line-down.svg",
        "move-line-up": "move-line-up.svg",
        "move-up": "move-up.svg",
        "next-match": "next.svg",
        "open": "open.svg",
        "outline": "outline.svg",
        "outdent": "outdent.svg",
        "paste": "paste.svg",
        "previous-match": "previous.svg",
        "primary-module": "primary-module.svg",
        "redo": "redo.svg",
        "remove-document": "remove-document.svg",
        "replace": "replace.svg",
        "save-as": "save-as.svg",
        "save-c": "export.svg",
        "save-python": "save.svg",
        "select-all": "select-all.svg",
        "settings": "settings.svg",
        "split-view": "split-view.svg",
        "summary": "summary.svg",
        "telemetry": "telemetry.svg",
        "toggle-comment": "toggle-comment.svg",
        "toggle-fold": "toggle-fold.svg",
        "undo": "undo.svg",
        "view-c": "show-c.svg",
        "whitespace": "whitespace.svg",
    }
)


def pycforge_icon_root() -> Path:
    """Return the packaged vector-resource directory."""

    return Path(__file__).parent / "resources" / "icons"


def pycforge_icon_path(name: str) -> Path:
    """Return the packaged SVG path for a stable logical icon name."""

    try:
        filename = PYCFORGE_ICON_FILES[name]
    except KeyError as exc:
        raise KeyError(f"unknown PyCForge icon: {name}") from exc
    return pycforge_icon_root() / filename


__all__ = [
    "PYCFORGE_ICON_FILES",
    "pycforge_icon_path",
    "pycforge_icon_root",
]
