from __future__ import annotations

import re
import unittest
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path

from pycforge.ide.theme import (
    PYCFORGE_COLORS,
    PYCFORGE_ICON_FILES,
    PYCFORGE_QSS,
    QT_THEME_AVAILABLE,
    apply_pycforge_theme,
    pycforge_icon_path,
    pycforge_palette,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "pycforge" / "ide" / "resources"
ICON_ROOT = RESOURCE_ROOT / "icons"


class Phase121PyCForgeThemeTests(unittest.TestCase):
    def test_theme_is_complete_and_import_safe(self) -> None:
        self.assertGreater(len(PYCFORGE_QSS), 8_000)
        required_surfaces = (
            "QMainWindow",
            "QToolBar",
            "QPushButton:hover",
            "QPushButton:focus",
            "QPushButton:disabled",
            "QTabWidget::pane",
            "QTabBar::tab:selected",
            "QPlainTextEdit:focus",
            'QWidget[role="find-bar"]',
            "QScrollBar:vertical",
            "QScrollBar::handle:vertical:hover",
            "QStatusBar",
            'QLabel[role="status-chip"]',
            "QToolTip",
        )
        for selector in required_surfaces:
            with self.subTest(selector=selector):
                self.assertIn(selector, PYCFORGE_QSS)

        for semantic_state in ('state="error"', 'state="warning"', 'state="success"'):
            with self.subTest(semantic_state=semantic_state):
                self.assertIn(semantic_state, PYCFORGE_QSS)

        self.assertIsInstance(QT_THEME_AVAILABLE, bool)
        if not QT_THEME_AVAILABLE:
            self.assertIsNone(pycforge_palette())
            self.assertFalse(apply_pycforge_theme(object()))

    def test_palette_tokens_are_valid_and_high_contrast(self) -> None:
        token_values = {
            field.name: getattr(PYCFORGE_COLORS, field.name)
            for field in fields(PYCFORGE_COLORS)
        }
        for name, value in token_values.items():
            with self.subTest(name=name):
                self.assertRegex(value, r"^#[0-9A-F]{6}$")

        for foreground in (
            PYCFORGE_COLORS.text,
            PYCFORGE_COLORS.text_soft,
            PYCFORGE_COLORS.text_muted,
        ):
            with self.subTest(foreground=foreground):
                self.assertGreaterEqual(
                    _contrast_ratio(foreground, PYCFORGE_COLORS.canvas), 4.5
                )

    def test_qss_covers_integrated_pycforge_workspace_objects(self) -> None:
        required_selectors = (
            "QMenuBar",
            "QMenuBar::item:selected",
            "QFrame#DocumentNavigator",
            "QToolButton#IconButton",
            "QLineEdit#NavigatorFilter",
            "QListWidget#DocumentList::item:selected",
            "QLabel#PanelEyebrow",
            "QLabel#MutedLabel",
            "QLabel#PathLabel",
            "QLabel#ActiveModuleLabel",
            'QFrame#ToastBanner[tone="info"]',
            'QFrame#ToastBanner[tone="success"]',
            'QFrame#ToastBanner[tone="warning"]',
            'QFrame#ToastBanner[tone="error"]',
            "QWidget#DiagnosticsView",
            "QWidget#MappingsView",
            "QWidget#InspectorTree",
            "QTreeWidget#DiagnosticsTree",
            "QTreeWidget#MappingsTree",
            "QTextBrowser#DiagnosticDetails",
            "QFrame#SourceEditorSurface",
            "QFrame#GeneratedCPanel",
            "QPlainTextEdit#PythonSourceEditor",
            "QPlainTextEdit#GeneratedCEditor",
        )
        for selector in required_selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, PYCFORGE_QSS)

        panel_source = (ROOT / "pycforge/ide/panels.py").read_text(encoding="utf-8")
        qt_source = (ROOT / "pycforge/ide/qt.py").read_text(encoding="utf-8")
        for object_name in (
            "DocumentNavigator",
            "DocumentList",
            "PanelEyebrow",
            "MutedLabel",
            "PathLabel",
            "ToastBanner",
            "DiagnosticsView",
            "MappingsView",
            "InspectorTree",
        ):
            with self.subTest(object_name=object_name):
                self.assertIn(f'setObjectName("{object_name}")', panel_source + qt_source)

        for tone, foreground, background in (
            ("info", "#CDEFFC", "#12313D"),
            ("success", "#C9F7E2", "#123329"),
            ("warning", "#FFE4AB", "#3A301B"),
            ("error", "#FFD0D6", "#3A1E26"),
        ):
            with self.subTest(toast_contrast=tone):
                self.assertGreaterEqual(_contrast_ratio(foreground, background), 7.0)

    def test_icon_catalogue_covers_workspace_mechanics(self) -> None:
        expected = {
            "open",
            "save-python",
            "convert",
            "save-c",
            "view-c",
            "cancel",
            "add-document",
            "remove-document",
            "move-up",
            "move-down",
            "find",
            "replace",
            "link-c",
            "previous-match",
            "next-match",
            "settings",
            "close",
        }
        self.assertTrue(expected <= set(PYCFORGE_ICON_FILES))
        self.assertEqual(
            len(set(PYCFORGE_ICON_FILES.values())),
            len(PYCFORGE_ICON_FILES),
        )

        icon_root = ICON_ROOT.resolve()
        for logical_name in sorted(expected):
            with self.subTest(icon=logical_name):
                path = pycforge_icon_path(logical_name)
                self.assertEqual(path.parent.resolve(), icon_root)
                self.assertTrue(path.is_file())
                self.assertEqual(path.suffix, ".svg")

        with self.assertRaisesRegex(KeyError, "unknown PyCForge icon"):
            pycforge_icon_path("not-an-icon")

    def test_icons_are_self_contained_vector_assets(self) -> None:
        forbidden_elements = {"image", "script", "foreignObject", "style"}
        for path in sorted(ICON_ROOT.glob("*.svg")):
            with self.subTest(icon=path.name):
                root = ET.parse(path).getroot()
                self.assertEqual(_local_name(root.tag), "svg")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 24 24")
                self.assertNotIn("width", root.attrib)
                self.assertNotIn("height", root.attrib)
                self.assertTrue(list(root))
                for element in root.iter():
                    self.assertNotIn(_local_name(element.tag), forbidden_elements)
                    for attribute, value in element.attrib.items():
                        self.assertNotIn(_local_name(attribute), {"href", "src"})
                        self.assertNotRegex(value, r"(?i)(?:data:|https?://|file:)")

    def test_resources_contain_no_bitmap_or_embedded_raster(self) -> None:
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
        assets = [path for path in RESOURCE_ROOT.rglob("*") if path.is_file()]
        self.assertTrue(assets)
        self.assertFalse(
            [path.relative_to(RESOURCE_ROOT) for path in assets if path.suffix.lower() in bitmap_suffixes]
        )
        for path in assets:
            if path.suffix.lower() == ".svg":
                self.assertNotRegex(
                    path.read_text(encoding="utf-8"),
                    re.compile(r"(?i)image/(?:png|jpeg|gif|webp|bmp)"),
                )


def _local_name(expanded_name: str) -> str:
    return expanded_name.rsplit("}", 1)[-1]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


if __name__ == "__main__":
    unittest.main()
