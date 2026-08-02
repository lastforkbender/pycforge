from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path

from pycforge.ide.icons import (
    PYCFORGE_ICON_FILES,
    pycforge_icon_path,
    pycforge_icon_root,
)
from pycforge.ide.theme import PYCFORGE_QSS
from pycforge.ide.theme_stylesheet import build_pycforge_stylesheet
from pycforge.ide.visual_tokens import (
    PYCFORGE_COLORS,
    PYCFORGE_METRICS,
    color_tokens,
    contrast_ratio,
    relative_luminance,
)


ROOT = Path(__file__).resolve().parents[1]
ICON_ROOT = ROOT / "pycforge" / "ide" / "resources" / "icons"
VISUAL_MODULES = (
    ROOT / "pycforge" / "ide" / "icons.py",
    ROOT / "pycforge" / "ide" / "theme.py",
    ROOT / "pycforge" / "ide" / "theme_stylesheet.py",
    ROOT / "pycforge" / "ide" / "visual_tokens.py",
)


class Phase15BVisualTokenTests(unittest.TestCase):
    def test_visual_modules_remain_bounded(self) -> None:
        for path in VISUAL_MODULES:
            with self.subTest(module=path.name):
                self.assertLess(
                    len(path.read_text(encoding="utf-8").splitlines()),
                    600,
                )

    def test_every_color_is_canonical_uppercase_rgb(self) -> None:
        values = {
            field.name: getattr(PYCFORGE_COLORS, field.name)
            for field in fields(PYCFORGE_COLORS)
        }
        self.assertEqual(dict(color_tokens()), values)
        for name, value in values.items():
            with self.subTest(token=name):
                self.assertRegex(value, r"^#[0-9A-F]{6}$")

    def test_readable_roles_meet_wcag_aa_on_primary_surfaces(self) -> None:
        colors = PYCFORGE_COLORS
        foregrounds = (
            colors.text,
            colors.text_soft,
            colors.text_muted,
            colors.text_disabled,
            colors.blue,
            colors.violet,
            colors.warm,
            colors.success,
            colors.warning,
            colors.error,
        )
        for background in (colors.canvas, colors.surface):
            for foreground in foregrounds:
                with self.subTest(
                    foreground=foreground,
                    background=background,
                ):
                    self.assertGreaterEqual(
                        contrast_ratio(foreground, background),
                        4.5,
                    )
        self.assertGreaterEqual(
            contrast_ratio(colors.text, colors.selection),
            7.0,
        )

    def test_contrast_helpers_reject_noncanonical_input(self) -> None:
        self.assertGreater(relative_luminance("#FFFFFF"), 0.99)
        self.assertEqual(relative_luminance("#000000"), 0.0)
        for value in ("fff", "#FFFF", "#GGGGGG", "", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    relative_luminance(value)  # type: ignore[arg-type]

    def test_metrics_are_logical_and_touch_targets_are_consistent(self) -> None:
        metrics = PYCFORGE_METRICS
        self.assertEqual(metrics.icon_menu, 18)
        self.assertEqual(metrics.icon_toolbar, 20)
        self.assertGreaterEqual(metrics.radius_menu, metrics.radius_panel)
        self.assertGreaterEqual(
            metrics.menu_item_left_padding,
            metrics.icon_menu + 16,
        )


class Phase15BStylesheetTests(unittest.TestCase):
    def test_stylesheet_is_complete_and_deterministic(self) -> None:
        self.assertEqual(PYCFORGE_QSS, build_pycforge_stylesheet())
        self.assertGreater(len(PYCFORGE_QSS), 15_000)
        self.assertNotIn("${", PYCFORGE_QSS)
        self.assertNotIn("font-size:", PYCFORGE_QSS)

    def test_custom_menu_language_covers_every_interaction_state(self) -> None:
        selectors = (
            "QMenu#PyCForgeMenu",
            "QMenuBar::item:selected",
            "QMenuBar::item:pressed",
            "QMenu::item:selected",
            "QMenu::item:pressed",
            "QMenu::item:disabled",
            'QMenu#PyCForgeMenu[pycforgeTone="primary"]::item:selected',
            'QMenu#PyCForgeMenu[pycforgeTone="danger"]::item:selected',
            "QMenu::separator",
            "QMenu::icon",
            "QMenu::indicator:checked",
            "QMenu::right-arrow",
            "QMenu::scroller",
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, PYCFORGE_QSS)

    def test_workspace_states_and_high_contrast_path_are_explicit(self) -> None:
        selectors = (
            "QPushButton:hover",
            "QPushButton:focus",
            "QPushButton:pressed",
            "QPushButton:disabled",
            'QPushButton[role="primary"]',
            'QPushButton[role="danger"]',
            'QLabel[status="success"]',
            'QLabel[status="warning"]',
            'QLabel[status="error"]',
            'QWidget[visualMode="high-contrast"] QMenu::item:selected',
            "QProgressBar::chunk",
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, PYCFORGE_QSS)
        for accent in (
            PYCFORGE_COLORS.blue,
            PYCFORGE_COLORS.violet,
            PYCFORGE_COLORS.warm,
        ):
            self.assertIn(accent, PYCFORGE_QSS)


class Phase15BVectorIconTests(unittest.TestCase):
    EXPECTED_ICONS = {
        "about",
        "add-document",
        "brand-mark",
        "cancel",
        "check",
        "chevron-right",
        "close",
        "collapse-all",
        "command-palette",
        "convert",
        "copy",
        "cut",
        "decision-trace",
        "details",
        "diagnostics",
        "duplicate-line",
        "exit",
        "expand-all",
        "find",
        "bundle-search",
        "go-to-line",
        "go-to-output",
        "go-to-source",
        "history",
        "indent",
        "link-c",
        "mappings",
        "module",
        "move-down",
        "move-line-down",
        "move-line-up",
        "move-up",
        "next-match",
        "open",
        "outline",
        "outdent",
        "paste",
        "previous-match",
        "primary-module",
        "redo",
        "remove-document",
        "replace",
        "save-as",
        "save-c",
        "save-python",
        "select-all",
        "settings",
        "split-view",
        "summary",
        "telemetry",
        "toggle-comment",
        "toggle-fold",
        "undo",
        "view-c",
        "whitespace",
    }

    def test_catalogue_and_packaged_inventory_are_exact(self) -> None:
        self.assertEqual(set(PYCFORGE_ICON_FILES), self.EXPECTED_ICONS)
        self.assertEqual(
            len(PYCFORGE_ICON_FILES),
            len(set(PYCFORGE_ICON_FILES.values())),
        )
        self.assertEqual(pycforge_icon_root().resolve(), ICON_ROOT.resolve())
        self.assertEqual(
            {path.name for path in ICON_ROOT.glob("*.svg")},
            set(PYCFORGE_ICON_FILES.values()),
        )
        for name in self.EXPECTED_ICONS:
            with self.subTest(icon=name):
                self.assertTrue(pycforge_icon_path(name).is_file())
        with self.assertRaisesRegex(KeyError, "unknown PyCForge icon"):
            pycforge_icon_path("missing")

    def test_every_icon_is_safe_scalable_vector_art(self) -> None:
        forbidden_elements = {
            "foreignObject",
            "image",
            "script",
            "style",
            "text",
        }
        allowed_colors = set(color_tokens().values())
        for path in sorted(ICON_ROOT.glob("*.svg")):
            with self.subTest(icon=path.name):
                document = path.read_text(encoding="utf-8")
                root = ET.fromstring(document)
                self.assertEqual(_local_name(root.tag), "svg")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 24 24")
                self.assertNotIn("width", root.attrib)
                self.assertNotIn("height", root.attrib)
                self.assertTrue(list(root))
                for element in root.iter():
                    self.assertNotIn(
                        _local_name(element.tag),
                        forbidden_elements,
                    )
                    for attribute, value in element.attrib.items():
                        local = _local_name(attribute)
                        self.assertNotIn(local, {"href", "src"})
                        self.assertNotRegex(
                            value,
                            re.compile(
                                r"(?i)(?:data:|https?://|file:|javascript:)"
                            ),
                        )
                        if local in {"fill", "stroke"} and value != "none":
                            self.assertIn(value, allowed_colors)
                        if local == "stroke-width":
                            self.assertGreaterEqual(float(value), 1.5)
                            self.assertLessEqual(float(value), 2.0)

    def test_resources_contain_no_bitmap_assets(self) -> None:
        bitmap_suffixes = {
            ".avif",
            ".bmp",
            ".gif",
            ".ico",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        }
        self.assertFalse(
            [
                path
                for path in ICON_ROOT.iterdir()
                if path.suffix.lower() in bitmap_suffixes
            ]
        )


def _local_name(expanded_name: str) -> str:
    return expanded_name.rsplit("}", 1)[-1]


if __name__ == "__main__":
    unittest.main()
