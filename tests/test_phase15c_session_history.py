from __future__ import annotations

from concurrent.futures import Future
from dataclasses import FrozenInstanceError, fields, replace
import time
import unittest

from pycforge.converter.core.enums import ResultStatus
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.facade import PythonToCConverter
from pycforge.ide import WorkspaceController
from pycforge.ide.session_history import (
    MAX_CONVERSION_HISTORY_ENTRIES,
    ConversionHistoryEntry,
    append_conversion_history,
)
from pycforge.ide.supervisor import (
    ConversionCancelled,
    ConversionSuperseded,
    WorkerFailure,
)


SOURCE_A = "def value() -> int:\n    return 1\n"
SOURCE_B = "def value() -> int:\n    return 2\n"


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def terminal_result(request, status: ResultStatus | None = None):
    converted = PythonToCConverter().convert(request)
    if status is None:
        return converted
    return replace(
        converted,
        status=status,
        generated_c=None,
        diagnostics=(),
        output_fingerprint=None,
        last_completed_stage="parse",
        stage_order=("parse",),
        decision_trace=None,
        telemetry=None,
        stage_artifact=None,
        conversion_summary=None,
    )


class ImmediateSupervisor:
    def __init__(self, outcome) -> None:
        self._outcome = outcome

    def submit(self, **submission):
        future = Future()
        try:
            outcome = self._outcome(submission)
        except BaseException as exc:
            future.set_exception(exc)
        else:
            if isinstance(outcome, BaseException):
                future.set_exception(outcome)
            else:
                future.set_result(outcome)
        return future

    def cancel(self, generation=None) -> None:
        return None


class StartupFailureSupervisor:
    def submit(self, **submission):
        raise RuntimeError("injected startup failure")

    def cancel(self, generation=None) -> None:
        return None


class QueueSupervisor:
    def __init__(self, *, complete_on_cancel: bool = False) -> None:
        self.submissions: list[tuple[Future, dict[str, object]]] = []
        self.complete_on_cancel = complete_on_cancel

    def submit(self, **submission):
        future = Future()
        self.submissions.append((future, submission))
        return future

    def cancel(self, generation=None) -> None:
        if not self.complete_on_cancel:
            return
        for future, submission in self.submissions:
            if (
                not future.done()
                and (
                    generation is None
                    or submission["generation"] == generation
                )
            ):
                future.set_exception(
                    ConversionCancelled("request canceled")
                )

    def complete_result(self, index: int) -> None:
        future, submission = self.submissions[index]
        future.set_result(terminal_result(submission["request"]))


def history_entry(sequence: int) -> ConversionHistoryEntry:
    return ConversionHistoryEntry(
        request_sequence=sequence,
        revision_generation=sequence - 1,
        bundle_fingerprint=f"{sequence:064x}",
        request_fingerprint=f"{sequence + 1:064x}",
        output_fingerprint=None,
        status="Converted",
        diagnostic_count=0,
        completed_stage_count=1,
        total_stage_count=1,
        stage="render",
        published=True,
        reason=None,
    )


