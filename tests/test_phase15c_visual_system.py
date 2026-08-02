from __future__ import annotations

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

from pycforge.ide import VISUAL_SYSTEM_VERSION
from pycforge.ide.action_contract import ACTION_SPECS
from pycforge.ide.icons import (
    PYCFORGE_ICON_FILES,
    pycforge_icon_path,
    pycforge_icon_root,
)
from pycforge.ide.theme import PYCFORGE_QSS
from pycforge.ide.theme_stylesheet import build_pycforge_stylesheet
from pycforge.ide.theme_workspace_stylesheet import (
    build_workspace_stylesheet,
)
from pycforge.ide.visual_tokens import color_tokens


ROOT = Path(__file__).resolve().parents[1]
ICON_ROOT = ROOT / "pycforge" / "ide" / "resources" / "icons"

PHASE15B_ICON_IDS = frozenset(
    {
        "about",
        "add-document",
        "brand-mark",
        "cancel",
        "check",
        "chevron-right",
        "close",
        "collapse-all",
        "convert",
        "copy",
        "cut",
        "decision-trace",
        "details",
        "diagnostics",
        "exit",
        "expand-all",
        "find",
        "go-to-output",
        "go-to-source",
        "link-c",
        "mappings",
        "module",
        "move-down",
        "move-up",
        "next-match",
        "open",
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
        "summary",
        "telemetry",
        "undo",
        "view-c",
    }
)

PHASE15C_ICON_IDS = frozenset(
    {
        "bundle-search",
        "command-palette",
        "duplicate-line",
        "go-to-line",
        "history",
        "indent",
        "move-line-down",
        "move-line-up",
        "outline",
        "outdent",
        "split-view",
        "toggle-comment",
        "toggle-fold",
        "whitespace",
    }
)

PHASE15C_ACTION_ICONS = {
    "edit.duplicate_line": "duplicate-line",
    "edit.move_line_up": "move-line-up",
    "edit.move_line_down": "move-line-down",
    "edit.indent": "indent",
    "edit.outdent": "outdent",
    "edit.toggle_comment": "toggle-comment",
    "search.bundle": "bundle-search",
    "view.outline": "outline",
    "view.conversion_history": "history",
    "view.whitespace": "whitespace",
    "view.split_source": "split-view",
    "editor.toggle_fold": "toggle-fold",
    "navigation.go_to_line": "go-to-line",
    "workspace.command_palette": "command-palette",
    "mappings.reveal_source": "go-to-source",
}

UNSAFE_RESOURCE_REFERENCE = re.compile(
    r"(?i)(?:data:|https?://|file:|javascript:)"
)


def local_name(expanded_name: str) -> str:
    return expanded_name.rsplit("}", 1)[-1]


