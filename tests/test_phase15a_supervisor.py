from __future__ import annotations

import os
import time
import unittest

from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ConversionRequest
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_json
from pycforge.converter.facade import PythonToCConverter
from pycforge.ide.supervisor import (
    ConversionCancelled,
    ConversionSuperseded,
    ProcessConversionSupervisor,
    WorkerFailure,
)
from pycforge.ide.worker_protocol import (
    encode_terminal,
    receive_request,
    send_event,
)


SOURCE = "def add(a: int, b: int) -> int:\n    return a + b\n"


def generation_one_hangs_then_convert(
    request_connection,
    event_connection,
    control_connection,
) -> None:
    request = receive_request(request_connection)
    request_connection.close()
    if request.generation == 1:
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


def abrupt_worker(
    request_connection,
    event_connection,
    control_connection,
) -> None:
    receive_request(request_connection)
    os._exit(29)


def malformed_worker(
    request_connection,
    event_connection,
    control_connection,
) -> None:
    receive_request(request_connection)
    event_connection.send_bytes(b'{"not":"a worker event"}')
    event_connection.close()
    control_connection.close()


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class Phase15AProcessSupervisorTests(unittest.TestCase):
    def test_spawned_result_is_exactly_direct_equivalent(self) -> None:
        request = ConversionRequest.from_source(SOURCE)
        direct = PythonToCConverter().convert(
            request,
            observation=ObservationOptions("Full", True),
        )
        from pycforge.ide.worker_protocol import bundle_fingerprint_for_request

        supervisor = ProcessConversionSupervisor()
        self.addCleanup(supervisor.close)
        isolated = supervisor.submit(
            generation=1,
            bundle_fingerprint=bundle_fingerprint_for_request(request),
            request=request,
        ).result(timeout=10)

        self.assertEqual(result_to_json(isolated), result_to_json(direct))
        self.assertEqual(
            isolated.stage_artifact.artifact_fingerprint,
            direct.stage_artifact.artifact_fingerprint,
        )
        self.assertTrue(supervisor.wait_idle(timeout=2))
        snapshot = supervisor.snapshot
        self.assertEqual(snapshot.started_workers, 1)
        self.assertEqual(snapshot.reaped_workers, 1)
        self.assertEqual(snapshot.maximum_simultaneous_workers, 1)
        self.assertIsNone(snapshot.active_pid)

    def test_one_active_one_latest_pending_and_hard_stop(self) -> None:
        from pycforge.ide.worker_protocol import bundle_fingerprint_for_request

        request = ConversionRequest.from_source(SOURCE)
        bundle = bundle_fingerprint_for_request(request)
        supervisor = ProcessConversionSupervisor(
            worker_target=generation_one_hangs_then_convert
        )
        self.addCleanup(supervisor.close)
        first = supervisor.submit(
            generation=1,
            bundle_fingerprint=bundle,
            request=request,
        )
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 1)
        )
        replaced = supervisor.submit(
            generation=2,
            bundle_fingerprint=bundle,
            request=request,
        )
        latest = supervisor.submit(
            generation=3,
            bundle_fingerprint=bundle,
            request=request,
        )
        self.assertEqual(supervisor.snapshot.pending_generation, 3)
        with self.assertRaises(ConversionSuperseded):
            replaced.result(timeout=2)
        with self.assertRaises(ConversionSuperseded):
            first.result(timeout=3)
        result = latest.result(timeout=5)
        self.assertIsNotNone(result.generated_c)
        self.assertTrue(supervisor.wait_idle(timeout=2))
        snapshot = supervisor.snapshot
        self.assertEqual(snapshot.started_workers, 2)
        self.assertEqual(snapshot.reaped_workers, 2)
        self.assertEqual(snapshot.forced_terminations, 1)
        self.assertLessEqual(
            snapshot.latest_pending_start_delay_seconds or 1.0,
            0.250,
        )

    def test_cancel_is_nonblocking_and_reclaims_noncooperative_worker(self) -> None:
        from pycforge.ide.worker_protocol import bundle_fingerprint_for_request

        request = ConversionRequest.from_source(SOURCE)
        supervisor = ProcessConversionSupervisor(
            worker_target=generation_one_hangs_then_convert
        )
        self.addCleanup(supervisor.close)
        future = supervisor.submit(
            generation=1,
            bundle_fingerprint=bundle_fingerprint_for_request(request),
            request=request,
        )
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 1)
        )
        started = time.monotonic()
        supervisor.cancel(1)
        call_elapsed = time.monotonic() - started
        with self.assertRaises(ConversionCancelled):
            future.result(timeout=3)
        reclaim_elapsed = time.monotonic() - started

        self.assertLess(call_elapsed, 0.100)
        self.assertLess(reclaim_elapsed, 2.000)
        self.assertTrue(supervisor.wait_idle(timeout=1))
        self.assertIsNone(supervisor.snapshot.active_pid)

    def test_abrupt_and_malformed_workers_fail_closed(self) -> None:
        from pycforge.ide.worker_protocol import bundle_fingerprint_for_request

        request = ConversionRequest.from_source(SOURCE)
        bundle = bundle_fingerprint_for_request(request)
        for target, classification in (
            (abrupt_worker, "abrupt-worker-exit"),
            (malformed_worker, "malformed-worker-envelope"),
        ):
            with self.subTest(classification=classification):
                supervisor = ProcessConversionSupervisor(worker_target=target)
                try:
                    future = supervisor.submit(
                        generation=1,
                        bundle_fingerprint=bundle,
                        request=request,
                    )
                    with self.assertRaises(WorkerFailure) as caught:
                        future.result(timeout=5)
                    self.assertEqual(
                        caught.exception.classification,
                        classification,
                    )
                    self.assertTrue(supervisor.wait_idle(timeout=1))
                finally:
                    supervisor.close(timeout=3)

    def test_close_accepts_immediately_and_reaps_asynchronously(self) -> None:
        from pycforge.ide.worker_protocol import bundle_fingerprint_for_request

        request = ConversionRequest.from_source(SOURCE)
        supervisor = ProcessConversionSupervisor(
            worker_target=generation_one_hangs_then_convert
        )
        future = supervisor.submit(
            generation=1,
            bundle_fingerprint=bundle_fingerprint_for_request(request),
            request=request,
        )
        self.assertTrue(
            wait_until(lambda: supervisor.snapshot.active_generation == 1)
        )
        started = time.monotonic()
        supervisor.close(wait=False)
        self.assertLess(time.monotonic() - started, 0.250)
        with self.assertRaises(ConversionCancelled):
            future.result(timeout=2)
        supervisor.close(wait=True, timeout=2)
        self.assertIsNone(supervisor.snapshot.active_pid)


if __name__ == "__main__":
    unittest.main()
