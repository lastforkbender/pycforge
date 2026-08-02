from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.action_contract import ACTION_SPECS
from pycforge.ide.qt_contract import PRESENTATION_SETTING_KEYS


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_MODULES = (
    "pycforge/ide/qt.py",
    "pycforge/ide/qt_contract.py",
    "pycforge/ide/qt_shell.py",
    "pycforge/ide/qt_shell_interactions.py",
    "pycforge/ide/qt_editor_surfaces.py",
    "pycforge/ide/qt_editor_buffers.py",
    "pycforge/ide/qt_workspace_features.py",
    "pycforge/ide/qt_workspace_navigation.py",
    "pycforge/ide/qt_workspace_observers.py",
    "pycforge/ide/qt_workspace_panels.py",
    "pycforge/ide/qt_documents.py",
    "pycforge/ide/qt_projection.py",
    "pycforge/ide/qt_state.py",
    "pycforge/ide/qt_close.py",
)


def module_source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


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


def named_assignment(
    method: ast.FunctionDef,
    name: str,
) -> ast.Assign:
    return next(
        node
        for node in method.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    )


def attribute_path(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


class Phase15CQtWorkspaceIntegrationTests(unittest.TestCase):
    def test_shell_registers_exactly_all_47_static_handlers(self) -> None:
        source = module_source("pycforge/ide/qt_shell.py")
        tree = ast.parse(source)
        method = method_node(tree, "QtShellMixin", "_build_actions")
        assignment = named_assignment(method, "handlers")
        self.assertIsInstance(assignment.value, ast.Dict)
        handler_ids = tuple(
            ast.literal_eval(key)
            for key in assignment.value.keys
            if key is not None
        )
        static_ids = {
            action_id
            for action_id, spec in ACTION_SPECS.items()
            if not spec.dynamic
        }
        self.assertEqual(len(handler_ids), 47)
        self.assertEqual(len(set(handler_ids)), 47)
        self.assertEqual(set(handler_ids), static_ids)

    def test_missing_qt_clipboard_payload_disables_paste(self) -> None:
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import tempfile
        from types import SimpleNamespace
        from unittest import mock

        from pycforge.ide.controller import WorkspaceController
        from pycforge.ide import qt as workspace_qt

        if not workspace_qt.QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-clipboard-test"]
        )
        controller = WorkspaceController()
        window = None
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            data_changed = SimpleNamespace(
                connect=lambda _receiver: None
            )
            clipboard = SimpleNamespace(
                dataChanged=data_changed,
                mimeData=lambda: None,
            )
            try:
                with (
                    mock.patch.object(
                        workspace_qt,
                        "QSettings",
                        return_value=settings,
                    ),
                    mock.patch.object(
                        QApplication,
                        "clipboard",
                        return_value=clipboard,
                    ),
                ):
                    window = workspace_qt.MainWindow(controller)
                    states = window._action_states(
                        None,
                        window.source,
                    )
                self.assertFalse(states["edit.paste"].enabled)
            finally:
                if window is not None:
                    window._closing = True
                    controller.unsubscribe(window._snapshot_listener)
                    window._close_workspace_features()
                    window.close()
                    window.deleteLater()
                controller.close(wait=True)
                app.processEvents()

    def test_shared_qt_document_rebind_preserves_highlighter_lifetime(
        self,
    ) -> None:
        try:
            from PyQt5.QtCore import QObject
            from PyQt5.QtGui import QTextDocument
            from PyQt5.QtWidgets import (
                QApplication,
                QPlainTextDocumentLayout,
            )
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        from pycforge.ide.editor import CodeEditor, QT_AVAILABLE

        if not QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-buffer-test"]
        )
        owner = QObject()
        document = QTextDocument(owner)
        document.setDocumentLayout(
            QPlainTextDocumentLayout(document)
        )
        document.setPlainText("def value():\n    return 1\n")
        primary = CodeEditor(language="python")
        secondary = CodeEditor(
            language="python",
            highlighting=False,
        )
        try:
            primary.bind_text_document(document)
            secondary.bind_text_document(document)
            self.assertIs(primary.document(), document)
            self.assertIs(secondary.document(), document)
            self.assertIs(primary._highlighter.document(), document)
            self.assertIsNone(secondary._highlighter.document())

            primary.set_large_file_mode(True)
            self.assertIsNone(primary._highlighter.document())
            primary.set_large_file_mode(False)
            self.assertIs(primary._highlighter.document(), document)
        finally:
            primary.close()
            secondary.close()
            primary.deleteLater()
            secondary.deleteLater()
            owner.deleteLater()
            app.processEvents()

    def test_qt_show_ignores_formatting_but_typing_marks_edit_pending(
        self,
    ) -> None:
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtTest import QTest
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import tempfile
        from unittest import mock

        from pycforge.ide.controller import WorkspaceController
        from pycforge.ide import qt as workspace_qt

        if not workspace_qt.QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-formatting-test"]
        )
        controller = WorkspaceController()
        controller.set_source(
            "def value() -> int:\n"
            "    return 1\n"
        )
        window = None
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            try:
                with mock.patch.object(
                    workspace_qt,
                    "QSettings",
                    return_value=settings,
                ):
                    window = workspace_qt.MainWindow(controller)
                window.show()
                QTest.qWait(20)
                app.processEvents()
                self.assertFalse(window._source_sync_pending)
                self.assertFalse(window.source.document().isModified())

                window.source.setFocus()
                QTest.keyClicks(window.source, "x")
                app.processEvents()
                self.assertTrue(window._source_sync_pending)
                self.assertTrue(window.source.document().isModified())
            finally:
                if window is not None:
                    window._closing = True
                    controller.unsubscribe(window._snapshot_listener)
                    window._close_workspace_features()
                    window.close()
                    window.deleteLater()
                controller.close(wait=True)
                app.processEvents()

    def test_disabled_qt_window_shortcut_is_consumed_in_identity_field(
        self,
    ) -> None:
        try:
            from PyQt5.QtCore import QSettings, Qt
            from PyQt5.QtTest import QTest
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import tempfile
        from unittest import mock

        from pycforge.ide.controller import WorkspaceController
        from pycforge.ide import qt as workspace_qt

        if not workspace_qt.QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-disabled-shortcut-test"]
        )
        controller = WorkspaceController()
        window = None
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            try:
                with mock.patch.object(
                    workspace_qt,
                    "QSettings",
                    return_value=settings,
                ):
                    window = workspace_qt.MainWindow(controller)
                window.show()
                window.navigator.module_edit.setFocus()
                window.navigator.module_edit.selectAll()
                QTest.keyClicks(window.navigator.module_edit, "renamed")
                before = window.navigator.module_edit.text()
                self.assertFalse(window.save_c_action.isEnabled())

                QTest.keyClick(
                    window.navigator.module_edit,
                    Qt.Key_S,
                    Qt.ControlModifier | Qt.AltModifier,
                )
                app.processEvents()
                self.assertEqual(
                    window.navigator.module_edit.text(),
                    before,
                )
            finally:
                if window is not None:
                    window._closing = True
                    controller.unsubscribe(window._snapshot_listener)
                    window.close()
                    window.deleteLater()
                controller.close(wait=True)
                app.processEvents()

    def test_qt_replace_advances_past_astral_replacement(self) -> None:
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtTest import QTest
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import tempfile
        from unittest import mock

        from pycforge.ide.controller import WorkspaceController
        from pycforge.ide import qt as workspace_qt

        if not workspace_qt.QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-replace-test"]
        )
        controller = WorkspaceController()
        controller.set_source("# x X xylophone x\n")
        window = None
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            try:
                with mock.patch.object(
                    workspace_qt,
                    "QSettings",
                    return_value=settings,
                ):
                    window = workspace_qt.MainWindow(controller)
                window.show()
                window.find_bar.attach_editor(window.source)
                window.find_bar.open_find(True)
                window.find_bar.find_edit.setText("x")
                window.find_bar.whole_word.setChecked(True)
                window.find_bar.match_case.setChecked(True)
                for _index in range(200):
                    if (
                        window.find_bar.match_count == 2
                        and not window.find_bar._search_pending
                    ):
                        break
                    QTest.qWait(5)
                    app.processEvents()
                self.assertEqual(window.find_bar.match_count, 2)

                window.find_bar.replace_edit.setText("🚀x")
                self.assertTrue(window.find_bar.replace_current())
                for _index in range(200):
                    if (
                        window.find_bar.match_count == 2
                        and not window.find_bar._search_pending
                    ):
                        break
                    QTest.qWait(5)
                    app.processEvents()
                self.assertEqual(window.find_bar.active_match_index, 1)
                window.find_bar._select_active_match()
                replaced = window.source.toPlainText()
                cursor = window.source.textCursor()
                self.assertEqual(cursor.selectedText(), "x")
                self.assertEqual(
                    cursor.selectionStart(),
                    workspace_qt.python_offset_to_qt_position(
                        replaced,
                        replaced.rfind("x"),
                    ),
                )
            finally:
                if window is not None:
                    window._closing = True
                    controller.unsubscribe(window._snapshot_listener)
                    window.close()
                    window.deleteLater()
                controller.close(wait=True)
                app.processEvents()

    def test_repeated_qt_window_teardown_closes_search_services(
        self,
    ) -> None:
        try:
            from PyQt5.QtCore import QCoreApplication, QEvent, QSettings
            from PyQt5.QtTest import QTest
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import tempfile
        from unittest import mock

        from pycforge.ide.controller import WorkspaceController
        from pycforge.ide import qt as workspace_qt

        if not workspace_qt.QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-teardown-test"]
        )
        find_services = []
        bundle_services = []
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.IniFormat,
            )
            for _index in range(4):
                controller = WorkspaceController()
                with mock.patch.object(
                    workspace_qt,
                    "QSettings",
                    return_value=settings,
                ):
                    window = workspace_qt.MainWindow(controller)
                window.show()
                QTest.qWait(10)
                find_services.append(window.find_bar._search_service)
                bundle_services.append(
                    window.bundle_search._search_service
                )
                window._closing = True
                controller.unsubscribe(window._snapshot_listener)
                controller.close(wait=True)
                window.close()
                self.assertTrue(find_services[-1]._closed)
                self.assertTrue(bundle_services[-1].is_closed)
                window.deleteLater()
                QCoreApplication.sendPostedEvents(
                    None,
                    QEvent.DeferredDelete,
                )
                app.processEvents()
        self.assertTrue(
            all(service._closed for service in find_services)
        )
        self.assertTrue(
            all(service.is_closed for service in bundle_services)
        )

    def test_qt_search_widget_gc_finalizers_close_services(self) -> None:
        try:
            from PyQt5.QtCore import QCoreApplication, QEvent
            from PyQt5.QtWidgets import QApplication
        except (ImportError, ModuleNotFoundError):
            self.skipTest("PyQt5 is unavailable")

        import gc
        from weakref import ref

        from pycforge.ide.find_replace import (
            FindReplaceBar,
            QT_AVAILABLE as FIND_QT_AVAILABLE,
        )
        from pycforge.ide.qt_workspace_panels import (
            BundleSearchView,
        )

        if not FIND_QT_AVAILABLE:
            self.skipTest("PyQt5 is unavailable")
        app = QApplication.instance() or QApplication(
            ["pycforge-phase15c-finalizer-test"]
        )
        find_bar = FindReplaceBar()
        bundle_search = BundleSearchView()
        find_service = find_bar._search_service
        bundle_service = bundle_search._search_service
        find_ref = ref(find_bar)
        bundle_ref = ref(bundle_search)
        find_bar.deleteLater()
        bundle_search.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        del find_bar
        del bundle_search
        gc.collect()
        self.assertIsNone(find_ref())
        self.assertIsNone(bundle_ref())
        self.assertTrue(find_service._closed)
        self.assertTrue(bundle_service.is_closed)

    def test_new_panels_are_constructed_tabbed_and_signal_wired(self) -> None:
        shell = module_source("pycforge/ide/qt_shell.py")
        interactions = module_source(
            "pycforge/ide/qt_shell_interactions.py"
        )
        for declaration in (
            "self.outline = OutlineView()",
            "self.bundle_search = BundleSearchView()",
            "self.session_history = SessionHistoryView()",
            'self.tabs.addTab(self.outline, "Outline")',
            'self.tabs.addTab(self.bundle_search, "Bundle Search")',
            'self.tabs.addTab(self.session_history, "History")',
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, shell)
        for connection in (
            "self.outline.symbolActivated.connect(",
            "self.bundle_search.matchActivated.connect(",
            "self.session_history.historyActivated.connect(",
        ):
            with self.subTest(connection=connection):
                self.assertIn(connection, interactions)

    def test_context_menu_targets_are_exact_for_workspace_views(self) -> None:
        source = module_source("pycforge/ide/qt_shell.py")
        tree = ast.parse(source)
        method = method_node(tree, "QtShellMixin", "_build_menus")
        assignment = named_assignment(method, "required_contexts")
        self.assertIsInstance(assignment.value, ast.Tuple)
        actual = tuple(
            (
                attribute_path(entry.elts[0]),
                ast.literal_eval(entry.elts[1]),
            )
            for entry in assignment.value.elts
            if isinstance(entry, ast.Tuple)
            and len(entry.elts) == 2
        )
        self.assertEqual(
            actual,
            (
                ("self.source", "context.python_source"),
                ("self.source_secondary", "context.python_source"),
                ("self.output", "context.generated_c"),
                (
                    "self.navigator.documents",
                    "context.source_bundle",
                ),
                (
                    "self.document_tabs",
                    "context.document_tabs",
                ),
                ("self.diags.tree", "context.diagnostics"),
                ("self.mappings.tree", "context.mappings"),
                ("self.summary.tree", "context.inspector"),
                ("self.trace.tree", "context.inspector"),
                ("self.telemetry.tree", "context.inspector"),
                ("self.outline.tree", "context.inspector"),
                (
                    "self.bundle_search.tree",
                    "context.bundle_search",
                ),
                (
                    "self.session_history.tree",
                    "context.conversion_history",
                ),
            ),
        )
        text_assignment = named_assignment(method, "text_inputs")
        self.assertIsInstance(text_assignment.value, ast.Tuple)
        text_inputs = {
            attribute_path(item)
            for item in text_assignment.value.elts
        }
        self.assertTrue(
            {
                "self.outline.filter_edit",
                "self.bundle_search.query_edit",
            }.issubset(text_inputs)
        )

    def test_secondary_source_is_a_shared_buffer_view(self) -> None:
        surfaces = module_source(
            "pycforge/ide/qt_editor_surfaces.py"
        )
        interactions = module_source(
            "pycforge/ide/qt_shell_interactions.py"
        )
        projection = module_source("pycforge/ide/qt_projection.py")
        features = module_source(
            "pycforge/ide/qt_workspace_features.py"
        )
        for declaration in (
            'owner.source = CodeEditor(language="python")',
            "owner.source_secondary = CodeEditor(",
            'owner.source_secondary.setObjectName("PythonSourceEditorSecondary")',
            "owner.source_splitter.addWidget(owner.source)",
            "owner.source_splitter.addWidget(owner.source_secondary)",
            "owner.source_secondary.setVisible(False)",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, surfaces)
        self.assertIn(
            "for editor in (self.source, self.source_secondary):",
            interactions,
        )
        self.assertIn(
            "self.source_secondary.set_diagnostic_ranges(",
            projection,
        )
        self.assertIn("SourceBufferStore(", features)
        self.assertIn(".document_for(", features)
        self.assertGreaterEqual(
            features.count(".bind_text_document("),
            2,
        )

    def test_buffer_store_is_bounded_snapshot_only_and_payload_safe(
        self,
    ) -> None:
        source = module_source(
            "pycforge/ide/qt_editor_buffers.py"
        )
        tree = ast.parse(source)
        self.assertIn("MAX_SOURCE_BUFFERS = 64", source)
        self.assertIn("class SourceBufferStore(QObject):", source)
        reconcile = method_node(
            tree,
            "SourceBufferStore",
            "reconcile",
        )
        reconcile_source = ast.get_source_segment(
            source,
            reconcile,
        ) or ""
        self.assertIn("1 <= len(records) <= MAX_SOURCE_BUFFERS", reconcile_source)
        self.assertIn("item.document_id", reconcile_source)
        self.assertIn("item.text", reconcile_source)
        self.assertIn("id(item.text)", reconcile_source)
        self.assertNotIn("item.path", reconcile_source)
        self.assertNotIn("open(", reconcile_source)
        self.assertNotIn(".read_", reconcile_source)

    def test_structure_service_bridge_is_generation_and_workspace_safe(
        self,
    ) -> None:
        public = module_source("pycforge/ide/qt.py")
        features = module_source(
            "pycforge/ide/qt_workspace_features.py"
        )
        observers = module_source(
            "pycforge/ide/qt_workspace_observers.py"
        )
        bridge = features + "\n" + observers
        tree = ast.parse(features)
        self.assertIn("structure_ready = pyqtSignal(object)", public)
        self.assertIn("AsyncSourceStructureService(", features)
        self.assertIn("SourceStructureDocument(", bridge)
        self.assertIn("callback=self.structure_ready.emit", bridge)
        self.assertIn("workspace_key=", bridge)
        self.assertIn("result.generation", bridge)
        self.assertIn("result.workspace_key", bridge)
        self.assertIn(
            "self.controller.snapshot.bundle_fingerprint",
            bridge,
        )
        self.assertIn("self.structure_ready.connect(", features)
        self.assertIn("snapshot.revision_generation", bridge)
        self.assertIn("snapshot.bundle_fingerprint", bridge)
        methods = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "QtWorkspaceFeaturesMixin"
            for node in node.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue(
            {
                "_initialize_workspace_features",
                "_project_workspace_features",
                "_invalidate_source_observers",
                "_close_workspace_features",
                "_submit_source_structure",
                "_accept_source_structure",
            }.issubset(methods)
        )

    def test_feature_projection_populates_tabs_search_and_history(
        self,
    ) -> None:
        source = module_source(
            "pycforge/ide/qt_workspace_features.py"
        )
        tree = ast.parse(source)
        method = method_node(
            tree,
            "QtWorkspaceFeaturesMixin",
            "_project_workspace_features",
        )
        method_source = ast.get_source_segment(source, method) or ""
        for call in (
            "self.source_buffers.reconcile(",
            "self.document_tabs.set_documents(",
            "self.bundle_search.set_documents(",
            "self.session_history.set_entries(",
        ):
            with self.subTest(call=call):
                self.assertIn(call, method_source)
        self.assertIn("snapshot.documents", method_source)
        self.assertIn("snapshot.active_document_id", method_source)
        self.assertIn("snapshot.conversion_history", method_source)

    def test_pending_sync_palette_fold_and_breadcrumb_guards_are_static(
        self,
    ) -> None:
        features = module_source(
            "pycforge/ide/qt_workspace_features.py"
        )
        panels = module_source(
            "pycforge/ide/qt_workspace_panels.py"
        )
        tree = ast.parse(features)
        project = ast.get_source_segment(
            features,
            method_node(
                tree,
                "QtWorkspaceFeaturesMixin",
                "_project_workspace_features",
            ),
        ) or ""
        self.assertIn("if pending_id is not None:", project)
        self.assertIn("self.bundle_search.invalidate_results()", project)
        self.assertIn("self.bundle_search.set_documents(", project)
        self.assertIn("self._submit_source_structure(", project)

        palette = ast.get_source_segment(
            features,
            method_node(
                tree,
                "QtWorkspaceFeaturesMixin",
                "_open_command_palette",
            ),
        ) or ""
        self.assertIn("if self._command_palette_open:", palette)
        self.assertIn("try:", palette)
        self.assertIn("finally:", palette)
        self.assertIn("self._command_palette_open = False", palette)

        folding = ast.get_source_segment(
            features,
            method_node(
                tree,
                "QtWorkspaceFeaturesMixin",
                "_toggle_source_fold",
            ),
        ) or ""
        self.assertIn("target is self.source_secondary", folding)
        self.assertIn("self.source.toggle_fold_at_cursor()", folding)

        update = ast.get_source_segment(
            features,
            method_node(
                tree,
                "QtWorkspaceFeaturesMixin",
                "_update_breadcrumbs",
            ),
        ) or ""
        self.assertIn("self._breadcrumb_timer.start()", update)
        self.assertIn("self._breadcrumb_timer.setSingleShot(True)", features)
        self.assertIn("self._breadcrumb_timer.stop()", features)
        self.assertIn("def invalidate_results(", panels)
        self.assertIn("self._documents = ()", panels)
        self.assertIn("self._document_key = ()", panels)

    def test_close_path_retires_observers_panels_and_buffers(self) -> None:
        close = module_source("pycforge/ide/qt_close.py")
        features = module_source(
            "pycforge/ide/qt_workspace_features.py"
        )
        tree = ast.parse(features)
        method = method_node(
            tree,
            "QtWorkspaceFeaturesMixin",
            "_close_workspace_features",
        )
        method_source = ast.get_source_segment(source=features, node=method)
        method_source = method_source or ""
        self.assertIn("self._close_workspace_features()", close)
        for declaration in (
            "self._workspace_features_closed = True",
            "self._expected_structure_generation = None",
            "self._expected_structure_key = None",
            "self._source_structure_result = None",
            "self._source_structure_service.close(wait_seconds=0.05)",
            "self.bundle_search.close_service()",
            "self.source_buffers.close()",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, method_source)

    def test_new_split_settings_keys_are_exact_and_round_trip(self) -> None:
        self.assertEqual(
            PRESENTATION_SETTING_KEYS,
            (
                "window/geometry",
                "window/state",
                "splitter/workspace",
                "splitter/editors",
                "splitter/main",
                "splitter/source",
                "view/bundle",
                "view/generated_c",
                "view/details",
                "view/source_split",
                "view/whitespace",
                "workspace/last_directory",
                "workspace/recent_paths",
            ),
        )
        state = module_source("pycforge/ide/qt_state.py")
        for declaration in (
            '("splitter/source", self.source_splitter.restoreState)',
            '"splitter/source": self.source_splitter.saveState()',
            'self._setting_bool("view/source_split", False)',
            '"view/source_split": self.source_secondary.isVisible()',
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, state)

    def test_public_optional_seam_exports_reverse_position_helper_and_mixin(
        self,
    ) -> None:
        source = module_source("pycforge/ide/qt.py")
        self.assertIn("qt_position_to_python_offset,", source)
        self.assertIn(
            "from .qt_workspace_features import QtWorkspaceFeaturesMixin",
            source,
        )
        self.assertIn("QtWorkspaceFeaturesMixin,", source)
        self.assertEqual(
            source.count('"qt_position_to_python_offset",'),
            2,
        )

    def test_integration_modules_are_bounded_and_parseable(self) -> None:
        for relative in INTEGRATION_MODULES:
            with self.subTest(relative=relative):
                source = module_source(relative)
                self.assertLess(len(source.splitlines()), 600)
                ast.parse(source, filename=relative)


if __name__ == "__main__":
    unittest.main()
