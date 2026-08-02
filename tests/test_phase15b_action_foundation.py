from __future__ import annotations

import ast
from pathlib import Path
import unittest

from pycforge.ide.action_contract import (
    ACTION_SPECS,
    DYNAMIC_ACTION_GROUPS,
    MAIN_MENU_SURFACES,
    MAX_DYNAMIC_ACTIONS,
    SURFACE_SPECS,
    ActionState,
    DynamicActionEntry,
    PlacementKind,
    SurfaceKind,
    validate_action_contract,
    validated_dynamic_entries,
)
from pycforge.ide.qt_actions import (
    QT_ACTIONS_AVAILABLE,
    QtActionRegistry,
)
from pycforge.ide.qt_menus import (
    QT_MENUS_AVAILABLE,
    PyCForgeMenu,
    QtMenuFactory,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MODULES = (
    "pycforge/ide/action_contract.py",
    "pycforge/ide/qt_actions.py",
    "pycforge/ide/qt_menus.py",
)


def action_ids(surface_id: str) -> tuple[str, ...]:
    return tuple(
        placement.target
        for placement in SURFACE_SPECS[surface_id].placements
        if placement.kind is PlacementKind.ACTION
    )


class Phase15BActionContractTests(unittest.TestCase):
    def test_contract_is_complete_and_deterministically_valid(self) -> None:
        self.assertEqual(validate_action_contract(), ())
        self.assertGreaterEqual(len(ACTION_SPECS), 30)
        self.assertEqual(
            tuple(MAIN_MENU_SURFACES),
            (
                "menu.file",
                "menu.edit",
                "menu.view",
                "menu.navigate",
                "menu.conversion",
            ),
        )
        for action_id, spec in ACTION_SPECS.items():
            with self.subTest(action_id=action_id):
                self.assertEqual(spec.action_id, action_id)
                self.assertTrue(spec.menu_text)
                self.assertTrue(spec.tooltip)
                self.assertTrue(spec.accessible_name)
                self.assertNotIn("&", spec.accessible_name)
                self.assertNotIn("&", spec.toolbar_text)

    def test_all_surface_references_resolve_to_declared_owners(self) -> None:
        for surface_id, surface in SURFACE_SPECS.items():
            with self.subTest(surface_id=surface_id):
                self.assertEqual(surface.surface_id, surface_id)
                self.assertTrue(surface.accessible_name)
                for placement in surface.placements:
                    if placement.kind is PlacementKind.ACTION:
                        self.assertIn(placement.target, ACTION_SPECS)
                        self.assertFalse(
                            ACTION_SPECS[placement.target].dynamic
                        )
                    elif placement.kind is PlacementKind.SUBMENU:
                        self.assertEqual(
                            SURFACE_SPECS[placement.target].kind,
                            SurfaceKind.MENU,
                        )
                    elif placement.kind is PlacementKind.DYNAMIC:
                        self.assertIn(
                            placement.target, DYNAMIC_ACTION_GROUPS
                        )

    def test_generated_c_context_is_an_exact_read_only_allowlist(self) -> None:
        self.assertEqual(
            action_ids("context.generated_c"),
            ("edit.copy", "edit.select_all", "search.find"),
        )
        mutating = {
            "edit.undo",
            "edit.redo",
            "edit.cut",
            "edit.paste",
            "search.replace",
            "search.replace_current",
            "search.replace_all",
        }
        self.assertTrue(
            mutating.isdisjoint(action_ids("context.generated_c"))
        )

    def test_required_context_surfaces_are_declared(self) -> None:
        expected = {
            "context.python_source",
            "context.generated_c",
            "context.source_bundle",
            "context.diagnostics",
            "context.mappings",
            "context.inspector",
            "context.text_input",
            "context.read_only_text",
        }
        self.assertTrue(expected.issubset(SURFACE_SPECS))
        for surface_id in expected:
            self.assertEqual(
                SURFACE_SPECS[surface_id].kind,
                SurfaceKind.CONTEXT,
            )

    def test_action_catalog_has_no_forbidden_product_commands(self) -> None:
        forbidden = {
            "run",
            "execute",
            "build",
            "compile",
            "assemble",
            "deploy",
            "test",
            "debug",
            "profile",
            "terminal",
            "toolchain",
        }
        for spec in ACTION_SPECS.values():
            words = {
                word.strip("….,()").casefold()
                for text in (
                    spec.action_id.replace(".", " "),
                    spec.menu_text.replace("&", ""),
                    spec.tooltip,
                    spec.accessible_name,
                )
                for word in text.split()
            }
            with self.subTest(action_id=spec.action_id):
                self.assertTrue(forbidden.isdisjoint(words))

    def test_dynamic_entries_are_bounded_and_strict(self) -> None:
        entry = DynamicActionEntry(
            key="one",
            label="module.py",
            tooltip="/safe/module.py",
            accessible_name="Open recent module.py",
            payload="/safe/module.py",
        )
        self.assertEqual(validated_dynamic_entries([entry]), (entry,))
        with self.assertRaisesRegex(ValueError, "limit"):
            validated_dynamic_entries(
                [
                    DynamicActionEntry(
                        key=str(index),
                        label=f"{index}.py",
                        tooltip=f"/safe/{index}.py",
                        accessible_name=f"Open recent {index}.py",
                        payload=f"/safe/{index}.py",
                    )
                    for index in range(MAX_DYNAMIC_ACTIONS + 1)
                ]
            )
        with self.assertRaisesRegex(ValueError, "unique"):
            validated_dynamic_entries([entry, entry])
        with self.assertRaisesRegex(TypeError, "payload"):
            validated_dynamic_entries(
                [
                    DynamicActionEntry(
                        key="bad",
                        label="bad.py",
                        tooltip="/safe/bad.py",
                        accessible_name="Open recent bad.py",
                        payload=7,  # type: ignore[arg-type]
                    )
                ]
            )

    def test_action_state_is_a_small_immutable_projection(self) -> None:
        state = ActionState(enabled=False, checked=True, visible=False)
        self.assertFalse(state.enabled)
        self.assertTrue(state.checked)
        self.assertFalse(state.visible)
        with self.assertRaises((AttributeError, TypeError)):
            state.enabled = True  # type: ignore[misc]

    def test_new_production_modules_are_bounded_and_parse(self) -> None:
        retired = "space" + "port"
        for relative in PRODUCTION_MODULES:
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                self.assertLess(len(source.splitlines()), 600)
                ast.parse(source, filename=relative)
                self.assertNotIn(retired, source.casefold())

    def test_optional_qt_modules_share_availability_and_import_safely(self) -> None:
        self.assertEqual(QT_ACTIONS_AVAILABLE, QT_MENUS_AVAILABLE)
        if not QT_ACTIONS_AVAILABLE:
            for value in (
                QtActionRegistry,
                PyCForgeMenu,
                QtMenuFactory,
            ):
                with self.subTest(value=value.__name__):
                    with self.assertRaisesRegex(RuntimeError, "PyQt5"):
                        value(None)


if __name__ == "__main__":
    unittest.main()
