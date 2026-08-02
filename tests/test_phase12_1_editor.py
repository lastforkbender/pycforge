from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.editor import (
    CodeEditor,
    EditorMarker,
    QT_AVAILABLE as EDITOR_QT_AVAILABLE,
    lexical_protected_spans,
    normalize_markers,
    qt_position_length,
)
from pycforge.ide.find_replace import (
    FindReplaceBar,
    QT_AVAILABLE as FIND_QT_AVAILABLE,
    find_literal_ranges,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase121EditorComponentTests(unittest.TestCase):
    def test_marker_normalization_clips_drops_empty_and_preserves_roles(self):
        markers = normalize_markers(
            [
                (-3, 2),
                (8, 99),
                (4, 4),
                EditorMarker(2, 5, kind="warning", message="bounded"),
            ],
            text_length=10,
            kind="search",
        )
        self.assertEqual(
            markers,
            (
                EditorMarker(0, 2, kind="search"),
                EditorMarker(8, 10, kind="search"),
                EditorMarker(2, 5, kind="warning", message="bounded"),
            ),
        )
        with self.assertRaisesRegex(ValueError, "exactly start and end"):
            normalize_markers([(1, 2, 3)], text_length=10, kind="search")

    def test_literal_search_is_case_and_identifier_boundary_aware(self):
        text = "alpha ALPHA alphabet alpha_ alpha\nalpha"
        self.assertEqual(
            find_literal_ranges(text, "alpha"),
            ((0, 5), (6, 11), (12, 17), (21, 26), (28, 33), (34, 39)),
        )
        self.assertEqual(
            find_literal_ranges(text, "alpha", match_case=True),
            ((0, 5), (12, 17), (21, 26), (28, 33), (34, 39)),
        )
        self.assertEqual(
            find_literal_ranges(text, "alpha", whole_word=True),
            ((0, 5), (6, 11), (28, 33), (34, 39)),
        )
        self.assertEqual(find_literal_ranges(text, ""), ())
        self.assertEqual(find_literal_ranges("a+b aab", "a+b"), ((0, 3),))

    def test_optional_qt_modules_agree_and_import_headlessly(self):
        self.assertEqual(EDITOR_QT_AVAILABLE, FIND_QT_AVAILABLE)
        if not EDITOR_QT_AVAILABLE:
            with self.assertRaisesRegex(RuntimeError, "PyQt5 is required"):
                CodeEditor()
            with self.assertRaisesRegex(RuntimeError, "PyQt5 is required"):
                FindReplaceBar()

    def test_editor_positions_and_lexical_layers_handle_real_source_text(self):
        self.assertEqual(qt_position_length("a🚀b"), 4)
        self.assertEqual(
            lexical_protected_spans('value = "# visible"  # comment', "python"),
            (((8, 19),), 21),
        )
        self.assertEqual(
            lexical_protected_spans('const char *s = "http://x"; // comment', "c"),
            (((16, 26),), 28),
        )
        with self.assertRaises(ValueError):
            lexical_protected_spans("text", "unknown")

    def test_widget_sources_publish_the_integration_surface(self):
        expected = {
            "CodeEditor": {
                "set_language",
                "set_search_ranges",
                "set_diagnostic_ranges",
                "set_mapping_ranges",
                "clear_markers",
                "markers",
                "go_to_position",
            },
            "FindReplaceBar": {
                "attach_editor",
                "open_find",
                "close_bar",
                "set_replace_visible",
                "next_match",
                "previous_match",
                "replace_current",
                "replace_all",
            },
        }
        discovered: dict[str, set[str]] = {}
        for relative in ("pycforge/ide/editor.py", "pycforge/ide/find_replace.py"):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name in expected:
                    methods = {
                        item.name
                        for item in node.body
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    }
                    if methods:
                        discovered.setdefault(node.name, set()).update(methods)
        for class_name, methods in expected.items():
            self.assertTrue(methods <= discovered[class_name])


if __name__ == "__main__":
    unittest.main()
