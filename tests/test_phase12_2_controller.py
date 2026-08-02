from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from pycforge.ide import WorkspaceController, WorkspaceState
from pycforge.ide.supervisor import (
    ConversionCancelled,
    ProcessConversionSupervisor,
    WorkerFailure,
)
from tests.test_phase15a_controller import (
    second_generation_hangs,
    second_generation_malformed,
)
from tests.test_phase15a_supervisor import generation_one_hangs_then_convert


SOURCE_A = "def alpha(value: int) -> int:\n    return value + 1\n"
SOURCE_B = "def beta(value: int) -> int:\n    return value + 2\n"
SOURCE_PRIOR = "def prior(value: int) -> int:\n    return value - 1\n"
SOURCE_FAILURE = "def explode(value: int) -> int:\n    return value + 3\n"


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class FailOnceSupervisor:
    def __init__(self) -> None:
        self._failed = False
        self._real = ProcessConversionSupervisor()

    def submit(self, **kwargs):
        if not self._failed:
            self._failed = True
            raise RuntimeError("injected submit failure")
        return self._real.submit(**kwargs)

    def cancel(self, generation=None):
        self._real.cancel(generation)

    def close(self):
        self._real.close()


class Phase122ControllerHardeningTests(unittest.TestCase):
    def assert_failure_artifacts_cleared(self, controller: WorkspaceController) -> None:
        snapshot = controller.snapshot
        self.assertEqual(snapshot.state, WorkspaceState.FAILED)
        self.assertEqual(snapshot.diagnostics, ())
        self.assertEqual(snapshot.summary, ())
        self.assertIsNone(snapshot.decision_trace)
        self.assertIsNone(snapshot.telemetry)
        self.assertIsNone(snapshot.conversion_summary)
        self.assertIsNone(snapshot.active_stage)
        self.assertEqual(snapshot.completed_stages, 0)
        self.assertEqual(snapshot.total_stages, 0)
        self.assertFalse(snapshot.can_save_c)
        self.assertTrue(snapshot.can_convert)

    def test_a_b_a_edit_retires_cancellation_ignoring_request(self):
        supervisor = ProcessConversionSupervisor(
            worker_target=generation_one_hangs_then_convert
        )
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_A)
        obsolete = controller.convert_async()
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 1)
        )

        controller.set_source(SOURCE_B)
        controller.set_source(SOURCE_A)
        retired_generation = controller.snapshot.revision_generation
        self.assertIsNone(controller.snapshot.generated_c)
        self.assertFalse(controller.snapshot.can_save_c)

        with self.assertRaises(ConversionCancelled):
            obsolete.result(timeout=3)
        self.assertEqual(
            controller.snapshot.revision_generation,
            retired_generation,
        )
        self.assertIsNone(controller.snapshot.generated_c)
        self.assertFalse(controller.snapshot.can_save_c)

    def test_a_b_a_edit_cannot_replace_or_revalidate_prior_c(self):
        supervisor = ProcessConversionSupervisor(
            worker_target=second_generation_hangs
        )
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_PRIOR)
        controller.convert()
        prior_c = controller.snapshot.generated_c
        prior_mappings = controller.snapshot.mappings

        controller.set_source(SOURCE_A)
        obsolete = controller.convert_async()
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 2)
        )
        controller.set_source(SOURCE_B)
        controller.set_source(SOURCE_A)
        self.assertEqual(controller.snapshot.state, WorkspaceState.STALE)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertEqual(controller.snapshot.mappings, prior_mappings)
        self.assertFalse(controller.snapshot.can_save_c)

        with self.assertRaises(ConversionCancelled):
            obsolete.result(timeout=3)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertFalse(controller.snapshot.can_save_c)

    def test_duplicate_save_as_is_rejected_before_touching_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_path = root / "first.py"
            second_path = root / "second.py"
            first_path.write_bytes(SOURCE_A.encode("utf-8"))
            second_bytes = b"# destination custody\r\ndef second(value: int) -> int:\r\n    return value\r\n"
            second_path.write_bytes(second_bytes)

            controller = WorkspaceController()
            self.addCleanup(controller.close)
            controller.open_document(first_path)
            controller.open_document(second_path)
            controller.update_document("doc-main", SOURCE_B)
            self.assertTrue(
                wait_until(lambda: controller.snapshot.revision_authenticated)
            )
            before = controller.snapshot

            with self.assertRaises(ValueError):
                controller.save_document("doc-main", second_path)

            self.assertEqual(second_path.read_bytes(), second_bytes)
            self.assertEqual(controller.snapshot, before)
            self.assertFalse(any(root.glob(".second.py.*.tmp")))

    def test_worker_exception_fails_safely_and_allows_retry(self):
        supervisor = ProcessConversionSupervisor(
            worker_target=second_generation_malformed
        )
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_PRIOR)
        controller.convert()
        prior_c = controller.snapshot.generated_c
        prior_mappings = controller.snapshot.mappings

        controller.set_source(SOURCE_FAILURE)
        failed = controller.convert_async()
        with self.assertRaises(WorkerFailure):
            failed.result(timeout=5)

        self.assert_failure_artifacts_cleared(controller)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertEqual(controller.snapshot.mappings, prior_mappings)
        self.assertEqual(controller.snapshot.stale_reason, "conversion-failed")

        recovered = controller.convert()
        self.assertEqual(controller.snapshot.state, WorkspaceState.CONVERTED)
        self.assertEqual(controller.snapshot.generated_c, recovered.generated_c)
        self.assertNotEqual(controller.snapshot.generated_c, prior_c)
        self.assertTrue(controller.snapshot.can_save_c)

    def test_submit_exception_fails_safely_and_allows_retry(self):
        supervisor = FailOnceSupervisor()
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_A)
        self.assertTrue(
            wait_until(lambda: controller.snapshot.revision_authenticated)
        )

        with self.assertRaisesRegex(RuntimeError, "injected submit failure"):
            controller.convert_async().result(timeout=1)

        self.assert_failure_artifacts_cleared(controller)
        self.assertIsNone(controller.snapshot.generated_c)

        recovered = controller.convert()
        self.assertEqual(controller.snapshot.state, WorkspaceState.CONVERTED)
        self.assertEqual(controller.snapshot.generated_c, recovered.generated_c)
        self.assertTrue(controller.snapshot.can_save_c)


if __name__ == "__main__":
    unittest.main()
