from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "pycforge/ide/qt_workspace_panels.py"


def method_node(
    tree: ast.AST,
    class_name: str,
    method_name: str,
) -> ast.FunctionDef:
    class_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == class_name
    )
    return next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
        and node.name == method_name
    )


class Phase15CQtPanelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PANEL_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(PANEL_PATH))

    def test_optional_module_is_direct_qt_bounded_and_parseable(
        self,
    ) -> None:
        self.assertLess(len(self.source.splitlines()), 600)
        self.assertIn("from PyQt5.QtCore import", self.source)
        self.assertIn("from PyQt5.QtWidgets import", self.source)
        self.assertNotIn("try:\n    from PyQt5", self.source)
        classes = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ClassDef)
        }
        self.assertTrue(
            {"OutlineView", "BundleSearchView", "SessionHistoryView"}
            .issubset(classes)
        )

    def test_all_projection_trees_are_uniform_accessible_context_targets(
        self,
    ) -> None:
        self.assertEqual(
            self.source.count("setUniformRowHeights(True)"),
            3,
        )
        for declaration in (
            'self.tree.setObjectName("OutlineTree")',
            'self.tree.setObjectName("BundleSearchTree")',
            'self.tree.setObjectName("SessionHistoryTree")',
            "self.tree.setAccessibleName(",
            "self.tree.itemActivated.connect(",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, self.source)
        self.assertNotIn("createStandardContextMenu", self.source)

    def test_outline_uses_parent_ids_bounds_filter_and_small_activation(
        self,
    ) -> None:
        method = method_node(
            self.tree, "OutlineView", "set_result"
        )
        method_source = ast.get_source_segment(
            self.source, method
        ) or ""
        self.assertIn(
            "result.symbols[:MAX_OUTLINE_SYMBOLS]", method_source
        )
        self.assertIn("symbol.parent_node_id", method_source)
        self.assertIn("parent_item.addChild(item)", method_source)
        self.assertNotIn("symbol.provenance", method_source)
        self.assertIn(
            "symbolActivated = pyqtSignal(str, int, int)",
            self.source,
        )
        self.assertIn("self.filter_edit.textChanged.connect", self.source)
        self.assertIn("observer_failed_document_ids", method_source)

    def test_bundle_search_captures_text_only_and_is_generation_safe(
        self,
    ) -> None:
        set_documents = ast.get_source_segment(
            self.source,
            method_node(
                self.tree, "BundleSearchView", "set_documents"
            ),
        ) or ""
        submit = ast.get_source_segment(
            self.source,
            method_node(
                self.tree, "BundleSearchView", "_submit_search"
            ),
        ) or ""
        apply_result = ast.get_source_segment(
            self.source,
            method_node(
                self.tree, "BundleSearchView", "_apply_result"
            ),
        ) or ""
        self.assertIn("WorkspaceSearchDocument(", set_documents)
        self.assertIn('getattr(record, "text", None)', set_documents)
        self.assertNotIn('getattr(record, "path"', set_documents)
        self.assertNotIn(".read_", set_documents)
        self.assertNotIn("open(", set_documents)
        self.assertIn("AsyncBundleSearchService()", self.source)
        self.assertIn("self._search_service.cancel()", self.source)
        self.assertIn("self._search_timer.setInterval(150)", self.source)
        self.assertIn(
            "self.query_edit.setMaxLength(MAX_QUERY_CHARS)",
            self.source,
        )
        self.assertIn("callback=self._searchCompleted.emit", submit)
        self.assertIn(
            "result.generation != self._expected_generation",
            apply_result,
        )
        self.assertIn(
            "matchActivated = pyqtSignal(str, int, int)",
            self.source,
        )
        self.assertIn("def close_service(", self.source)
        self.assertIn("def closeEvent(", self.source)

    def test_history_projection_is_exactly_bounded_and_payload_free(
        self,
    ) -> None:
        method = method_node(
            self.tree, "SessionHistoryView", "set_entries"
        )
        method_source = ast.get_source_segment(
            self.source, method
        ) or ""
        self.assertIn("MAX_CONVERSION_HISTORY_ENTRIES + 1", method_source)
        self.assertIn("ConversionHistoryEntry", method_source)
        self.assertIn(
            "entry.request_sequence", method_source
        )
        self.assertNotIn("self._entries", method_source)
        self.assertNotIn("generated_c", method_source)
        self.assertNotIn("source_text", method_source)
        self.assertNotIn("diagnostics=", method_source)
        self.assertIn(
            "historyActivated = pyqtSignal(int)",
            self.source,
        )

    def test_static_contract_makes_no_widget_runtime_claim(
        self,
    ) -> None:
        imported_roots = {
            (node.module or "").split(".")[0]
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("pathlib", imported_roots)
        self.assertNotIn("subprocess", imported_roots)
        self.assertNotIn("platform", imported_roots)
        self.assertNotIn("visible platform", self.source.casefold())


if __name__ == "__main__":
    unittest.main()
