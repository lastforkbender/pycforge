from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import unittest

from pycforge.ide.workspace_session import (
    MAX_EDITOR_PANES,
    SplitOrientation,
    WorkspaceSession,
    activate_document,
    activate_pane,
    close_split,
    create_workspace_session,
    reconcile_session,
    split_session,
)


class Phase15CWorkspaceSessionTests(unittest.TestCase):
    def test_tabs_and_active_document_are_identifier_only(self):
        session = create_workspace_session(
            ("doc-main", "doc-lib"),
            "doc-lib",
        )
        self.assertEqual(session.document_ids, ("doc-main", "doc-lib"))
        self.assertEqual(session.pane_document_ids, ("doc-lib",))
        self.assertEqual(session.active_document_id, "doc-lib")
        self.assertEqual(
            {field.name for field in fields(WorkspaceSession)},
            {
                "document_ids",
                "pane_document_ids",
                "active_pane",
                "split_orientation",
            },
        )
        with self.assertRaises(FrozenInstanceError):
            session.active_pane = 1  # type: ignore[misc]

    def test_split_is_bounded_to_two_panes_and_reorients(self):
        session = create_workspace_session(("a", "b"), "a")
        session = split_session(
            session,
            SplitOrientation.VERTICAL,
            document_id="b",
        )
        self.assertTrue(session.is_split)
        self.assertEqual(len(session.pane_document_ids), MAX_EDITOR_PANES)
        self.assertEqual(session.pane_document_ids, ("a", "b"))
        self.assertEqual(session.active_pane, 1)
        self.assertEqual(session.active_document_id, "b")

        reoriented = split_session(session, "horizontal")
        self.assertEqual(
            reoriented.pane_document_ids,
            session.pane_document_ids,
        )
        self.assertEqual(
            reoriented.split_orientation,
            SplitOrientation.HORIZONTAL,
        )

    def test_activation_and_close_split_are_deterministic(self):
        session = split_session(
            create_workspace_session(("a", "b", "c")),
            "vertical",
            document_id="b",
        )
        session = activate_document(session, "c", pane=0)
        self.assertEqual(session.pane_document_ids, ("c", "b"))
        self.assertEqual(session.active_document_id, "c")
        session = activate_pane(session, 1)
        self.assertEqual(session.active_document_id, "b")
        session = close_split(session)
        self.assertFalse(session.is_split)
        self.assertEqual(session.pane_document_ids, ("b",))
        self.assertEqual(
            session.split_orientation,
            SplitOrientation.VERTICAL,
        )

    def test_reconcile_uses_exact_current_order_and_repairs_removed_panes(self):
        session = split_session(
            create_workspace_session(("a", "b", "c"), "a"),
            "horizontal",
            document_id="b",
        )
        reconciled = reconcile_session(
            session,
            ("c", "a", "d"),
            active_document_id="d",
        )
        self.assertEqual(reconciled.document_ids, ("c", "a", "d"))
        self.assertEqual(reconciled.pane_document_ids, ("a", "d"))
        self.assertEqual(reconciled.active_document_id, "d")

        repaired = reconcile_session(
            activate_pane(reconciled, 0),
            ("c", "d"),
        )
        self.assertEqual(repaired.pane_document_ids, ("c", "d"))
        self.assertEqual(repaired.active_document_id, "c")

    def test_invalid_or_external_document_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            create_workspace_session(())
        with self.assertRaises(TypeError):
            create_workspace_session("abc")
        with self.assertRaises(ValueError):
            create_workspace_session(("a", "a"))
        session = create_workspace_session(("a",))
        with self.assertRaises(ValueError):
            activate_document(session, "external")
        with self.assertRaises(ValueError):
            split_session(session, "diagonal")
        with self.assertRaises(ValueError):
            reconcile_session(session, ("b",), active_document_id="a")


if __name__ == "__main__":
    unittest.main()
