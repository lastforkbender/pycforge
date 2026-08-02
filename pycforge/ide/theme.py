"""Qt adapter for the PyCForge visual system.

The authoritative palette, vector catalogue, and stylesheet builder live in
headless-safe modules.  This adapter remains importable when PyQt5 is absent so
the source-transpiler core never acquires a desktop dependency.
"""

from __future__ import annotations

from typing import Any

from .icons import PYCFORGE_ICON_FILES, pycforge_icon_path
from .theme_stylesheet import build_pycforge_stylesheet
from .visual_tokens import (
    PYCFORGE_COLORS,
    PYCFORGE_METRICS,
    PyCForgeColors,
    PyCForgeMetrics,
)

try:  # Keep diagnostics useful if a required dependency is damaged.
    from PyQt5.QtGui import QColor, QPalette
except (ImportError, ModuleNotFoundError):
    QColor = None  # type: ignore[assignment]
    QPalette = None  # type: ignore[assignment]
    QT_THEME_AVAILABLE = False
else:
    QT_THEME_AVAILABLE = True


PYCFORGE_QSS = build_pycforge_stylesheet()


def pycforge_palette(
    colors: PyCForgeColors = PYCFORGE_COLORS,
) -> Any | None:
    """Build the Qt palette, or return ``None`` if PyQt5 is unavailable."""

    if not QT_THEME_AVAILABLE or QColor is None or QPalette is None:
        return None

    palette = QPalette()
    role_colors = {
        QPalette.Window: colors.canvas,
        QPalette.WindowText: colors.text,
        QPalette.Base: colors.void,
        QPalette.AlternateBase: colors.surface,
        QPalette.ToolTipBase: colors.surface_active,
        QPalette.ToolTipText: colors.text,
        QPalette.Text: colors.text,
        QPalette.Button: colors.surface_raised,
        QPalette.ButtonText: colors.text,
        QPalette.BrightText: colors.blue_bright,
        QPalette.Highlight: colors.selection,
        QPalette.HighlightedText: "#FFFFFF",
        QPalette.Link: colors.blue,
        QPalette.LinkVisited: colors.violet,
        QPalette.Light: colors.border_strong,
        QPalette.Midlight: colors.border,
        QPalette.Dark: colors.canvas,
        QPalette.Mid: colors.border,
        QPalette.Shadow: colors.void,
    }
    for role, value in role_colors.items():
        palette.setColor(role, QColor(value))

    placeholder_role = getattr(QPalette, "PlaceholderText", None)
    if placeholder_role is not None:
        palette.setColor(
            placeholder_role, QColor(colors.text_muted)
        )
    for role in (
        QPalette.WindowText,
        QPalette.Text,
        QPalette.ButtonText,
    ):
        palette.setColor(
            QPalette.Disabled, role, QColor(colors.text_disabled)
        )
    palette.setColor(
        QPalette.Disabled,
        QPalette.Highlight,
        QColor(colors.surface_active),
    )
    palette.setColor(
        QPalette.Disabled,
        QPalette.HighlightedText,
        QColor(colors.text_disabled),
    )
    return palette


def apply_pycforge_theme(application: Any) -> bool:
    """Apply Fusion, the palette, and PyCForge QSS to an application."""

    palette = pycforge_palette()
    if palette is None:
        return False
    if application is None:
        raise TypeError("application must be a QApplication instance")
    application.setStyle("Fusion")
    application.setPalette(palette)
    application.setStyleSheet(PYCFORGE_QSS)
    return True


__all__ = [
    "QT_THEME_AVAILABLE",
    "PYCFORGE_COLORS",
    "PYCFORGE_ICON_FILES",
    "PYCFORGE_METRICS",
    "PYCFORGE_QSS",
    "PyCForgeColors",
    "PyCForgeMetrics",
    "apply_pycforge_theme",
    "build_pycforge_stylesheet",
    "pycforge_icon_path",
    "pycforge_palette",
]
