from __future__ import annotations

from pathlib import Path
import re
import unittest

from pycforge.ide import ACTION_REGISTRY_VERSION
from pycforge.ide.action_contract import (
    ACTION_SPECS,
    MAIN_MENU_SURFACES,
    SURFACE_SPECS,
    ActionState,
    PlacementKind,
    SurfaceKind,
    validate_action_contract,
)


ROOT = Path(__file__).resolve().parents[1]

PHASE15B_ACTION_IDS = frozenset(
    {
        "file.open_python",
        "file.open_recent",
        "bundle.new_module",
        "bundle.remove_module",
        "bundle.move_up",
        "bundle.move_down",
        "bundle.make_primary",
        "file.save_python",
        "file.save_python_as",
        "output.set_destination",
        "output.save_c",
        "conversion.convert",
        "conversion.cancel",
        "edit.undo",
        "edit.redo",
        "edit.cut",
        "edit.copy",
        "edit.paste",
        "edit.select_all",
        "search.find",
        "search.replace",
        "search.next_match",
        "search.previous_match",
        "search.replace_current",
        "search.replace_all",
        "search.close",
        "view.source_bundle",
        "view.generated_c",
        "view.conversion_details",
        "tree.expand_all",
        "tree.collapse_all",
        "diagnostics.reveal_source",
        "mappings.reveal_output",
    }
)

PHASE15C_ACTION_IDS = frozenset(
    {
        "edit.duplicate_line",
        "edit.move_line_up",
        "edit.move_line_down",
        "edit.indent",
        "edit.outdent",
        "edit.toggle_comment",
        "search.bundle",
        "view.outline",
        "view.conversion_history",
        "view.whitespace",
        "view.split_source",
        "editor.toggle_fold",
        "navigation.go_to_line",
        "workspace.command_palette",
        "mappings.reveal_source",
    }
)

EXPECTED_SURFACE_IDS = frozenset(
    {
        "menu.file",
        "menu.open_recent",
        "menu.edit",
        "menu.view",
        "menu.navigate",
        "menu.conversion",
        "toolbar.workspace",
        "context.python_source",
        "context.generated_c",
        "context.source_bundle",
        "context.document_tabs",
        "context.diagnostics",
        "context.mappings",
        "context.bundle_search",
        "context.conversion_history",
        "context.inspector",
        "context.text_input",
        "context.read_only_text",
    }
)

SOURCE_MUTATING_ACTION_IDS = frozenset(
    {
        "edit.duplicate_line",
        "edit.move_line_up",
        "edit.move_line_down",
        "edit.indent",
        "edit.outdent",
        "edit.toggle_comment",
    }
)

RETIRED_THEME_TERM = "space" + "port"
FORBIDDEN_OR_DEFERRED_TOKENS = frozenset(
    {
        RETIRED_THEME_TERM,
        "run",
        "execute",
        "compile",
        "compiler",
        "assemble",
        "link",
        "linker",
        "load",
        "package",
        "packaging",
        "deploy",
        "deployment",
        "test",
        "debug",
        "debugger",
        "profile",
        "benchmark",
        "sanitize",
        "runtime-verify",
        "terminal",
        "console",
        "repl",
        "build",
        "build-system",
        "task-runner",
        "toolchain",
        "plugin",
        "extension",
        "script",
        "macro",
        "hook",
        "project",
        "project-explorer",
        "directory",
        "folder",
        "recursive",
        "scan",
        "host-discovery",
        "import",
        "environment",
        "installed-module",
        "lsp",
        "formatter",
        "refactor",
        "completion",
    }
)


def action_ids(surface_id: str) -> tuple[str, ...]:
    return tuple(
        placement.target
        for placement in SURFACE_SPECS[surface_id].placements
        if placement.kind is PlacementKind.ACTION
    )


def placement_signature(surface_id: str) -> tuple[str, ...]:
    return tuple(
        "|" if placement.kind is PlacementKind.SEPARATOR
        else f"{placement.kind.value}:{placement.target}"
        for placement in SURFACE_SPECS[surface_id].placements
    )


def action_surface_ids(action_id: str) -> frozenset[str]:
    return frozenset(
        surface_id
        for surface_id, surface in SURFACE_SPECS.items()
        if any(
            placement.kind is PlacementKind.ACTION
            and placement.target == action_id
            for placement in surface.placements
        )
    )


def metadata_tokens(action_id: str) -> frozenset[str]:
    spec = ACTION_SPECS[action_id]
    values = (
        spec.action_id,
        spec.menu_text.replace("&", ""),
        spec.toolbar_text,
        spec.tooltip,
        spec.accessible_name,
    )
    return frozenset(
        token
        for value in values
        for token in re.findall(
            r"[a-z]+(?:-[a-z]+)*",
            value.casefold().replace("_", " ").replace(".", " "),
        )
    )


