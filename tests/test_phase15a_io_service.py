from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from threading import Event

from pycforge.ide.io_service import (
    StaleWorkspaceWrite,
    WorkspaceIOService,
)


class Phase15AWorkspaceIOTests(unittest.TestCase):
    def test_read_and_atomic_write_run_outside_calling_thread(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"
            path.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            service = WorkspaceIOService()
            self.addCleanup(service.close)

            read = service.read_text(path)
            observation = read.result(timeout=2)
            self.assertEqual(observation.text, path.read_text(encoding="utf-8"))
            self.assertEqual(len(observation.utf8_sha256), 64)

            written = service.write_text(path, "replacement\n").result(timeout=2)
            self.assertEqual(written, str(path))
            self.assertEqual(path.read_text(encoding="utf-8"), "replacement\n")
            self.assertFalse(any(path.parent.glob(".source.py.*.tmp")))

    def test_slow_guard_does_not_block_submit_and_stale_write_never_replaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.c"
            path.write_text("last-known-good", encoding="utf-8")
            guard_entered = Event()
            release_guard = Event()

            def guard() -> bool:
                guard_entered.set()
                if not release_guard.wait(timeout=5):
                    raise RuntimeError("test guard timed out")
                return False

            service = WorkspaceIOService()
            self.addCleanup(service.close)
            started = time.monotonic()
            future = service.write_text(
                path,
                "stale candidate",
                before_replace=guard,
            )
            self.assertLess(time.monotonic() - started, 0.100)
            self.assertTrue(guard_entered.wait(timeout=2))
            self.assertEqual(path.read_text(encoding="utf-8"), "last-known-good")
            release_guard.set()
            with self.assertRaises(StaleWorkspaceWrite):
                future.result(timeout=2)
            self.assertEqual(path.read_text(encoding="utf-8"), "last-known-good")
            self.assertFalse(any(path.parent.glob(".generated.c.*.tmp")))

    def test_close_wait_false_accepts_while_daemon_operation_is_blocked(self):
        service = WorkspaceIOService(workers=1, capacity=2)
        started = Event()
        release = Event()

        def blocked():
            started.set()
            release.wait(timeout=5)
            return "done"

        future = service._submit(blocked)
        self.assertTrue(started.wait(timeout=1))
        before = time.monotonic()
        service.close(wait=False)
        self.assertLess(time.monotonic() - before, 0.250)
        release.set()
        self.assertEqual(future.result(timeout=2), "done")
        service.close(wait=True, timeout=2)


if __name__ == "__main__":
    unittest.main()
