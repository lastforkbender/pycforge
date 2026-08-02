from __future__ import annotations

import unittest
from pathlib import Path

from pycforge.ide.panels import (
    DiagnosticsView,
    DocumentNavigator,
    InspectorTree,
    MappingsView,
    QT_AVAILABLE as PANELS_QT_AVAILABLE,
    ToastBanner,
)
from pycforge.ide.qt import (
    QT_AVAILABLE,
    _coerce_settings_schema_version,
    diagnostic_character_range,
    line_column_offset,
    mapping_character_range,
    python_offset_to_qt_position,
)


ROOT = Path(__file__).resolve().parents[1]


class PyCForgeQtIntegrationTests(unittest.TestCase):
    def test_settings_schema_version_coercion_is_bounded_and_strict(self):
        self.assertEqual(_coerce_settings_schema_version(1), 1)
        self.assertEqual(_coerce_settings_schema_version("1"), 1)
        for value in (True, False, "1.0", "-1", "", "1" * 17, [], None):
            with self.subTest(value=value):
                self.assertIsNone(_coerce_settings_schema_version(value))

    def test_active_workspace_uses_pycforge_branding(self):
        sources = {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "pycforge/ide/editor.py",
                "pycforge/ide/panels.py",
                "pycforge/ide/qt.py",
                "pycforge/ide/theme.py",
                "pycforge/ide/visual_tokens.py",
            )
        }
        required = {
            "pycforge/ide/editor.py": "class PyCForgeSyntaxHighlighter",
            "pycforge/ide/panels.py": '"""PyCForge workspace',
            "pycforge/ide/qt.py": 'self.setObjectName("PyCForgeMainWindow")',
            "pycforge/ide/theme.py": "PYCFORGE_QSS = build_pycforge_stylesheet()",
            "pycforge/ide/visual_tokens.py": "class PyCForgeColors",
        }
        for relative, contract in required.items():
            with self.subTest(relative=relative):
                self.assertIn(contract, sources[relative])
        qt_source = sources["pycforge/ide/qt.py"]
        for contract in (
            'self.setWindowTitle(f"PyCForge {__version__} — Workspace")',
            'toolbar.setObjectName("PyCForgeToolbar")',
            'app.setApplicationName("PyCForge")',
            "apply_pycforge_theme(app)",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, qt_source)

    def test_line_column_offsets_are_character_not_utf8_byte_positions(self):
        text = "αβ\néx\n"
        self.assertEqual(line_column_offset(text, 1, 1), 1)
        self.assertEqual(line_column_offset(text, 2, 1), 4)
        self.assertEqual(line_column_offset(text, 99, 99), len(text))
        self.assertEqual(line_column_offset(text, 0, 9), 0)

        mapping = {
            "start_byte": 999,
            "end_byte": 1_111,
            "start_line": 2,
            "start_column": 0,
            "end_line": 2,
            "end_column": 2,
        }
        self.assertEqual(mapping_character_range(mapping, text), (3, 5))
        self.assertEqual(python_offset_to_qt_position("a🚀b", 2), 3)
        self.assertEqual(python_offset_to_qt_position("a🚀b", 99), 4)

    def test_diagnostic_ranges_prefer_exact_offsets_and_clip_safely(self):
        text = "def f():\n    pass\n"
        diagnostic = {
            "source_span": {
                "start": {"line": 99, "column": 99, "offset": 4},
                "end": {"line": 99, "column": 99, "offset": 7},
            }
        }
        self.assertEqual(diagnostic_character_range(diagnostic, text), (4, 7))
        self.assertEqual(
            diagnostic_character_range(
                {
                    "source_span": {
                        "start": {"line": 2, "column": 4},
                        "end": {"line": 2, "column": 8},
                    }
                },
                text,
            ),
            (13, 17),
        )

    def test_optional_panel_surface_is_consistently_headless_safe(self):
        self.assertEqual(QT_AVAILABLE, PANELS_QT_AVAILABLE)
        if not QT_AVAILABLE:
            for widget in (
                DocumentNavigator,
                DiagnosticsView,
                InspectorTree,
                MappingsView,
                ToastBanner,
            ):
                with self.subTest(widget=widget.__name__):
                    with self.assertRaisesRegex(RuntimeError, "PyQt5 is required"):
                        widget()

    def test_main_window_wires_the_professional_workspace_surface(self):
        source = (ROOT / "pycforge/ide/qt.py").read_text(encoding="utf-8")
        required = (
            "CodeEditor(language=\"python\")",
            "CodeEditor(language=\"c\")",
            "DocumentNavigator()",
            "FindReplaceBar()",
            "DiagnosticsView()",
            "MappingsView()",
            "apply_pycforge_theme(app)",
            "QFileSystemWatcher",
            "QSettings",
            '"modules.resolve": "Resolving module bundle"',
            "save_generated_c_linked",
            "snapshot.can_save_c",
            "diagnostic_character_range",
            "mapping_character_range",
            "self.output.setReadOnly(True)",
            "self.output.setVisible(False)",
            "self.tabs.setVisible(False)",
        )
        for feature in required:
            with self.subTest(feature=feature):
                self.assertIn(feature, source)
        self.assertNotIn("json.dumps", source)
        self.assertNotIn("QPlainTextEdit", source)
        self.assertNotIn("QProgressDialog", source)

    def test_workspace_contains_no_execution_or_host_import_controls(self):
        source = (ROOT / "pycforge/ide/qt.py").read_text(encoding="utf-8")
        for label in (
            "Execute Python",
            "Compile C",
            "Load library",
            "Inspect installed package",
            "Resolve host import",
        ):
            with self.subTest(label=label):
                self.assertNotIn(label, source)


if __name__ == "__main__":
    unittest.main()
