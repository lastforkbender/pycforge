from __future__ import annotations

from pathlib import Path
from threading import Event
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from pycforge.ide.controller import WorkspaceController
import pycforge.ide.positions as positions
from pycforge.ide.positions import build_text_position_index
from pycforge.ide.qt_contract import (
    line_column_offset,
    python_offset_to_qt_position,
    qt_range,
)


ROOT = Path(__file__).resolve().parents[1]


class _NoSplitText(str):
    def splitlines(self, *args, **kwargs):  # type: ignore[override]
        raise AssertionError("indexed projection rescanned the full document")


class Phase15APositionIndexTests(unittest.TestCase):
    @staticmethod
    def _wait_until(predicate, timeout: float = 5.0) -> bool:
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if predicate():
                return True
            sleep(0.005)
        return bool(predicate())

    def test_indexed_line_and_utf16_positions_match_reference(self) -> None:
        text = "alpha\nbeta \U0001f680 gamma\nomega\n"
        index = build_text_position_index(text)
        for line, column in ((1, 0), (1, 3), (2, 0), (2, 7), (3, 3), (9, 0)):
            with self.subTest(line=line, column=column):
                self.assertEqual(
                    line_column_offset(text, line, column, index),
                    line_column_offset(text, line, column),
                )
        for offset in range(len(text) + 1):
            with self.subTest(offset=offset):
                self.assertEqual(
                    python_offset_to_qt_position(text, offset, index),
                    python_offset_to_qt_position(text, offset),
                )

    def test_indexed_line_lookup_does_not_split_the_document(self) -> None:
        original = "x\n" * 50_000
        index = build_text_position_index(original)
        text = _NoSplitText(original)
        self.assertEqual(
            line_column_offset(text, 49_999, 0, index),
            99_996,
        )

    def test_bmp_text_uses_constant_time_qt_offsets(self) -> None:
        text = "a" * 999_999
        index = build_text_position_index(text)
        self.assertTrue(index.utf16_compatible)
        self.assertEqual(index.qt_position(text, 900_000), 900_000)
        self.assertEqual(
            qt_range(text, 123_456, 900_000, index),
            (123_456, 900_000),
        )

    def test_qt_marker_projection_consumes_cached_indexes(self) -> None:
        source = (
            ROOT / "pycforge" / "ide" / "qt_projection.py"
        ).read_text(encoding="utf-8")
        self.assertIn("source_position_index", source)
        self.assertIn("self.controller.result_output_index", source)
        self.assertNotIn('output_text.count("\\n")', source)

    def test_terminal_result_does_not_wait_for_output_indexing(self) -> None:
        controller = WorkspaceController()
        entered = Event()
        release = Event()
        original = positions.build_text_position_index

        def delayed(text: str, *, cancelled=None):
            entered.set()
            release.wait(3)
            return original(text, cancelled=cancelled)

        try:
            controller.set_source(
                "def value() -> int:\n"
                "    return 7\n"
            )
            self.assertTrue(
                self._wait_until(
                    lambda: controller.snapshot.revision_authenticated
                )
            )
            with patch.object(
                positions,
                "build_text_position_index",
                side_effect=delayed,
            ):
                result = controller.convert_async().result(timeout=20)
                self.assertEqual(result.status.value, "Converted")
                self.assertTrue(entered.wait(2))
                self.assertIsNone(controller.result_output_index)
                release.set()
                self.assertTrue(
                    self._wait_until(
                        lambda: controller.result_output_index is not None
                    )
                )
        finally:
            release.set()
            controller.close(wait=True)


if __name__ == "__main__":
    unittest.main()
