from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EDITOR_MODULES = {
    "editor.py": 1_000,
    "editor_lexical.py": 600,
    "editor_sidebars.py": 600,
    "editor_syntax.py": 600,
}


class Phase15AEditorDecompositionTests(unittest.TestCase):
    def test_editor_modules_are_bounded_and_parse_independently(self) -> None:
        for name, limit in EDITOR_MODULES.items():
            path = ROOT / "pycforge" / "ide" / name
            source = path.read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertLess(
                    len(source.splitlines()),
                    limit,
                    f"{name} exceeded its Phase 15A module budget",
                )
                ast.parse(source, filename=str(path))

    def test_public_editor_surface_remains_at_the_original_module(self) -> None:
        source = (
            ROOT / "pycforge" / "ide" / "editor.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        code_editor = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and node.name == "CodeEditor"
            and any(
                isinstance(item, ast.FunctionDef)
                for item in node.body
            )
        )
        methods = {
            item.name
            for item in code_editor.body
            if isinstance(item, ast.FunctionDef)
        }
        self.assertTrue(
            {
                "set_large_file_mode",
                "setPlainText",
                "_viewport_projection_bounds",
                "_rail_markers",
                "_bracket_positions",
            }
            <= methods
        )
        for exported in (
            '"CodeEditor"',
            '"EditorMarker"',
            '"PyCForgeSyntaxHighlighter"',
            '"bounded_marker_projection"',
            '"large_file_mode_required"',
            '"lexical_protected_spans"',
        ):
            with self.subTest(exported=exported):
                self.assertIn(exported, source)

    def test_private_rendering_helpers_are_cohesive(self) -> None:
        editor = (
            ROOT / "pycforge" / "ide" / "editor.py"
        ).read_text(encoding="utf-8")
        syntax = (
            ROOT / "pycforge" / "ide" / "editor_syntax.py"
        ).read_text(encoding="utf-8")
        sidebars = (
            ROOT / "pycforge" / "ide" / "editor_sidebars.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "from .editor_syntax import PyCForgeSyntaxHighlighter",
            editor,
        )
        self.assertIn(
            "class PyCForgeSyntaxHighlighter(QSyntaxHighlighter)",
            syntax,
        )
        self.assertIn("class _LineNumberArea(QWidget)", sidebars)
        self.assertIn("class _QuantumRail(QWidget)", sidebars)


if __name__ == "__main__":
    unittest.main()
