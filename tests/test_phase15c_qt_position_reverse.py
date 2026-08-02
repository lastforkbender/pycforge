from __future__ import annotations

import unittest

from pycforge.ide.positions import build_text_position_index
from pycforge.ide.qt_contract import (
    python_offset_to_qt_position,
    qt_position_to_python_offset,
)


class _SliceRecordingText(str):
    def __new__(cls, value: str):
        instance = super().__new__(cls, value)
        instance.slices = []
        return instance

    def __getitem__(self, key):
        if isinstance(key, slice):
            self.slices.append(key)
        return super().__getitem__(key)


class Phase15CQtPositionReverseTests(unittest.TestCase):
    def test_ascii_positions_are_clamped_character_offsets(self) -> None:
        text = "alpha\nbeta"
        index = build_text_position_index(text)
        for position in range(len(text) + 1):
            with self.subTest(position=position):
                self.assertEqual(
                    qt_position_to_python_offset(text, position),
                    position,
                )
                self.assertEqual(
                    qt_position_to_python_offset(text, position, index),
                    position,
                )
        self.assertEqual(qt_position_to_python_offset(text, -20), 0)
        self.assertEqual(
            qt_position_to_python_offset(text, len(text) + 20),
            len(text),
        )
        with self.assertRaises(TypeError):
            qt_position_to_python_offset(text, 1.5)  # type: ignore[arg-type]

    def test_astral_surrogate_interior_clamps_to_codepoint_start(self) -> None:
        text = "a\U0001f680b"
        index = build_text_position_index(text)
        expected = {
            0: 0,
            1: 1,
            2: 1,
            3: 2,
            4: 3,
            5: 3,
        }
        for qt_position, python_offset in expected.items():
            with self.subTest(qt_position=qt_position):
                self.assertEqual(
                    qt_position_to_python_offset(text, qt_position),
                    python_offset,
                )
                self.assertEqual(
                    qt_position_to_python_offset(
                        text,
                        qt_position,
                        index,
                    ),
                    python_offset,
                )

    def test_line_boundaries_match_with_and_without_index(self) -> None:
        text = "a\U0001f680\nb\U00010400c\n"
        index = build_text_position_index(text)
        self.assertEqual(index.line_starts, (0, 3, 7))
        self.assertEqual(index.utf16_line_starts, (0, 4, 9))
        utf16_length = len(text.encode("utf-16-le")) // 2
        for position in range(utf16_length + 2):
            with self.subTest(position=position):
                self.assertEqual(
                    qt_position_to_python_offset(text, position, index),
                    qt_position_to_python_offset(text, position),
                )
        self.assertEqual(
            qt_position_to_python_offset(
                text,
                index.utf16_line_starts[1],
                index,
            ),
            index.line_starts[1],
        )
        self.assertEqual(
            qt_position_to_python_offset(
                text,
                index.utf16_line_starts[2],
                index,
            ),
            index.line_starts[2],
        )

    def test_every_python_boundary_round_trips_through_qt(self) -> None:
        text = "\n\U0001f680 alpha\nbeta \U00010400\nomega"
        index = build_text_position_index(text)
        for offset in range(len(text) + 1):
            qt_position = python_offset_to_qt_position(
                text,
                offset,
                index,
            )
            with self.subTest(offset=offset, qt_position=qt_position):
                self.assertEqual(
                    qt_position_to_python_offset(
                        text,
                        qt_position,
                        index,
                    ),
                    offset,
                )

    def test_indexed_astral_lookup_scans_only_the_target_line(self) -> None:
        original = (
            ("prefix\n" * 2_000)
            + "target \U0001f680 value\n"
            + ("suffix\n" * 2_000)
        )
        index = build_text_position_index(original)
        line_index = 2_000
        text = _SliceRecordingText(original)
        target = index.utf16_line_starts[line_index] + 9
        offset = qt_position_to_python_offset(text, target, index)
        self.assertEqual(
            offset,
            index.line_starts[line_index] + len("target \U0001f680"),
        )
        self.assertEqual(len(text.slices), 1)
        self.assertEqual(
            text.slices[0],
            slice(
                index.line_starts[line_index],
                index.line_starts[line_index + 1],
            ),
        )

    def test_mismatched_index_falls_back_to_exact_text(self) -> None:
        text = "a\U0001f680b"
        stale = build_text_position_index("different")
        self.assertEqual(
            qt_position_to_python_offset(text, 3, stale),
            2,
        )


if __name__ == "__main__":
    unittest.main()
