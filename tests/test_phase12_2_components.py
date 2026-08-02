from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pycforge.ide.editor import (  # noqa: E402 - offscreen platform precedes Qt import
    CodeEditor,
    EditorMarker,
    QT_AVAILABLE as EDITOR_QT_AVAILABLE,
)
from pycforge.ide.panels import (  # noqa: E402
    DocumentNavigator,
    InspectorTree,
    QT_AVAILABLE as PANELS_QT_AVAILABLE,
    ToastBanner,
)
from pycforge.ide.qt_actions import QtActionRegistry  # noqa: E402
from pycforge.ide.theme import PYCFORGE_QSS  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REAL_QT_AVAILABLE = EDITOR_QT_AVAILABLE and PANELS_QT_AVAILABLE

if REAL_QT_AVAILABLE:  # pragma: no branch - selected by the test environment
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication


class Phase122ComponentContractTests(unittest.TestCase):
    def test_navigator_publishes_accessible_reorder_controls_and_signals(self) -> None:
        source = (ROOT / "pycforge/ide/panels.py").read_text(encoding="utf-8")
        for contract in (
            "move_up_requested = pyqtSignal(str)",
            "move_down_requested = pyqtSignal(str)",
            "self.move_up_button",
            "self.move_down_button",
            'setAccessibleName("Move selected module up")',
            'setAccessibleName("Move selected module down")',
            'pycforge_icon_path("move-up")',
            'pycforge_icon_path("move-down")',
            "def bind_action_registry(self, registry: Any)",
            'registry.attach_to_widget("bundle.move_up", self)',
            'registry.attach_to_widget("bundle.move_down", self)',
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, source)

    def test_inspector_toast_and_rail_publish_accessibility_metadata(self) -> None:
        panels = (ROOT / "pycforge/ide/panels.py").read_text(encoding="utf-8")
        editor = (ROOT / "pycforge/ide/editor.py").read_text(encoding="utf-8")
        self.assertIn(
            'self.filter_edit.setAccessibleName(f"Filter {label.casefold()}")',
            panels,
        )
        self.assertIn(
            'self.close_button.setAccessibleName("Dismiss notification")',
            panels,
        )
        self.assertIn('self.setObjectName("QuantumVisibilityRail")', editor)
        self.assertIn("self.setFocusPolicy(Qt.StrongFocus)", editor)
        self.assertIn("self.setAccessibleDescription(", editor)
        self.assertIn("def keyPressEvent(self, event)", editor)

    def test_item_views_have_visible_keyboard_focus_treatment(self) -> None:
        for selector in (
            "QListWidget#DocumentList:focus",
            "QTreeView:focus, QListView:focus, QTableView:focus",
            "QTreeWidget#DiagnosticsTree:focus",
            "QTreeWidget#MappingsTree:focus",
            "QWidget#InspectorTree QTreeWidget:focus",
            "QTreeView:focus::item:selected",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, PYCFORGE_QSS)
        focused_rule = PYCFORGE_QSS.split(
            "QTreeView:focus, QListView:focus, QTableView:focus", 1
        )[1].split("}", 1)[0]
        self.assertIn("#4FB6FF", focused_rule)
        self.assertIn("#A58BFF", focused_rule)


