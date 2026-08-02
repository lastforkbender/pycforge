from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.editor import (
    BRACKET_SCAN_LIMIT,
    LARGE_FILE_BRACKET_SCAN_LIMIT,
    LARGE_FILE_CHARACTER_THRESHOLD,
    LARGE_FILE_EXTRA_SELECTION_LIMIT,
    LARGE_FILE_LINE_THRESHOLD,
    LARGE_FILE_MARKER_STORAGE_LIMIT,
    LARGE_FILE_RAIL_MARKER_LIMIT,
    EditorMarker,
    bounded_marker_projection,
    large_file_mode_required,
    normalize_markers,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase15AEditorLargeFileTests(unittest.TestCase):
    def test_large_file_policy_enters_before_the_resource_ceiling(self) -> None:
        self.assertLessEqual(LARGE_FILE_CHARACTER_THRESHOLD, 250_000)
        self.assertLess(LARGE_FILE_LINE_THRESHOLD, 100_000)
        self.assertFalse(
            large_file_mode_required(
                character_count=LARGE_FILE_CHARACTER_THRESHOLD - 1,
                line_count=LARGE_FILE_LINE_THRESHOLD - 1,
            )
        )
        self.assertTrue(
            large_file_mode_required(
                character_count=LARGE_FILE_CHARACTER_THRESHOLD,
                line_count=1,
            )
        )
        self.assertTrue(
            large_file_mode_required(
                character_count=1,
                line_count=LARGE_FILE_LINE_THRESHOLD,
            )
        )

    def test_marker_normalization_samples_sequences_and_bounds_generators(self) -> None:
        source = tuple((index * 10, index * 10 + 1) for index in range(10))
        self.assertEqual(
            normalize_markers(
                source,
                text_length=100,
                kind="search",
                limit=3,
            ),
            (
                EditorMarker(0, 1, kind="search"),
                EditorMarker(40, 41, kind="search"),
                EditorMarker(90, 91, kind="search"),
            ),
        )

        consumed: list[int] = []

        def records():
            for index in range(100_000):
                consumed.append(index)
                yield (index, index + 1)

        projected = normalize_markers(
            records(),
            text_length=100_000,
            kind="diagnostic",
            limit=7,
        )
        self.assertEqual(len(projected), 7)
        self.assertEqual(len(consumed), 7)

    def test_marker_projection_prefers_viewport_and_has_a_hard_limit(self) -> None:
        markers = tuple(
            EditorMarker(index * 10, index * 10 + 3, marker_id=str(index))
            for index in range(100)
        )
        projected = bounded_marker_projection(
            markers,
            limit=8,
            focus_start=400,
            focus_end=430,
        )
        self.assertEqual(len(projected), 8)
        self.assertTrue(
            {
                marker.marker_id
                for marker in markers
                if marker.end >= 400 and marker.start <= 430
            }
            <= {marker.marker_id for marker in projected}
        )
        with self.assertRaisesRegex(ValueError, "must not be negative"):
            bounded_marker_projection(markers, limit=-1)

    def test_widget_source_has_explicit_bounded_large_file_path(self) -> None:
        source = (ROOT / "pycforge/ide/editor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        code_editor = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "CodeEditor"
        )
        methods = {
            node.name: node
            for node in code_editor.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("set_large_file_mode", methods)
        self.assertIn("setPlainText", methods)
        self.assertIn("_viewport_projection_bounds", methods)
        self.assertIn("_rail_markers", methods)

        for method_name in (
            "_document_changed",
            "_bracket_positions",
            "go_to_position",
        ):
            segment = ast.get_source_segment(source, methods[method_name])
            self.assertNotIn("toPlainText", segment)

        bracket_source = ast.get_source_segment(
            source,
            methods["_bracket_positions"],
        )
        self.assertIn("scanned < scan_limit", bracket_source)
        self.assertLess(LARGE_FILE_BRACKET_SCAN_LIMIT, BRACKET_SCAN_LIMIT)
        self.assertLess(
            LARGE_FILE_EXTRA_SELECTION_LIMIT,
            LARGE_FILE_MARKER_STORAGE_LIMIT,
        )
        self.assertLessEqual(LARGE_FILE_RAIL_MARKER_LIMIT, 512)


if __name__ == "__main__":
    unittest.main()
