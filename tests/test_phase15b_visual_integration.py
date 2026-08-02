from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from pycforge.ide.panels import (
    INSPECTOR_TREE_MAX_CHILDREN,
    INSPECTOR_TREE_MAX_DEPTH,
    INSPECTOR_TREE_MAX_NODES,
    INSPECTOR_TREE_MAX_TEXT_CHARS,
    project_inspector_tree,
)


ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    name: (ROOT / f"pycforge/ide/{name}.py").read_text(encoding="utf-8")
    for name in (
        "editor",
        "editor_sidebars",
        "editor_syntax",
        "find_replace",
        "panels",
    )
}


class Phase15BVisualIntegrationTests(unittest.TestCase):
    def test_modules_parse_and_keep_visual_values_centralized(self) -> None:
        color_literal = re.compile(r"#[0-9A-Fa-f]{6}\b")
        for name, source in MODULES.items():
            with self.subTest(module=name):
                ast.parse(source, filename=f"{name}.py")
                self.assertIsNone(color_literal.search(source))
        for name in ("editor", "editor_syntax", "panels"):
            with self.subTest(token_consumer=name):
                self.assertIn(
                    ".visual_tokens import PYCFORGE_COLORS",
                    MODULES[name],
                )

    def test_editor_and_find_bar_delegate_styling_to_the_theme(self) -> None:
        self.assertNotIn("setStyleSheet(", MODULES["editor"])
        self.assertNotIn("setStyleSheet(", MODULES["find_replace"])
        self.assertIn(
            'self.setProperty("role", "code-editor")',
            MODULES["editor"],
        )
        self.assertIn(
            'self.setProperty("role", "find-bar")',
            MODULES["find_replace"],
        )

    def test_find_and_navigator_shortcuts_are_registry_owned(self) -> None:
        for name in ("find_replace", "panels"):
            with self.subTest(module=name):
                self.assertNotIn("QShortcut", MODULES[name])
                self.assertIn(
                    "def bind_action_registry(self, registry: Any)",
                    MODULES[name],
                )

        find_source = MODULES["find_replace"]
        for action_id in (
            "search.previous_match",
            "search.next_match",
            "search.replace_current",
            "search.replace_all",
            "search.close",
        ):
            with self.subTest(action_id=action_id):
                self.assertIn(f'"{action_id}"', find_source)
                self.assertIn(
                    "registry.attach_to_widget(action_id, self)",
                    find_source,
                )

        navigator_source = MODULES["panels"]
        for action_id in (
            "bundle.new_module",
            "bundle.remove_module",
            "bundle.move_up",
            "bundle.move_down",
        ):
            with self.subTest(action_id=action_id):
                self.assertIn(f'"{action_id}"', navigator_source)
        self.assertIn(
            'registry.attach_to_widget("bundle.move_up", self)',
            navigator_source,
        )
        self.assertIn(
            'registry.attach_to_widget("bundle.move_down", self)',
            navigator_source,
        )

    def test_icon_controls_are_named_and_use_catalogue_assets(self) -> None:
        find_source = MODULES["find_replace"]
        for icon_name in (
            "previous-match",
            "next-match",
            "replace",
            "close",
        ):
            with self.subTest(find_icon=icon_name):
                self.assertIn(f'"{icon_name}"', find_source)
        for contract in (
            'button.setText("" if icon_only else text)',
            "button.setToolTip(tooltip)",
            "button.setAccessibleName(tooltip)",
            "Qt.ToolButtonIconOnly",
        ):
            with self.subTest(find_contract=contract):
                self.assertIn(contract, find_source)

        panels_source = MODULES["panels"]
        for icon_name in (
            "add-document",
            "remove-document",
            "move-up",
            "move-down",
            "primary-module",
            "module",
            "close",
        ):
            with self.subTest(panel_icon=icon_name):
                self.assertIn(f'"{icon_name}"', panels_source)
        for pseudo_icon in ("◆", "◇", "×"):
            with self.subTest(pseudo_icon=pseudo_icon):
                self.assertNotIn(pseudo_icon, panels_source)


class Phase15BInspectorProjectionTests(unittest.TestCase):
    def test_projection_has_absolute_default_budgets(self) -> None:
        self.assertGreaterEqual(INSPECTOR_TREE_MAX_NODES, 256)
        self.assertLessEqual(INSPECTOR_TREE_MAX_NODES, 2048)
        self.assertGreaterEqual(INSPECTOR_TREE_MAX_DEPTH, 8)
        self.assertLessEqual(INSPECTOR_TREE_MAX_DEPTH, 32)
        self.assertGreaterEqual(INSPECTOR_TREE_MAX_CHILDREN, 64)
        self.assertLessEqual(INSPECTOR_TREE_MAX_CHILDREN, 512)
        self.assertGreaterEqual(INSPECTOR_TREE_MAX_TEXT_CHARS, 256)
        self.assertLessEqual(INSPECTOR_TREE_MAX_TEXT_CHARS, 4096)

    def test_projection_is_node_child_and_text_bounded(self) -> None:
        nodes = project_inspector_tree(
            {
                "items": list(range(100)),
                "long": "x" * 200,
            },
            max_nodes=12,
            max_depth=4,
            max_children=3,
            max_text_chars=24,
        )
        self.assertLessEqual(len(nodes), 12)
        self.assertTrue(
            any("additional" in node.value for node in nodes)
        )
        self.assertTrue(any(node.value.endswith("…") for node in nodes))
        self.assertTrue(
            all(
                len(node.key) <= 24 and len(node.value) <= 24
                for node in nodes
            )
        )

    def test_projection_reserves_a_node_limit_notice(self) -> None:
        nodes = project_inspector_tree(
            list(range(100)),
            max_nodes=7,
            max_children=100,
            max_text_chars=64,
        )
        self.assertEqual(len(nodes), 7)
        self.assertIn("node limit reached", nodes[-1].value)
        self.assertEqual(nodes[-1].parent_index, 0)

    def test_projection_is_cycle_safe_and_depth_bounded(self) -> None:
        cyclic: list[object] = []
        cyclic.append(cyclic)
        nodes = project_inspector_tree(cyclic, max_nodes=8)
        self.assertEqual(len(nodes), 2)
        self.assertIn("reference to node", nodes[-1].value)

        nested: dict[str, object] = {}
        cursor = nested
        for index in range(20):
            child: dict[str, object] = {}
            cursor[str(index)] = child
            cursor = child
        nodes = project_inspector_tree(
            nested,
            max_nodes=30,
            max_depth=3,
        )
        self.assertTrue(
            any("depth limit reached" in node.value for node in nodes)
        )
        self.assertLessEqual(len(nodes), 5)

    def test_projection_rejects_invalid_budgets(self) -> None:
        invalid = (
            {"max_nodes": 1},
            {"max_depth": -1},
            {"max_children": 0},
            {"max_text_chars": 7},
        )
        for limits in invalid:
            with self.subTest(limits=limits):
                with self.assertRaises(ValueError):
                    project_inspector_tree({}, **limits)


if __name__ == "__main__":
    unittest.main()
