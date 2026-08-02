from __future__ import annotations

import time
import unittest

from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.facade import PythonToCConverter
from pycforge.ide import WorkspaceController, WorkspaceState
from pycforge.ide.supervisor import (
    ConversionCancelled,
    ProcessConversionSupervisor,
    WorkerFailure,
)
from pycforge.ide.worker_protocol import (
    encode_terminal,
    receive_request,
    send_event,
)


SOURCE_A = "def value() -> int:\n    return 1\n"
SOURCE_B = "def value() -> int:\n    return 2\n"
SOURCE_C = "def value() -> int:\n    return 3\n"


def second_generation_hangs(
    request_connection,
    event_connection,
    control_connection,
) -> None:
    request = receive_request(request_connection)
    request_connection.close()
    if request.generation == 2:
        while True:
            time.sleep(1)
    result = PythonToCConverter().convert(
        request.request,
        observation=request.observation,
        cancellation=CancellationToken(),
    )
    send_event(event_connection, encode_terminal(request, result))
    control_connection.close()
    event_connection.close()


def second_generation_malformed(
    request_connection,
    event_connection,
    control_connection,
) -> None:
    request = receive_request(request_connection)
    request_connection.close()
    if request.generation == 2:
        event_connection.send_bytes(b'{"malformed":true}')
    else:
        result = PythonToCConverter().convert(
            request.request,
            observation=request.observation,
            cancellation=CancellationToken(),
        )
        send_event(event_connection, encode_terminal(request, result))
    control_connection.close()
    event_connection.close()


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class Phase15AControllerCustodyTests(unittest.TestCase):
    def controller_with(self, worker_target):
        supervisor = ProcessConversionSupervisor(worker_target=worker_target)
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(supervisor.close)
        self.addCleanup(controller.close)
        return controller, supervisor

    def wait_authenticated(self, controller: WorkspaceController) -> None:
        self.assertTrue(
            wait_until(lambda: controller.snapshot.revision_authenticated),
            "workspace revision authentication timed out",
        )

    def test_cancel_requested_is_synchronous_and_last_good_c_is_preserved(self):
        controller, supervisor = self.controller_with(second_generation_hangs)
        controller.set_source(SOURCE_A)
        first = controller.convert()
        prior_c = first.generated_c
        prior_mappings = controller.snapshot.mappings
        self.assertTrue(controller.snapshot.can_save_c)

        controller.set_source(SOURCE_B)
        second = controller.convert_async()
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 2)
        )
        started = time.monotonic()
        controller.cancel()
        visible_elapsed = time.monotonic() - started

        self.assertLess(visible_elapsed, 0.100)
        self.assertEqual(
            controller.snapshot.state,
            WorkspaceState.CANCEL_REQUESTED,
        )
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertEqual(controller.snapshot.mappings, prior_mappings)
        self.assertFalse(controller.snapshot.can_save_c)
        with self.assertRaises(ConversionCancelled):
            second.result(timeout=3)
        self.assertEqual(controller.snapshot.state, WorkspaceState.CANCELED)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertFalse(controller.snapshot.can_save_c)

        controller.set_source(SOURCE_C)
        recovered = controller.convert()
        self.assertEqual(controller.snapshot.generated_c, recovered.generated_c)
        self.assertNotEqual(controller.snapshot.generated_c, prior_c)
        self.assertTrue(controller.snapshot.can_save_c)

    def test_malformed_worker_never_replaces_last_good_and_retry_recovers(self):
        controller, _supervisor = self.controller_with(
            second_generation_malformed
        )
        controller.set_source(SOURCE_A)
        controller.convert()
        prior_c = controller.snapshot.generated_c
        prior_mappings = controller.snapshot.mappings

        controller.set_source(SOURCE_B)
        failed = controller.convert_async()
        with self.assertRaises(WorkerFailure) as caught:
            failed.result(timeout=5)
        self.assertEqual(
            caught.exception.classification,
            "malformed-worker-envelope",
        )
        self.assertEqual(controller.snapshot.state, WorkspaceState.FAILED)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertEqual(controller.snapshot.mappings, prior_mappings)
        self.assertFalse(controller.snapshot.can_save_c)

        controller.set_source(SOURCE_C)
        controller.convert()
        self.assertEqual(controller.snapshot.state, WorkspaceState.CONVERTED)
        self.assertNotEqual(controller.snapshot.generated_c, prior_c)
        self.assertTrue(controller.snapshot.can_save_c)

    def test_a_b_a_fingerprint_return_does_not_revalidate_old_result(self):
        controller = WorkspaceController()
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_A)
        controller.convert()
        first = controller.snapshot
        first_bundle = first.bundle_fingerprint
        first_generation = first.revision_generation
        first_c = first.generated_c

        controller.set_source(SOURCE_B)
        controller.set_source(SOURCE_A)
        self.wait_authenticated(controller)
        returned = controller.snapshot

        self.assertEqual(returned.bundle_fingerprint, first_bundle)
        self.assertGreater(returned.revision_generation, first_generation)
        self.assertEqual(returned.generated_c, first_c)
        self.assertEqual(returned.state, WorkspaceState.STALE)
        self.assertFalse(returned.can_save_c)

    def test_progress_and_terminal_publication_require_current_generation(self):
        controller, supervisor = self.controller_with(second_generation_hangs)
        controller.set_source(SOURCE_A)
        controller.convert()
        prior_c = controller.snapshot.generated_c

        controller.set_source(SOURCE_B)
        obsolete = controller.convert_async()
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 2)
        )
        controller.set_source(SOURCE_C)
        retired_generation = controller.snapshot.revision_generation
        with self.assertRaises(ConversionCancelled):
            obsolete.result(timeout=3)

        self.assertEqual(
            controller.snapshot.revision_generation,
            retired_generation,
        )
        self.assertEqual(controller.snapshot.request_sequence, 2)
        self.assertEqual(controller.snapshot.generated_c, prior_c)
        self.assertEqual(controller.snapshot.state, WorkspaceState.STALE)
        self.assertFalse(controller.snapshot.can_save_c)


if __name__ == "__main__":
    unittest.main()
