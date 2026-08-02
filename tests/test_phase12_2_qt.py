from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pycforge.ide.controller import WorkspaceController
from pycforge.ide import qt as workspace_qt


QT_AVAILABLE = workspace_qt.QT_AVAILABLE

if QT_AVAILABLE:
    from PyQt5.QtCore import QSettings, Qt
    from PyQt5.QtTest import QSignalSpy, QTest
    from PyQt5.QtWidgets import QApplication


@unittest.skipUnless(QT_AVAILABLE, "PyQt5 is unavailable")
class Phase122QtBehaviorTests(unittest.TestCase):
    """Real offscreen Qt behavior for the v0.12.2 workspace hardening."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["pycforge-qt-tests"])

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.settings = QSettings(
            str(Path(self._temporary_directory.name) / "settings.ini"),
            QSettings.IniFormat,
        )
        self.settings.clear()
        self._windows: list[workspace_qt.MainWindow] = []
        self.addCleanup(self._dispose_windows)

    def _window(
        self, controller: WorkspaceController | None = None
    ) -> workspace_qt.MainWindow:
        with mock.patch.object(workspace_qt, "QSettings", return_value=self.settings):
            window = workspace_qt.MainWindow(controller)
        self._windows.append(window)
        window.show()
        window.activateWindow()
        QTest.qWait(10)
        return window

    def _wait_until(self, predicate, attempts: int = 200) -> bool:
        for _index in range(attempts):
            if predicate():
                return True
            QTest.qWait(5)
            self.app.processEvents()
        return bool(predicate())

    def _dispose_windows(self) -> None:
        for window in reversed(self._windows):
            if getattr(window, "_closing", False):
                continue
            window._closing = True
            try:
                window.controller.unsubscribe(window._snapshot_listener)
            except (AttributeError, RuntimeError):
                pass
            window.controller.close(wait=True)
            window.close()
            window.deleteLater()
        self.app.processEvents()

    def test_corrupt_typed_settings_cannot_block_window_construction(self):
        self.settings.setValue(
            "settings/schema_version", workspace_qt.SETTINGS_SCHEMA_VERSION
        )
        self.settings.setValue("window/geometry", 17)
        self.settings.setValue("window/state", ["not", "a", "byte-array"])
        self.settings.setValue("splitter/workspace", {"bad": "state"})
        self.settings.setValue("splitter/editors", False)
        self.settings.setValue("splitter/main", "not-state")
        self.settings.setValue("view/bundle", 9)
        self.settings.setValue("view/generated_c", "maybe")
        self.settings.setValue("view/details", [True])
        self.settings.setValue("workspace/last_directory", ["not", "text"])
        self.settings.setValue("workspace/recent_paths", 42)
        self.settings.sync()

        window = self._window()
        self.assertEqual(window._recent_paths, [])
        self.assertEqual(window._last_directory, "")
        self.assertTrue(window.navigator.isVisible())
        self.assertFalse(window.output_panel.isVisible())
        self.assertFalse(window.tabs.isVisible())

        # A malformed schema marker clears the known presentation keys and is
        # repaired without affecting construction of a subsequent window.
        window._closing = True
        window.controller.unsubscribe(window._snapshot_listener)
        window.controller.close(wait=True)
        window.close()
        self.settings.setValue("settings/schema_version", "corrupt")
        self.settings.setValue("workspace/recent_paths", 99)
        repaired = self._window()
        self.assertEqual(repaired._recent_paths, [])
        self.assertEqual(
            int(self.settings.value("settings/schema_version")),
            workspace_qt.SETTINGS_SCHEMA_VERSION,
        )
        self.assertFalse(self.settings.contains("workspace/recent_paths"))

    def test_ctrl_h_opens_replace_once_while_find_field_has_focus(self):
        window = self._window()
        window.find_action.trigger()
        QTest.qWait(1)
        self.assertTrue(window.find_bar.isVisible())
        self.assertFalse(window.find_bar.replace_edit.isVisible())
        window.find_bar.find_edit.setFocus()
        triggered = QSignalSpy(window.replace_action.triggered)

        QTest.keyClick(window.find_bar.find_edit, Qt.Key_H, Qt.ControlModifier)
        QTest.qWait(1)

        self.assertEqual(len(triggered), 1)
        self.assertTrue(window.find_bar.replace_edit.isVisible())
        self.assertIs(window.find_bar.editor, window.source)

    def test_replacement_advance_uses_qt_utf16_positions(self):
        controller = WorkspaceController()
        controller.set_source("a a")
        window = self._window(controller)
        window.find_bar.open_find(True)
        window.find_bar.find_edit.setText("a")
        window.find_bar.replace_edit.setText("🚀a")
        self.assertTrue(
            self._wait_until(
                lambda: window.find_bar.match_count == 2
            )
        )
        self.assertTrue(window.find_bar.replace_button.isEnabled())

        QTest.mouseClick(window.find_bar.replace_button, Qt.LeftButton)
        self.assertEqual(window.source.toPlainText(), "🚀a a")
        self.assertTrue(
            self._wait_until(
                lambda: (
                    window.find_bar.match_count == 2
                    and not window.find_bar._search_pending
                )
            )
        )
        self.assertEqual(window.find_bar.active_match_index, 1)
        window.find_bar._select_active_match()
        cursor = window.source.textCursor()
        self.assertEqual(cursor.selectedText(), "a")
        self.assertEqual((cursor.selectionStart(), cursor.selectionEnd()), (4, 5))

    def test_pending_identity_disables_generated_c_save_before_commit(self):
        controller = WorkspaceController()
        controller.set_source("def identity(value: int) -> int:\n    return value\n")
        controller.convert()
        destination = Path(self._temporary_directory.name) / "linked.c"
        destination.write_text("last-known-good\n", encoding="utf-8")
        controller.link_generated_c(destination)
        self.assertTrue(controller.snapshot.can_save_c)
        window = self._window(controller)
        window.navigator.module_edit.setFocus()
        window.navigator.module_edit.selectAll()
        QTest.keyClicks(window.navigator.module_edit, "renamed")
        self.app.processEvents()
        self.assertTrue(window.navigator.identity_pending)
        self.assertFalse(window.save_c_action.isEnabled())
        self.assertEqual(
            window.output_state_label.text(),
            "STALE · IDENTITY EDIT PENDING",
        )
        self.assertEqual(window.state_chip.text(), "IDENTITY EDIT PENDING")
        triggered = QSignalSpy(window.save_c_action.triggered)

        QTest.keyClick(
            window.navigator.module_edit,
            Qt.Key_S,
            Qt.ControlModifier | Qt.AltModifier,
        )
        QTest.qWait(1)

        self.assertEqual(len(triggered), 0)
        self.assertEqual(controller.snapshot.active_document.module_id, "main")
        self.assertTrue(controller.snapshot.can_save_c)
        self.assertEqual(
            destination.read_text(encoding="utf-8"), "last-known-good\n"
        )

        QTest.keyClick(window.navigator.module_edit, Qt.Key_Return)
        QTest.qWait(1)

        self.assertEqual(controller.snapshot.active_document.module_id, "renamed")
        self.assertEqual(controller.snapshot.state.value, "stale")
        self.assertFalse(controller.snapshot.can_save_c)
        self.assertEqual(
            destination.read_text(encoding="utf-8"), "last-known-good\n"
        )

    def test_navigator_reorder_commits_identity_and_preserves_full_order(self):
        controller = WorkspaceController()
        alpha = controller.add_document(
            "alpha", "alpha.py", make_active=False, dirty=False
        )
        beta = controller.add_document(
            "beta", "beta.py", make_active=True, dirty=False
        )
        window = self._window(controller)
        window.navigator.module_edit.setFocus()
        window.navigator.module_edit.selectAll()
        QTest.keyClicks(window.navigator.module_edit, "beta_renamed")

        QTest.mouseClick(window.navigator.move_up_button, Qt.LeftButton)
        QTest.qWait(1)

        documents = controller.snapshot.documents
        self.assertEqual(
            tuple(item.document_id for item in documents),
            ("doc-main", beta.document_id, alpha.document_id),
        )
        self.assertEqual(documents[1].module_id, "beta_renamed")
        self.assertEqual(controller.snapshot.active_document_id, beta.document_id)
        self.assertEqual(window.navigator.current_document_id, beta.document_id)

    def test_mapping_status_has_one_prefix(self):
        controller = WorkspaceController()
        controller.set_source(
            "def value() -> int:\n"
            "    return 7\n"
        )
        controller.convert()
        window = self._window(controller)
        self.assertTrue(
            self._wait_until(
                lambda: controller.result_output_index is not None
            )
        )
        window._activate_mapping(
            {
                "module_id": "main",
                "rule_plan_id": "Mapping — plan-1",
                "start_line": 1,
                "start_column": 0,
                "end_line": 1,
                "end_column": 1,
            }
        )
        self.assertEqual(window.statusBar().currentMessage(), "Mapping — main · plan-1")


if __name__ == "__main__":
    unittest.main()