class Phase15CActionContractTests(unittest.TestCase):
    def test_registry_identity_and_inventories_are_exact(self) -> None:
        self.assertEqual(
            ACTION_REGISTRY_VERSION,
            "pycforge.action-registry/0.2",
        )
        self.assertEqual(len(PHASE15B_ACTION_IDS), 33)
        self.assertEqual(len(PHASE15C_ACTION_IDS), 15)
        self.assertTrue(
            PHASE15B_ACTION_IDS.isdisjoint(PHASE15C_ACTION_IDS)
        )
        self.assertEqual(len(ACTION_SPECS), 48)
        self.assertEqual(
            set(ACTION_SPECS),
            PHASE15B_ACTION_IDS | PHASE15C_ACTION_IDS,
        )
        self.assertEqual(
            set(ACTION_SPECS).difference(PHASE15B_ACTION_IDS),
            PHASE15C_ACTION_IDS,
        )

        self.assertEqual(len(SURFACE_SPECS), 18)
        self.assertEqual(set(SURFACE_SPECS), EXPECTED_SURFACE_IDS)
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
        for surface_id in MAIN_MENU_SURFACES:
            with self.subTest(surface_id=surface_id):
                self.assertEqual(
                    SURFACE_SPECS[surface_id].kind,
                    SurfaceKind.MENU,
                )

    def test_command_palette_action_is_a_declared_window_command(self) -> None:
        spec = ACTION_SPECS["workspace.command_palette"]
        self.assertEqual(spec.menu_text, "&Command Palette…")
        self.assertEqual(spec.toolbar_text, "Commands")
        self.assertEqual(
            spec.tooltip,
            "Search and invoke enabled declared PyCForge actions",
        )
        self.assertEqual(
            spec.accessible_name,
            "Open the PyCForge command palette",
        )
        self.assertEqual(spec.icon_name, "command-palette")
        self.assertEqual(spec.shortcut, "Ctrl+Shift+P")
        self.assertEqual(spec.shortcut_context, "window")
        self.assertFalse(spec.checkable)
        self.assertFalse(spec.dynamic)
        self.assertEqual(
            action_surface_ids(spec.action_id),
            frozenset({"menu.navigate"}),
        )

    def test_new_context_surfaces_have_exact_bounded_placements(self) -> None:
        expected = {
            "context.document_tabs": (
                "action:file.save_python",
                "action:file.save_python_as",
                "|",
                "action:bundle.remove_module",
                "action:bundle.make_primary",
                "|",
                "action:view.split_source",
            ),
            "context.bundle_search": ("action:edit.copy",),
            "context.conversion_history": ("action:edit.copy",),
        }
        for surface_id, signature in expected.items():
            with self.subTest(surface_id=surface_id):
                self.assertEqual(
                    SURFACE_SPECS[surface_id].kind,
                    SurfaceKind.CONTEXT,
                )
                self.assertEqual(
                    placement_signature(surface_id),
                    signature,
                )

    def test_generated_c_context_is_exactly_read_only(self) -> None:
        self.assertEqual(
            placement_signature("context.generated_c"),
            (
                "action:edit.copy",
                "action:edit.select_all",
                "|",
                "action:search.find",
            ),
        )
        self.assertEqual(
            action_ids("context.generated_c"),
            ("edit.copy", "edit.select_all", "search.find"),
        )
        mutating_or_replacing = SOURCE_MUTATING_ACTION_IDS | {
            "edit.undo",
            "edit.redo",
            "edit.cut",
            "edit.paste",
            "search.replace",
            "search.replace_current",
            "search.replace_all",
        }
        self.assertTrue(
            mutating_or_replacing.isdisjoint(
                action_ids("context.generated_c")
            )
        )

    def test_action_metadata_avoids_excluded_and_deferred_vocabulary(
        self,
    ) -> None:
        for action_id in ACTION_SPECS:
            with self.subTest(action_id=action_id):
                self.assertTrue(
                    FORBIDDEN_OR_DEFERRED_TOKENS.isdisjoint(
                        metadata_tokens(action_id)
                    )
                )

    def test_source_mutations_are_widget_scoped_and_state_disableable(
        self,
    ) -> None:
        disabled_states = {
            action_id: ActionState(enabled=False)
            for action_id in SOURCE_MUTATING_ACTION_IDS
        }
        self.assertTrue(
            all(not state.enabled for state in disabled_states.values())
        )
        for action_id in SOURCE_MUTATING_ACTION_IDS:
            with self.subTest(action_id=action_id):
                spec = ACTION_SPECS[action_id]
                self.assertEqual(spec.shortcut_context, "widget")
                self.assertFalse(spec.dynamic)
                self.assertEqual(
                    action_surface_ids(action_id),
                    frozenset(
                        {"menu.edit", "context.python_source"}
                    ),
                )

        registry_source = (
            ROOT / "pycforge" / "ide" / "qt_actions.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "enabled = state.enabled and action_id in self._handlers",
            registry_source,
        )
        self.assertIn(
            'if self.spec(action_id).shortcut_context != "widget":',
            registry_source,
        )

    def test_complete_successor_contract_validates_without_errors(
        self,
    ) -> None:
        self.assertEqual(validate_action_contract(), ())


if __name__ == "__main__":
    unittest.main()
