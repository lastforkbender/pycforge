from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from pycforge.ide.workspace_search import (
    AsyncBundleSearchService,
    MAX_BUNDLE_DOCUMENTS,
    MAX_BUNDLE_MATCHES,
    BundleSearchMatch,
    WorkspaceSearchDocument,
    search_closed_documents,
)
import pycforge.ide.workspace_search as workspace_search


ROOT = Path(__file__).resolve().parents[1]


def document(
    document_id: str,
    text: str,
    *,
    logical_name: str | None = None,
) -> WorkspaceSearchDocument:
    return WorkspaceSearchDocument(
        document_id,
        logical_name or f"{document_id}.py",
        text,
    )


class Phase15CWorkspaceSearchTests(unittest.TestCase):
    def test_closed_bundle_search_is_literal_ordered_and_position_explicit(
        self,
    ) -> None:
        result = search_closed_documents(
            (
                document("app", "🚀 Alpha alpha_ ALPHA"),
                document("lib", "alpha + a+b\nA+B"),
            ),
            "alpha",
            generation=17,
            whole_word=True,
            preview_chars=32,
            scan_chunk=5,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.generation, 17)
        self.assertEqual(result.total_count, 3)
        self.assertFalse(result.truncated)
        self.assertEqual(
            [
                (
                    item.document_id,
                    item.document_ordinal,
                    item.start,
                    item.end,
                    item.qt_start,
                    item.qt_end,
                )
                for item in result.matches
            ],
            [
                ("app", 0, 2, 7, 3, 8),
                ("app", 0, 15, 20, 16, 21),
                ("lib", 1, 0, 5, 0, 5),
            ],
        )
        self.assertTrue(
            all(len(item.preview) <= 32 for item in result.matches)
        )
        self.assertTrue(
            all(isinstance(item, BundleSearchMatch) for item in result.matches)
        )

        exact = search_closed_documents(
            (document("lib", "a+b aab A+B"),),
            "a+b",
            match_case=True,
        )
        assert exact is not None
        self.assertEqual(
            [(item.start, item.end) for item in exact.matches],
            [(0, 3)],
        )

    def test_match_cap_is_global_and_stops_at_first_omitted_match(
        self,
    ) -> None:
        result = search_closed_documents(
            (
                document("one", "x " * 3_000),
                document("two", "x " * 3_000),
            ),
            "x",
            scan_chunk=127,
        )
        assert result is not None
        self.assertEqual(len(result.matches), MAX_BUNDLE_MATCHES)
        self.assertEqual(result.total_count, MAX_BUNDLE_MATCHES + 1)
        self.assertTrue(result.truncated)
        self.assertEqual(result.matches[2_999].document_id, "one")
        self.assertEqual(result.matches[3_000].document_id, "two")

        smaller = search_closed_documents(
            (document("one", "x x x"),),
            "x",
            match_limit=2,
        )
        assert smaller is not None
        self.assertEqual(len(smaller.matches), 2)
        self.assertEqual(smaller.total_count, 3)
        self.assertTrue(smaller.truncated)

    def test_empty_query_cancellation_and_input_bounds_fail_closed(
        self,
    ) -> None:
        empty = search_closed_documents((document("one", "text"),), "")
        assert empty is not None
        self.assertEqual(empty.matches, ())
        self.assertEqual(empty.total_count, 0)
        self.assertIsNone(
            search_closed_documents(
                (document("one", "text"),),
                "text",
                cancelled=lambda: True,
            )
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 64"):
            search_closed_documents((), "x")
        with self.assertRaisesRegex(ValueError, "between 1 and 64"):
            search_closed_documents(
                tuple(
                    document(f"d{index}", "")
                    for index in range(MAX_BUNDLE_DOCUMENTS + 1)
                ),
                "x",
            )
        with self.assertRaisesRegex(ValueError, "IDs"):
            search_closed_documents(
                (document("same", ""), document("same", "")),
                "x",
            )
        with self.assertRaisesRegex(ValueError, "logical names"):
            search_closed_documents(
                (
                    document("one", "", logical_name="same.py"),
                    document("two", "", logical_name="same.py"),
                ),
                "x",
            )
        with self.assertRaises(TypeError):
            search_closed_documents((object(),), "x")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            search_closed_documents(
                (document("one", ""),), "x", match_limit=5_001
            )

    def test_search_values_are_immutable_and_have_no_path_surface(
        self,
    ) -> None:
        captured = document("one", "needle")
        self.assertFalse(hasattr(captured, "path"))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            captured.text = "changed"  # type: ignore[misc]
        result = search_closed_documents((captured,), "needle")
        assert result is not None
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            result.total_count = 7  # type: ignore[misc]

    def test_service_keeps_one_active_and_only_latest_pending_publishes(
        self,
    ) -> None:
        active_started = Event()
        release_active = Event()
        latest_done = Event()
        observed = []
        real_search = workspace_search.search_closed_documents

        def blocked(documents, query, **kwargs):
            if query == "first":
                active_started.set()
                self.assertTrue(release_active.wait(2.0))
            return real_search(documents, query, **kwargs)

        service = AsyncBundleSearchService(scan_chunk=32)
        try:
            with patch.object(
                workspace_search, "search_closed_documents", blocked
            ):
                first = service.submit(
                    (document("one", "first " * 10_000),),
                    "first",
                    callback=lambda result: observed.append(
                        result.generation
                    ),
                )
                self.assertTrue(active_started.wait(2.0))
                middle = service.submit(
                    (document("one", "middle"),),
                    "middle",
                    callback=lambda result: observed.append(
                        result.generation
                    ),
                )
                latest = service.submit(
                    (document("one", "latest"),),
                    "latest",
                    callback=lambda result: (
                        observed.append(result.generation),
                        latest_done.set(),
                    ),
                )
                self.assertEqual(service.active_generation, first)
                self.assertEqual(service.pending_generation, latest)
                self.assertNotEqual(middle, latest)
                release_active.set()
                self.assertTrue(latest_done.wait(2.0))
            self.assertEqual(observed, [latest])
            self.assertTrue(service.worker_is_daemon)
        finally:
            release_active.set()
            service.close()

    def test_cancel_and_close_suppress_stale_callbacks(
        self,
    ) -> None:
        active_started = Event()
        release_active = Event()
        observed = []
        real_search = workspace_search.search_closed_documents

        def blocked(documents, query, **kwargs):
            active_started.set()
            self.assertTrue(release_active.wait(2.0))
            return real_search(documents, query, **kwargs)

        service = AsyncBundleSearchService()
        try:
            with patch.object(
                workspace_search, "search_closed_documents", blocked
            ):
                generation = service.submit(
                    (document("one", "needle " * 20_000),),
                    "needle",
                    callback=observed.append,
                )
                self.assertTrue(active_started.wait(2.0))
                self.assertEqual(service.active_generation, generation)
                self.assertGreater(service.cancel(), generation)
                release_active.set()
            self.assertEqual(observed, [])
        finally:
            release_active.set()
            service.close()
        self.assertTrue(service.is_closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            service.submit(
                (document("one", "x"),),
                "x",
                callback=observed.append,
            )

    def test_observer_and_callback_failures_do_not_retire_worker(
        self,
    ) -> None:
        completed = Event()
        fault_started = Event()
        observed = []
        real_search = workspace_search.search_closed_documents

        def fail_once(documents, query, **kwargs):
            if query == "fault":
                fault_started.set()
                raise RuntimeError("injected observer failure")
            return real_search(documents, query, **kwargs)

        service = AsyncBundleSearchService()
        try:
            with patch.object(
                workspace_search, "search_closed_documents", fail_once
            ):
                service.submit(
                    (document("one", "fault"),),
                    "fault",
                    callback=observed.append,
                )
                self.assertTrue(fault_started.wait(2.0))
                service.submit(
                    (document("one", "ready"),),
                    "ready",
                    callback=lambda result: (
                        observed.append(result.total_count),
                        completed.set(),
                        (_ for _ in ()).throw(
                            RuntimeError("callback failure")
                        ),
                    ),
                )
                self.assertTrue(completed.wait(2.0))
            self.assertEqual(observed, [1])
        finally:
            service.close()

    def test_module_is_headless_bounded_and_contains_no_file_io(
        self,
    ) -> None:
        path = ROOT / "pycforge/ide/workspace_search.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        self.assertLess(len(source.splitlines()), 600)
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("pathlib", imported_names)
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("open", called_names)


if __name__ == "__main__":
    unittest.main()