class Phase15CVisualSystemTests(unittest.TestCase):
    def test_visual_identity_and_svg_inventory_are_exact(self) -> None:
        self.assertEqual(
            VISUAL_SYSTEM_VERSION,
            "pycforge.visual-system/0.2",
        )
        self.assertEqual(len(PHASE15B_ICON_IDS), 41)
        self.assertEqual(len(PHASE15C_ICON_IDS), 14)
        self.assertTrue(PHASE15B_ICON_IDS.isdisjoint(PHASE15C_ICON_IDS))
        self.assertEqual(len(PYCFORGE_ICON_FILES), 55)
        self.assertEqual(
            set(PYCFORGE_ICON_FILES),
            PHASE15B_ICON_IDS | PHASE15C_ICON_IDS,
        )
        self.assertEqual(
            set(PYCFORGE_ICON_FILES).difference(PHASE15B_ICON_IDS),
            PHASE15C_ICON_IDS,
        )
        self.assertEqual(
            len(PYCFORGE_ICON_FILES),
            len(set(PYCFORGE_ICON_FILES.values())),
        )
        self.assertEqual(pycforge_icon_root().resolve(), ICON_ROOT.resolve())
        self.assertEqual(
            {path.name for path in ICON_ROOT.glob("*.svg")},
            set(PYCFORGE_ICON_FILES.values()),
        )

    def test_all_55_packaged_icons_are_safe_scalable_vectors(self) -> None:
        forbidden_elements = {
            "foreignObject",
            "image",
            "script",
            "style",
            "text",
        }
        allowed_colors = set(color_tokens().values())
        paths = sorted(ICON_ROOT.glob("*.svg"))
        self.assertEqual(len(paths), 55)
        for path in paths:
            with self.subTest(icon=path.name):
                document = path.read_text(encoding="utf-8")
                root = ET.fromstring(document)
                self.assertEqual(local_name(root.tag), "svg")
                self.assertEqual(root.attrib.get("viewBox"), "0 0 24 24")
                self.assertNotIn("width", root.attrib)
                self.assertNotIn("height", root.attrib)
                self.assertTrue(list(root))
                for element in root.iter():
                    self.assertNotIn(
                        local_name(element.tag),
                        forbidden_elements,
                    )
                    for attribute, value in element.attrib.items():
                        attribute_name = local_name(attribute)
                        self.assertNotIn(
                            attribute_name,
                            {"href", "src"},
                        )
                        self.assertIsNone(
                            UNSAFE_RESOURCE_REFERENCE.search(value)
                        )
                        if (
                            attribute_name in {"fill", "stroke"}
                            and value != "none"
                        ):
                            self.assertIn(value, allowed_colors)
                        if attribute_name == "stroke-width":
                            self.assertGreaterEqual(float(value), 1.5)
                            self.assertLessEqual(float(value), 2.0)

    def test_every_declared_action_icon_resolves_to_a_packaged_svg(
        self,
    ) -> None:
        for action_id, spec in ACTION_SPECS.items():
            if spec.icon_name is None:
                continue
            with self.subTest(action_id=action_id):
                self.assertIn(spec.icon_name, PYCFORGE_ICON_FILES)
                path = pycforge_icon_path(spec.icon_name)
                self.assertTrue(path.is_file())
                self.assertEqual(path.suffix, ".svg")

    def test_phase15c_actions_use_the_exact_visual_additions(self) -> None:
        self.assertEqual(len(PHASE15C_ACTION_ICONS), 15)
        for action_id, icon_name in PHASE15C_ACTION_ICONS.items():
            with self.subTest(action_id=action_id):
                self.assertEqual(
                    ACTION_SPECS[action_id].icon_name,
                    icon_name,
                )
                self.assertTrue(pycforge_icon_path(icon_name).is_file())

    def test_workspace_styles_cover_tabs_breadcrumbs_and_result_views(
        self,
    ) -> None:
        workspace_qss = build_workspace_stylesheet()
        selectors = (
            "QTabBar#SourceDocumentTabs",
            "QTabBar#SourceDocumentTabs::tab:hover",
            "QTabBar#SourceDocumentTabs::tab:selected",
            "QTabBar#SourceDocumentTabs:focus",
            "QWidget#SourceBreadcrumbBar",
            "QToolButton#BreadcrumbButton:hover",
            "QToolButton#BreadcrumbButton:focus",
            "QLabel#BreadcrumbSeparator",
            "QDialog#CommandPaletteDialog",
            "QLineEdit#CommandPaletteQuery",
            "QTreeWidget#CommandPaletteResults",
            "QTreeWidget#BundleSearchTree",
            "QTreeWidget#OutlineTree",
            "QTreeWidget#SessionHistoryTree",
            "QWidget#BundleSearchView",
            "QWidget#OutlineView",
            "QWidget#SessionHistoryView",
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, workspace_qss)
                self.assertIn(selector, PYCFORGE_QSS)
        self.assertNotIn("${", workspace_qss)
        self.assertEqual(PYCFORGE_QSS, build_pycforge_stylesheet())


if __name__ == "__main__":
    unittest.main()
