from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.action_contract import ACTION_SPECS, SURFACE_SPECS


ROOT = Path(__file__).resolve().parents[1]
QT_INTEGRATION_MODULES = (
    "pycforge/ide/qt_shell.py",
    "pycforge/ide/qt_projection.py",
    "pycforge/ide/qt_documents.py",
    "pycforge/ide/qt_state.py",
    "pycforge/ide/qt.py",
)


def module_source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class Phase15BActionIntegrationTests(unittest.TestCase):
    def test_shell_registers_every_static_action_exactly_once(self) -> None:
        source = module_source("pycforge/ide/qt_shell.py")
        tree = ast.parse(source)
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_build_actions"
        )
        handler_assignment = next(
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "handlers"
                for target in node.targets
            )
        )
        self.assertIsInstance(handler_assignment.value, ast.Dict)
        handler_ids = {
            key.value
            for key in handler_assignment.value.keys
            if isinstance(key, ast.Constant)
            and isinstance(key.value, str)
        }
        static_ids = {
            action_id
            for action_id, spec in ACTION_SPECS.items()
            if not spec.dynamic
        }
        self.assertEqual(handler_ids, static_ids)
        self.assertIn("QtActionRegistry(", source)
        self.assertIn("QtMenuFactory(", source)

    def test_predecessor_action_attributes_are_object_aliases(self) -> None:
        source = module_source("pycforge/ide/qt_shell.py")
        expected = {
            '"open_action": "file.open_python"',
            '"add_document_action": "bundle.new_module"',
            '"remove_document_action": "bundle.remove_module"',
            '"save_python_action": "file.save_python"',
            '"save_python_as_action": "file.save_python_as"',
            '"convert_action": "conversion.convert"',
            '"cancel_action": "conversion.cancel"',
            '"find_action": "search.find"',
            '"replace_action": "search.replace"',
            '"link_c_action": "output.set_destination"',
            '"save_c_action": "output.save_c"',
            '"show_c_action": "view.generated_c"',
            '"show_details_action": "view.conversion_details"',
            '"show_navigator_action": "view.source_bundle"',
        }
        for declaration in expected:
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, source)
        self.assertIn("self.action_registry.action(action_id)", source)

    def test_shell_installs_every_required_context_surface(self) -> None:
        source = module_source("pycforge/ide/qt_shell.py")
        required = {
            "context.python_source",
            "context.generated_c",
            "context.source_bundle",
            "context.diagnostics",
            "context.mappings",
            "context.inspector",
            "context.text_input",
            "context.read_only_text",
        }
        for surface_id in required:
            with self.subTest(surface_id=surface_id):
                self.assertIn(f'"{surface_id}"', source)
                self.assertIn(surface_id, SURFACE_SPECS)
        generated = SURFACE_SPECS["context.generated_c"]
        self.assertEqual(
            tuple(
                placement.target
                for placement in generated.placements
                if placement.target
            ),
            ("edit.copy", "edit.select_all", "search.find"),
        )

    def test_snapshot_and_pending_edit_state_flow_through_registry(self) -> None:
        shell = module_source("pycforge/ide/qt_shell.py")
        projection = module_source("pycforge/ide/qt_projection.py")
        documents = module_source("pycforge/ide/qt_documents.py")
        state = module_source("pycforge/ide/qt_state.py")
        panels = module_source("pycforge/ide/panels.py")
        self.assertIn("self.action_registry.refresh()", projection)
        self.assertIn("self.action_registry.refresh()", documents)
        self.assertIn("self.action_registry.replace_dynamic(", state)
        self.assertIn("DynamicActionEntry(", state)
        self.assertIn("identity_pending_changed = pyqtSignal(bool)", panels)
        self.assertIn(
            "self.navigator.identity_pending_changed.connect(",
            shell,
        )
        self.assertIn(
            "and not self.navigator.identity_pending",
            shell,
        )
        self.assertIn("IDENTITY EDIT PENDING", documents)
        for source in (projection, documents, state):
            self.assertNotIn("recent_menu.addAction", source)
            self.assertNotIn("save_c_action.setEnabled", source)
            self.assertNotIn("show_c_action.setText", source)
            self.assertNotIn("show_details_action.setText", source)

    def test_no_integration_module_constructs_an_ad_hoc_action_or_menu(self) -> None:
        for relative in QT_INTEGRATION_MODULES:
            source = module_source(relative)
            with self.subTest(relative=relative):
                self.assertNotIn("QAction(", source)
                self.assertNotIn("menuBar().addMenu", source)
                self.assertNotIn("createStandardContextMenu", source)

    def test_product_operation_uses_transpile_wording(self) -> None:
        action = ACTION_SPECS["conversion.convert"]
        cancel = ACTION_SPECS["conversion.cancel"]
        menu = SURFACE_SPECS["menu.conversion"]
        self.assertIn("Transpile", action.menu_text)
        self.assertIn("Transpile", action.toolbar_text)
        self.assertIn("Transpile", action.accessible_name)
        self.assertIn("Transpilation", cancel.menu_text)
        self.assertEqual(menu.title, "&Transpile")
        self.assertEqual(menu.accessible_name, "Transpile menu")

    def test_integration_modules_remain_bounded_and_parse(self) -> None:
        for relative in QT_INTEGRATION_MODULES:
            source = module_source(relative)
            with self.subTest(relative=relative):
                self.assertLess(len(source.splitlines()), 600)
                ast.parse(source, filename=relative)

    def test_menu_object_uses_the_visual_system_selector(self) -> None:
        source = module_source("pycforge/ide/qt_menus.py")
        self.assertIn('self.setObjectName("PyCForgeMenu")', source)
        self.assertIn("PYCFORGE_METRICS.icon_menu", source)
        self.assertIn("QAbstractScrollArea", source)
        self.assertIn("widget.viewport()", source)
        self.assertIn("coordinate_widget.rect().center()", source)
        self.assertIn("coordinate_widget.mapToGlobal(anchor)", source)
        self.assertNotIn(
            "                    widget.mapToGlobal(anchor),",
            source,
        )

    def test_cancel_requested_diagnostics_are_not_projected_as_current(
        self,
    ) -> None:
        source = module_source("pycforge/ide/qt_projection.py")
        tree = ast.parse(source)
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_project_editor_markers"
        )
        inactive_states = {
            node.value
            for node in ast.walk(method)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
        }
        self.assertIn("cancel-requested", inactive_states)

    def test_window_brand_and_context_find_use_registry_target(self) -> None:
        shell = module_source("pycforge/ide/qt_shell.py")
        documents = module_source("pycforge/ide/qt_documents.py")
        self.assertIn('pycforge_icon_path("brand-mark")', shell)
        self.assertIn("target = self._resolved_action_target()", documents)
        self.assertNotIn("focused = QApplication.focusWidget()", documents)


if __name__ == "__main__":
    unittest.main()