class Phase15CSessionHistoryTests(unittest.TestCase):
    def controller_with(self, supervisor) -> WorkspaceController:
        controller = WorkspaceController(supervisor=supervisor)
        self.addCleanup(controller.close)
        controller.set_source(SOURCE_A)
        self.assertTrue(
            wait_until(lambda: controller.snapshot.revision_authenticated),
            "workspace revision authentication timed out",
        )
        return controller

    def test_entry_is_immutable_payload_free_and_helper_caps_at_64(self):
        allowed_fields = {
            "request_sequence",
            "revision_generation",
            "bundle_fingerprint",
            "request_fingerprint",
            "output_fingerprint",
            "status",
            "diagnostic_count",
            "completed_stage_count",
            "total_stage_count",
            "stage",
            "published",
            "reason",
        }
        self.assertEqual(
            {field.name for field in fields(ConversionHistoryEntry)},
            allowed_fields,
        )
        self.assertEqual(MAX_CONVERSION_HISTORY_ENTRIES, 64)

        history: tuple[ConversionHistoryEntry, ...] = ()
        for sequence in range(1, 71):
            history = append_conversion_history(
                history,
                history_entry(sequence),
            )
        self.assertEqual(len(history), 64)
        self.assertEqual(history[0].request_sequence, 7)
        self.assertEqual(history[-1].request_sequence, 70)
        self.assertIs(
            append_conversion_history(history, history[-1]),
            history,
        )
        with self.assertRaises(FrozenInstanceError):
            history[-1].status = "Rejected"
        for excluded in (
            "source_text",
            "generated_c",
            "diagnostics",
            "artifact",
            "timestamp",
        ):
            self.assertNotIn(excluded, allowed_fields)

    def test_accepted_converter_terminals_append_exactly_once(self):
        cases = (
            (None, "Converted", True, None),
            (
                ResultStatus.REJECTED,
                "Rejected",
                False,
                "converter-rejected",
            ),
            (
                ResultStatus.INTERNAL_FAILURE,
                "InternalFailure",
                False,
                "converter-internal-failure",
            ),
        )
        for result_status, status, published, reason in cases:
            with self.subTest(status=status):
                supervisor = ImmediateSupervisor(
                    lambda submission, value=result_status: terminal_result(
                        submission["request"],
                        value,
                    )
                )
                controller = self.controller_with(supervisor)
                result = controller.convert()
                history = controller.snapshot.conversion_history

                self.assertEqual(len(history), 1)
                entry = history[0]
                self.assertEqual(entry.request_sequence, 1)
                self.assertEqual(
                    entry.revision_generation,
                    controller.snapshot.revision_generation,
                )
                self.assertEqual(
                    entry.bundle_fingerprint,
                    controller.snapshot.bundle_fingerprint,
                )
                self.assertEqual(
                    entry.request_fingerprint,
                    result.request_fingerprint.value,
                )
                self.assertEqual(
                    entry.output_fingerprint,
                    (
                        result.output_fingerprint.value
                        if result.output_fingerprint
                        else None
                    ),
                )
                self.assertEqual(entry.status, status)
                self.assertIs(entry.published, published)
                self.assertEqual(entry.reason, reason)
                self.assertEqual(
                    entry.diagnostic_count,
                    len(result.diagnostics),
                )
                self.assertEqual(
                    entry.completed_stage_count,
                    len(result.stage_order),
                )

    def test_startup_worker_and_fingerprint_failures_are_classified(self):
        def worker_failure(_submission):
            return WorkerFailure("malformed-worker-envelope")

        def fingerprint_failure(submission):
            result = terminal_result(submission["request"])
            return replace(
                result,
                request_fingerprint=fingerprint(
                    "mismatched-request",
                    "different",
                ),
            )

        cases = (
            (
                StartupFailureSupervisor(),
                RuntimeError,
                "worker-startup-failure",
            ),
            (
                ImmediateSupervisor(worker_failure),
                WorkerFailure,
                "malformed-worker-envelope",
            ),
            (
                ImmediateSupervisor(fingerprint_failure),
                WorkerFailure,
                "request-fingerprint-mismatch",
            ),
        )
        for supervisor, exception, reason in cases:
            with self.subTest(reason=reason):
                controller = self.controller_with(supervisor)
                with self.assertRaises(exception):
                    controller.convert()
                history = controller.snapshot.conversion_history
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0].status, "WorkerFailure")
                self.assertEqual(history[0].reason, reason)
                self.assertFalse(history[0].published)
                self.assertIsNone(history[0].output_fingerprint)

    def test_current_request_cancellation_is_recorded(self):
        supervisor = QueueSupervisor(complete_on_cancel=True)
        controller = self.controller_with(supervisor)

        conversion = controller.convert_async()
        controller.cancel()
        with self.assertRaises(ConversionCancelled):
            conversion.result(timeout=1)

        self.assertEqual(len(controller.snapshot.conversion_history), 1)
        entry = controller.snapshot.conversion_history[0]
        self.assertEqual(entry.status, "Canceled")
        self.assertEqual(entry.reason, "conversion-canceled")
        self.assertFalse(entry.published)

    def test_stale_and_superseded_requests_never_append(self):
        stale_supervisor = QueueSupervisor()
        stale_controller = self.controller_with(stale_supervisor)
        stale = stale_controller.convert_async()
        stale_controller.set_source(SOURCE_B)
        self.assertTrue(
            wait_until(
                lambda: stale_controller.snapshot.revision_authenticated
            )
        )
        stale_supervisor.complete_result(0)
        stale.result(timeout=1)
        self.assertEqual(stale_controller.snapshot.conversion_history, ())

        superseded_supervisor = QueueSupervisor()
        current_controller = self.controller_with(superseded_supervisor)
        superseded = current_controller.convert_async()
        current = current_controller.convert_async()
        first_future, _submission = superseded_supervisor.submissions[0]
        first_future.set_exception(
            ConversionSuperseded("request superseded")
        )
        with self.assertRaises(ConversionSuperseded):
            superseded.result(timeout=1)
        self.assertEqual(current_controller.snapshot.conversion_history, ())

        superseded_supervisor.complete_result(1)
        current.result(timeout=1)
        self.assertEqual(
            tuple(
                entry.request_sequence
                for entry in current_controller.snapshot.conversion_history
            ),
            (2,),
        )


if __name__ == "__main__":
    unittest.main()
