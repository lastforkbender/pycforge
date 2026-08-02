from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
QT_MODULES = (
    "qt.py",
    "qt_close.py",
    "qt_contract.py",
    "qt_documents.py",
    "qt_projection.py",
    "qt_shell.py",
    "qt_state.py",
)


class Phase15AQtDecompositionTests(unittest.TestCase):
    def test_qt_modules_are_bounded_and_parse_independently(self) -> None:
        for name in QT_MODULES:
            path = ROOT / "pycforge" / "ide" / name
            source = path.read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertLess(
                    len(source.splitlines()),
                    600,
                    f"{name} exceeded the Phase 15A module budget",
                )
                ast.parse(source, filename=str(path))

    def test_source_change_handler_does_not_copy_the_editor_text(self) -> None:
        source = (
            ROOT / "pycforge" / "ide" / "qt_documents.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn(
            "toPlainText",
            methods["_source_changed"],
        )
        self.assertIn(
            "toPlainText",
            methods["_flush_pending_source_sync"],
        )
        self.assertIn(
            "_source_sync_timer.start()",
            methods["_source_changed"],
        )

    def test_large_output_mode_precedes_chunk_projection(self) -> None:
        source = (
            ROOT / "pycforge" / "ide" / "qt_projection.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertLess(
            source.index("self.output.set_large_file_mode("),
            source.index("self.output.clear()"),
        )
        self.assertNotIn(
            ".count(",
            methods["_start_output_projection"],
        )
        self.assertIn("start + 32_768", source)

    def test_public_qt_module_composes_the_cohesive_mixins(self) -> None:
        source = (
            ROOT / "pycforge" / "ide" / "qt.py"
        ).read_text(encoding="utf-8")
        for contract in (
            "QtShellMixin",
            "QtDocumentActionsMixin",
            "QtProjectionMixin",
            "QtStateMixin",
            "QtCloseMixin",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, source)
        self.assertIn("self._source_sync_timer.setInterval(120)", source)


if __name__ == "__main__":
    unittest.main()
