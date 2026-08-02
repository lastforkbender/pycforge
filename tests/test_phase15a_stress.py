from __future__ import annotations

import time
import unittest

from pycforge.ide import WorkspaceController
from pycforge.ide.supervisor import (
    ConversionCancelled,
    ProcessConversionSupervisor,
)


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.002)
    return predicate()


class Phase15AStressTests(unittest.TestCase):
    def test_one_hundred_edit_convert_cancel_cycles_leave_no_worker(self):
        supervisor = ProcessConversionSupervisor()
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        futures = []

        for cycle in range(100):
            controller.set_source(
                "def value() -> int:\n"
                f"    return {cycle % 4}\n"
                f"# revision {cycle}\n"
            )
            self.assertTrue(
                wait_until(
                    lambda: controller.snapshot.revision_authenticated,
                    timeout=2,
                ),
                f"revision {cycle} did not authenticate",
            )
            future = controller.convert_async()
            controller.cancel()
            futures.append(future)

        for future in futures:
            with self.assertRaises(ConversionCancelled):
                future.result(timeout=4)
        self.assertTrue(supervisor.wait_idle(timeout=4))
        snapshot = supervisor.snapshot
        self.assertIsNone(snapshot.active_generation)
        self.assertIsNone(snapshot.pending_generation)
        self.assertIsNone(snapshot.active_pid)
        self.assertEqual(snapshot.started_workers, snapshot.reaped_workers)
        self.assertLessEqual(snapshot.maximum_simultaneous_workers, 1)


if __name__ == "__main__":
    unittest.main()
