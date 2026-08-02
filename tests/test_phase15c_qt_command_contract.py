from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.action_contract import ActionState
from pycforge.ide.command_palette import (
    MAX_COMMAND_PALETTE_RESULTS,
    project_command_palette,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "pycforge" / "ide" / "qt_command_palette.py"


class Phase15CQtCommandContractTests(unittest.TestCase):
    def test_optional_adapter_has_declared_dialog_and_entry_points(self):
        source = MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("CommandPaletteDialog", classes)
        self.assertTrue(
            {"open_command_palette", "open_go_to_line"}.issubset(functions)
        )
        self.assertIn("project_command_palette", source)
        self.assertIn("MAX_COMMAND_PALETTE_RESULTS", source)

    def test_adapter_constructs_no_actions_or_free_form_execution_path(self):
        source = MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("QAction", imported)
        self.assertNotIn("QAction", called_names)
        self.assertTrue(
            {"eval", "exec", "compile"}.isdisjoint(called_names)
        )
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("handler", source.casefold())
        self.assertNotIn("callback", source.casefold())
        self.assertIn("self._registry.action(action_id)", source)
        self.assertIn("action.trigger()", source)

    def test_keyboard_and_disabled_action_guards_are_explicit(self):
        source = MODULE.read_text(encoding="utf-8")
        for token in (
            "Qt.Key_Down",
            "Qt.Key_Up",
            "Qt.Key_Return",
            "Qt.Key_Enter",
            "Qt.Key_Escape",
            "item.isDisabled()",
            "action.isEnabled()",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)

    def test_go_to_line_uses_document_blocks_without_source_copy(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("document.blockCount()", source)
        self.assertIn("document.findBlockByNumber(line - 1)", source)
        self.assertIn("QInputDialog.getInt(", source)
        self.assertNotIn("toPlainText", source)
        self.assertNotIn("splitlines", source)

    def test_headless_projection_remains_the_bounded_policy_authority(self):
        states = {
            "file.open_python": ActionState(enabled=False),
            "file.save_python": ActionState(visible=False),
        }
        projection = project_command_palette("open", states=states)
        self.assertLessEqual(
            len(projection.items),
            MAX_COMMAND_PALETTE_RESULTS,
        )
        self.assertTrue(
            all(item.action_id != "file.open_recent" for item in projection.items)
        )
        self.assertTrue(
            all(item.action_id != "file.save_python" for item in projection.items)
        )
        opened = next(
            item
            for item in projection.items
            if item.action_id == "file.open_python"
        )
        self.assertFalse(opened.enabled)

    def test_phase_does_not_assert_visible_platform_evidence(self):
        source = MODULE.read_text(encoding="utf-8").casefold()
        self.assertNotIn("windows 11", source)
        self.assertNotIn("visible linux", source)
        self.assertNotIn("platform gate passed", source)


if __name__ == "__main__":
    unittest.main()
