from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from pycforge.ide.source_editing import (
    SourceEditResult,
    clamped_go_to_line_offset,
    duplicate_lines,
    indent_lines,
    move_lines_down,
    move_lines_up,
    outdent_lines,
    toggle_python_line_comment,
)


class Phase15CSourceEditingTests(unittest.TestCase):
    def test_duplicate_current_and_selected_lines_preserves_line_endings(self):
        single = duplicate_lines("alpha", 2, 2)
        self.assertEqual(single.text, "alpha\nalpha")
        self.assertEqual(single.selection, (8, 8))

        selected = duplicate_lines("a\r\nbb\r\nc", 0, 5)
        self.assertEqual(selected.text, "a\r\nbb\r\na\r\nbb\r\nc")
        self.assertEqual(
            selected.text[
                selected.selection_start : selected.selection_end
            ],
            "a\r\nbb",
        )

        trailing = duplicate_lines("a\n", 2, 2)
        self.assertEqual(trailing.text, "a\n\n")
        self.assertEqual(trailing.selection, (3, 3))

    def test_move_lines_handles_lf_crlf_and_document_edges(self):
        moved = move_lines_up("a\nbb\nc", 2, 4)
        self.assertEqual(moved.text, "bb\na\nc")
        self.assertEqual(
            moved.text[moved.selection_start : moved.selection_end],
            "bb",
        )
        self.assertEqual(
            move_lines_up("a\nb", 0, 0),
            SourceEditResult("a\nb", 0, 0),
        )

        moved = move_lines_down("a\r\nbb\r\nc", 0, 1)
        self.assertEqual(moved.text, "bb\r\na\r\nc")
        self.assertEqual(
            moved.text[moved.selection_start : moved.selection_end],
            "a",
        )
        self.assertEqual(
            move_lines_down("a\nb", 2, 3),
            SourceEditResult("a\nb", 2, 3),
        )

    def test_indent_and_outdent_preserve_semantic_selection(self):
        empty = indent_lines("", 0, 0)
        self.assertEqual(empty, SourceEditResult("    ", 4, 4))

        source = "if ready:\r\n    value = 1\r\n\r\n"
        indented = indent_lines(source, 0, len(source))
        self.assertEqual(
            indented.text,
            "    if ready:\r\n        value = 1\r\n\r\n",
        )
        self.assertEqual(indented.selection_start, 4)
        self.assertEqual(indented.selection_end, len(indented.text))

        outdented = outdent_lines(
            "\tfirst\n  second\n        third",
            0,
            29,
        )
        self.assertEqual(
            outdented.text,
            "first\nsecond\n    third",
        )
        self.assertEqual(outdented.selection_start, 0)
        self.assertEqual(outdented.selection_end, len(outdented.text))

    def test_toggle_comment_skips_blank_lines_and_round_trips(self):
        source = "def value():\n    return 1\n\n"
        commented = toggle_python_line_comment(source, 0, len(source))
        self.assertEqual(
            commented.text,
            "# def value():\n    # return 1\n\n",
        )
        restored = toggle_python_line_comment(
            commented.text,
            commented.selection_start,
            commented.selection_end,
        )
        self.assertEqual(restored.text, source)
        self.assertEqual(restored.selection, (0, len(source)))

        mixed = toggle_python_line_comment("# first\nsecond", 0, 14)
        self.assertEqual(mixed.text, "# # first\n# second")

    def test_go_to_line_is_one_based_and_clamped(self):
        text = "one\r\ntwo\r\n"
        self.assertEqual(clamped_go_to_line_offset(text, -20), 0)
        self.assertEqual(clamped_go_to_line_offset(text, 1), 0)
        self.assertEqual(clamped_go_to_line_offset(text, 2), 5)
        self.assertEqual(clamped_go_to_line_offset(text, 3), len(text))
        self.assertEqual(clamped_go_to_line_offset(text, 99), len(text))
        with self.assertRaises(TypeError):
            clamped_go_to_line_offset(text, True)

    def test_results_are_frozen_and_input_selections_are_clamped(self):
        result = indent_lines("x", -100, 100)
        self.assertEqual(result, SourceEditResult("    x", 4, 5))
        with self.assertRaises(FrozenInstanceError):
            result.text = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
