from __future__ import annotations

from dataclasses import fields
import unittest

from pycforge.ide.action_contract import (
    ACTION_SPECS,
    ActionSpec,
    ActionState,
)
from pycforge.ide.command_palette import (
    MAX_COMMAND_PALETTE_QUERY_CHARS,
    MAX_COMMAND_PALETTE_RESULTS,
    CommandPaletteItem,
    project_command_palette,
    strip_mnemonics,
)


class Phase15CCommandPaletteTests(unittest.TestCase):
    def test_projection_contains_static_visible_registry_actions_only(self):
        states = {
            "file.open_python": ActionState(enabled=False),
            "file.save_python": ActionState(visible=False),
        }
        projection = project_command_palette(states=states)
        ids = tuple(item.action_id for item in projection.items)
        self.assertNotIn("file.open_recent", ids)
        self.assertNotIn("file.save_python", ids)
        self.assertIn("file.open_python", ids)
        opened = next(
            item
            for item in projection.items
            if item.action_id == "file.open_python"
        )
        self.assertFalse(opened.enabled)
        self.assertEqual(opened.label, "Open Python…")
        self.assertEqual(opened.shortcut, "Open")
        self.assertEqual(opened.shortcut_kind, "standard")

    def test_filtering_is_ranked_case_insensitive_and_deterministic(self):
        first = project_command_palette("save generated")
        second = project_command_palette("  SAVE   generated ")
        self.assertEqual(first.items, second.items)
        self.assertEqual(first.query, "save generated")
        self.assertEqual(first.items[0].action_id, "output.save_c")

        by_id = project_command_palette("bundle primary")
        self.assertEqual(
            by_id.items[0].action_id,
            "bundle.make_primary",
        )

    def test_result_limit_is_absolute_and_reports_truncation(self):
        projection = project_command_palette(limit=3)
        self.assertEqual(len(projection.items), 3)
        self.assertGreater(projection.total_count, 3)
        self.assertTrue(projection.truncated)
        with self.assertRaises(ValueError):
            project_command_palette(limit=MAX_COMMAND_PALETTE_RESULTS + 1)
        with self.assertRaises(ValueError):
            project_command_palette(
                "x" * (MAX_COMMAND_PALETTE_QUERY_CHARS + 1)
            )

    def test_mnemonics_are_removed_without_losing_literal_ampersands(self):
        self.assertEqual(strip_mnemonics("&Open && Inspect"), "Open & Inspect")
        self.assertEqual(strip_mnemonics("Cu&t"), "Cut")

    def test_projection_carries_no_handler_or_command_execution_surface(self):
        names = {field.name for field in fields(CommandPaletteItem)}
        self.assertNotIn("handler", names)
        self.assertNotIn("callback", names)
        self.assertNotIn("command", names)
        for item in project_command_palette().items:
            self.assertTrue(all(
                not callable(getattr(item, name))
                for name in names
            ))

    def test_custom_specs_remain_bounded_and_state_checked(self):
        specs = {
            f"safe.action_{index}": ActionSpec(
                action_id=f"safe.action_{index}",
                menu_text=f"&Action {index}",
                toolbar_text=f"Action {index}",
                tooltip=f"Declared action {index}",
                accessible_name=f"Action {index}",
            )
            for index in range(80)
        }
        projection = project_command_palette(action_specs=specs)
        self.assertEqual(
            len(projection.items),
            MAX_COMMAND_PALETTE_RESULTS,
        )
        self.assertEqual(projection.total_count, 80)
        with self.assertRaises(KeyError):
            project_command_palette(
                action_specs=specs,
                states={"outside.action": ActionState()},
            )
        with self.assertRaises(TypeError):
            project_command_palette(
                states={"file.open_python": object()},  # type: ignore[dict-item]
            )
        with self.assertRaises(TypeError):
            project_command_palette(
                action_specs={"safe.action": object()},  # type: ignore[dict-item]
            )
        self.assertGreater(len(ACTION_SPECS), 0)


if __name__ == "__main__":
    unittest.main()
