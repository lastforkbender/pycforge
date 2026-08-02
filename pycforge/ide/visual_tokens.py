"""Headless-safe semantic tokens for the PyCForge desktop visual system.

The optional Qt workspace and its tests share these values without importing
PyQt5.  Colors are named for their role rather than a particular widget so the
visual language remains coherent across menus, editors, panels, and future
presentation surfaces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PyCForgeColors:
    """Professional graphite palette with restrained operational accents."""

    void: str = "#070A10"
    canvas: str = "#0B0F16"
    surface: str = "#111823"
    surface_raised: str = "#172130"
    surface_active: str = "#1D2939"
    surface_hover: str = "#243348"
    border: str = "#29384A"
    border_strong: str = "#3B526A"
    text: str = "#F1F5FA"
    text_soft: str = "#C8D2DE"
    text_muted: str = "#9BAABC"
    text_disabled: str = "#748497"
    blue: str = "#4FB6FF"
    blue_bright: str = "#7BCCFF"
    blue_dim: str = "#1B425D"
    cyan: str = "#4FB6FF"
    cyan_bright: str = "#7BCCFF"
    cyan_dim: str = "#1B425D"
    violet: str = "#A58BFF"
    violet_bright: str = "#C0AEFF"
    violet_dim: str = "#443B70"
    warm: str = "#FF9A52"
    warm_bright: str = "#FFB878"
    warm_dim: str = "#55321F"
    success: str = "#5AD8A6"
    success_bright: str = "#91EDC8"
    success_dim: str = "#173C30"
    warning: str = "#FFC56F"
    warning_bright: str = "#FFDEA3"
    warning_dim: str = "#49371B"
    error: str = "#FF7085"
    error_bright: str = "#FFABB8"
    error_dim: str = "#49212A"
    selection: str = "#244F70"
    selection_active: str = "#2C638B"
    focus_ring: str = "#7BCCFF"


@dataclass(frozen=True, slots=True)
class PyCForgeMetrics:
    """Logical-pixel metrics; Qt applies the effective display scale."""

    radius_small: int = 4
    radius_control: int = 6
    radius_panel: int = 8
    radius_menu: int = 9
    icon_menu: int = 18
    icon_toolbar: int = 20
    icon_navigator: int = 18
    focus_width: int = 2
    menu_outer_padding: int = 6
    menu_item_vertical_padding: int = 7
    menu_item_left_padding: int = 38
    menu_item_right_padding: int = 36


PYCFORGE_COLORS = PyCForgeColors()
PYCFORGE_METRICS = PyCForgeMetrics()


def color_tokens(
    colors: PyCForgeColors = PYCFORGE_COLORS,
) -> Mapping[str, str]:
    """Return an immutable token mapping suitable for stylesheet expansion."""

    return MappingProxyType(asdict(colors))


def relative_luminance(color: str) -> float:
    """Return WCAG relative luminance for an exact ``#RRGGBB`` color."""

    red, green, blue = _rgb_channels(color)
    linear = tuple(
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in (red, green, blue)
    )
    return (
        0.2126 * linear[0]
        + 0.7152 * linear[1]
        + 0.0722 * linear[2]
    )


def contrast_ratio(first: str, second: str) -> float:
    """Return the WCAG contrast ratio between two exact RGB colors."""

    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def _rgb_channels(color: str) -> tuple[float, float, float]:
    if (
        not isinstance(color, str)
        or len(color) != 7
        or not color.startswith("#")
    ):
        raise ValueError("color must use exact #RRGGBB notation")
    try:
        values = tuple(
            int(color[index : index + 2], 16) / 255.0
            for index in (1, 3, 5)
        )
    except ValueError as exc:
        raise ValueError(
            "color must use exact #RRGGBB notation"
        ) from exc
    return values  # type: ignore[return-value]


__all__ = [
    "PYCFORGE_COLORS",
    "PYCFORGE_METRICS",
    "PyCForgeColors",
    "PyCForgeMetrics",
    "color_tokens",
    "contrast_ratio",
    "relative_luminance",
]