@unittest.skipUnless(REAL_QT_AVAILABLE, "real PyQt5 widgets are unavailable")
class Phase122RealQtComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._owned_app = None
        cls.app = QApplication.instance()
        if cls.app is None:
            cls._owned_app = QApplication(["pycforge-phase12-2-components"])
            cls.app = cls._owned_app

    @staticmethod
    def _document(index: int, *, primary: bool = False) -> SimpleNamespace:
        return SimpleNamespace(
            document_id=f"doc-{index}",
            module_id=f"module_{index}",
            logical_name=f"module_{index}.py",
            path=None,
            dirty=False,
            is_primary=primary,
        )

    def test_reorder_buttons_are_keyboard_operable_and_boundary_aware(self) -> None:
        navigator = DocumentNavigator()
        registry = QtActionRegistry(navigator)
        navigator.bind_action_registry(registry)
        navigator.set_documents(
            (
                self._document(1, primary=True),
                self._document(2),
                self._document(3),
            ),
            "doc-2",
        )
        navigator.resize(320, 560)
        navigator.show()
        self.app.processEvents()

        self.assertEqual(navigator.move_up_button.focusPolicy(), Qt.StrongFocus)
        self.assertEqual(navigator.move_down_button.focusPolicy(), Qt.StrongFocus)
        self.assertTrue(navigator.move_up_button.isEnabled())
        self.assertTrue(navigator.move_down_button.isEnabled())
        self.assertEqual(
            navigator.move_up_button.accessibleName(), "Move selected module up"
        )
        self.assertEqual(
            navigator.move_down_button.accessibleName(), "Move selected module down"
        )
        self.assertIs(
            navigator.move_up_button.defaultAction(),
            registry.action("bundle.move_up"),
        )
        self.assertIs(
            navigator.move_down_button.defaultAction(),
            registry.action("bundle.move_down"),
        )
        self.assertFalse(navigator.move_up_button.icon().isNull())
        self.assertFalse(navigator.move_down_button.icon().isNull())

        upward: list[str] = []
        downward: list[str] = []
        navigator.move_up_requested.connect(upward.append)
        navigator.move_down_requested.connect(downward.append)

        navigator.move_up_button.setFocus()
        QTest.keyClick(navigator.move_up_button, Qt.Key_Space)
        self.app.processEvents()
        self.assertEqual(upward, ["doc-2"])

        navigator.documents.setFocus()
        QTest.keyClick(navigator.documents, Qt.Key_Up, Qt.AltModifier)
        self.app.processEvents()
        self.assertEqual(upward, ["doc-2", "doc-2"])

        navigator.documents.setCurrentRow(0)
        self.app.processEvents()
        self.assertFalse(navigator.move_up_button.isEnabled())
        self.assertTrue(navigator.move_down_button.isEnabled())
        navigator.move_down_button.setFocus()
        QTest.keyClick(navigator.move_down_button, Qt.Key_Space)
        self.app.processEvents()
        self.assertEqual(downward, ["doc-1"])

        navigator.documents.setCurrentRow(2)
        self.app.processEvents()
        self.assertTrue(navigator.move_up_button.isEnabled())
        self.assertFalse(navigator.move_down_button.isEnabled())
        navigator.close()

    def test_inspector_filter_and_toast_dismiss_have_accessible_names(self) -> None:
        inspector = InspectorTree("Conversion summary")
        toast = ToastBanner()
        self.assertEqual(
            inspector.filter_edit.accessibleName(), "Filter conversion summary"
        )
        self.assertEqual(toast.close_button.accessibleName(), "Dismiss notification")
        inspector.close()
        toast.close()

    def test_quantum_rail_keyboard_navigation_activation_and_scrolling(self) -> None:
        editor = CodeEditor(language="python")
        text = "".join(f"line {index:02d}\n" for index in range(80))
        first = text.index("line 05")
        last = text.index("line 60")
        editor.setPlainText(text)
        editor.set_search_ranges(
            (
                EditorMarker(first, first + 7, marker_id="first", message="First match"),
                EditorMarker(last, last + 7, marker_id="last", message="Last match"),
            )
        )
        editor.resize(520, 260)
        editor.show()
        self.app.processEvents()

        rail = editor._quantum_rail
        self.assertEqual(rail.focusPolicy(), Qt.StrongFocus)
        self.assertEqual(rail.accessibleName(), "Source quantum visibility rail")
        self.assertIn("arrow keys", rail.accessibleDescription())
        self.assertIn("Enter or Space", rail.accessibleDescription())

        activated: list[tuple[str, str, int]] = []
        editor.markerActivated.connect(
            lambda kind, marker_id, position: activated.append(
                (kind, marker_id, position)
            )
        )
        rail.setFocus()
        QTest.keyClick(rail, Qt.Key_Down)
        self.assertEqual(rail.selected_marker().marker_id, "first")
        QTest.keyClick(rail, Qt.Key_Return)
        self.assertEqual(activated[-1], ("search", "first", first))

        QTest.keyClick(rail, Qt.Key_End)
        self.assertEqual(rail.selected_marker().marker_id, "last")
        QTest.keyClick(rail, Qt.Key_Space)
        self.assertEqual(activated[-1], ("search", "last", last))

        editor.clear_markers()
        scroll_bar = editor.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.minimum())
        before = scroll_bar.value()
        QTest.keyClick(rail, Qt.Key_PageDown)
        self.assertGreater(scroll_bar.value(), before)
        editor.close()


if __name__ == "__main__":
    unittest.main()
