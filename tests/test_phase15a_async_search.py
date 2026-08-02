from __future__ import annotations

import os
from threading import Event
from time import monotonic
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pycforge.ide.editor import CodeEditor  # noqa: E402
from pycforge.ide.find_replace import (  # noqa: E402
    FindReplaceBar,
    QT_AVAILABLE,
    find_literal_ranges,
)
from pycforge.ide.search_service import (  # noqa: E402
    AsyncLiteralSearchService,
)
import pycforge.ide.search_service as search_service_module  # noqa: E402


if QT_AVAILABLE:  # pragma: no branch - selected by the test environment
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication


class Phase15AAsyncSearchServiceTests(unittest.TestCase):
    def test_reference_literal_api_remains_codepoint_based_and_exact(self) -> None:
        self.assertEqual(
            find_literal_ranges("🚀 Alpha alpha_ ALPHA", "alpha", whole_word=True),
            ((2, 7), (15, 20)),
        )
        self.assertEqual(
            find_literal_ranges("a+b aab", "a+b", match_case=True),
            ((0, 3),),
        )

    def test_worker_returns_capped_ranges_total_and_utf16_positions(self) -> None:
        completed = Event()
        observed = []
        service = AsyncLiteralSearchService(match_limit=3, scan_chunk=5)
        try:
            generation = service.submit(
                "🚀x " * 10,
                "x",
                callback=lambda result: (observed.append(result), completed.set()),
            )
            self.assertTrue(completed.wait(2.0))
            self.assertEqual(observed[0].generation, generation)
            self.assertEqual(observed[0].total_count, 10)
            self.assertTrue(observed[0].truncated)
            self.assertEqual(observed[0].ranges, ((2, 3), (6, 7), (10, 11)))
            self.assertTrue(service.worker_is_daemon)
        finally:
            service.close()

    def test_active_scan_is_cancelled_and_only_latest_pending_result_publishes(self) -> None:
        active_started = Event()
        release_active = Event()
        latest_completed = Event()
        observed = []
        real_search = search_service_module._bounded_literal_search

        def blocked_search(request, **kwargs):
            if request.query == "first":
                active_started.set()
                self.assertTrue(release_active.wait(2.0))
            return real_search(request, **kwargs)

        service = AsyncLiteralSearchService(match_limit=10, scan_chunk=32)
        try:
            with patch.object(
                search_service_module, "_bounded_literal_search", blocked_search
            ):
                first = service.submit(
                    "first " * 50_000,
                    "first",
                    callback=lambda result: observed.append(result.generation),
                )
                self.assertTrue(active_started.wait(2.0))
                second = service.submit(
                    "second",
                    "second",
                    callback=lambda result: observed.append(result.generation),
                )
                latest = service.submit(
                    "latest",
                    "latest",
                    callback=lambda result: (
                        observed.append(result.generation),
                        latest_completed.set(),
                    ),
                )
                self.assertEqual(service.active_generation, first)
                self.assertEqual(service.pending_generation, latest)
                self.assertNotEqual(second, latest)
                release_active.set()
                self.assertTrue(latest_completed.wait(2.0))
            self.assertEqual(observed, [latest])
        finally:
            release_active.set()
            service.close()

    def test_cancel_suppresses_callback_and_submit_does_not_scan_caller_thread(self) -> None:
        active_started = Event()
        release_active = Event()
        observed = []
        real_search = search_service_module._bounded_literal_search

        def blocked_search(request, **kwargs):
            active_started.set()
            self.assertTrue(release_active.wait(2.0))
            return real_search(request, **kwargs)

        service = AsyncLiteralSearchService()
        try:
            with patch.object(
                search_service_module, "_bounded_literal_search", blocked_search
            ):
                text = "no-match\n" * 100_000
                started = monotonic()
                service.submit(
                    text,
                    "needle",
                    callback=lambda result: observed.append(result),
                )
                self.assertLess(monotonic() - started, 0.1)
                self.assertTrue(active_started.wait(2.0))
                service.cancel()
                release_active.set()
            self.assertFalse(observed)
        finally:
            release_active.set()
            service.close()

    def test_chunk_boundaries_match_the_headless_reference(self) -> None:
        text = "xalpha alpha_ alpha ALPHA\nalpha"
        completed = Event()
        observed = []
        service = AsyncLiteralSearchService(match_limit=100, scan_chunk=7)
        try:
            service.submit(
                text,
                "alpha",
                whole_word=True,
                callback=lambda result: (observed.append(result), completed.set()),
            )
            self.assertTrue(completed.wait(2.0))
            expected = find_literal_ranges(text, "alpha", whole_word=True)
            self.assertEqual(observed[0].total_count, len(expected))
            self.assertEqual(observed[0].ranges, expected)
        finally:
            service.close()

    def test_consumer_callback_failure_does_not_retire_the_worker(self) -> None:
        failed_called = Event()
        completed = Event()
        observed = []
        service = AsyncLiteralSearchService()

        def failed_receiver(_result) -> None:
            failed_called.set()
            raise RuntimeError("receiver disappeared")

        try:
            service.submit(
                "first",
                "first",
                callback=failed_receiver,
            )
            self.assertTrue(failed_called.wait(2.0))
            service.submit(
                "second",
                "second",
                callback=lambda result: (observed.append(result), completed.set()),
            )
            self.assertTrue(completed.wait(2.0))
            self.assertEqual(observed[0].total_count, 1)
        finally:
            service.close()


@unittest.skipUnless(QT_AVAILABLE, "PyQt5 is unavailable")
class Phase15AAsyncSearchQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(["pycforge-search-tests"])

    def test_debounce_publish_utf16_ranges_and_close_clears_markers(self) -> None:
        editor = CodeEditor(language="python")
        editor.setPlainText("🚀 alpha\nalpha")
        bar = FindReplaceBar()
        bar.attach_editor(editor)
        bar.open_find()
        bar.find_edit.setText("alpha")
        self.assertGreaterEqual(bar._search_timer.interval(), 100)
        self.assertLessEqual(bar._search_timer.interval(), 200)

        deadline = monotonic() + 2.0
        while bar.match_count != 2 and monotonic() < deadline:
            QTest.qWait(20)
            self.app.processEvents()

        self.assertEqual(bar.match_count, 2)
        self.assertEqual(
            tuple((marker.start, marker.end) for marker in editor.markers("search")),
            ((3, 8), (9, 14)),
        )
        bar.close_bar()
        self.assertEqual(editor.markers("search"), ())
        self.assertEqual(bar.stored_match_count, 0)
        editor.close()
        bar.close()


if __name__ == "__main__":
    unittest.main()
