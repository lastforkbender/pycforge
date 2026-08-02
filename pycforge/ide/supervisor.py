from __future__ import annotations

from concurrent.futures import CancelledError, Future
from dataclasses import dataclass
from multiprocessing import get_context
from multiprocessing.connection import Connection
from threading import Condition, RLock, Thread, current_thread
from time import monotonic
from typing import Callable

from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.request import ConversionRequest, ObservationOptions
from pycforge.converter.core.result import ConversionResult

from .process_worker import worker_main
from .worker_protocol import (
    WorkerEvent,
    WorkerRequest,
    encode_request,
    receive_event,
    send_cancel,
)


COOPERATIVE_CANCEL_GRACE_SECONDS = 0.750
FORCED_RECLAMATION_SECONDS = 2.000
KILL_ESCALATION_SECONDS = 1.750
POLL_SECONDS = 0.010


class ConversionSupervisorError(RuntimeError):
    """Base class for recoverable isolated-worker failures."""


class ConversionCancelled(CancelledError):
    """The request was retired before a complete result could publish."""


class ConversionSuperseded(ConversionCancelled):
    """A newer latest request replaced this request."""


class WorkerFailure(ConversionSupervisorError):
    """The isolated process failed without publishing a valid result."""

    def __init__(self, classification: str) -> None:
        self.classification = classification
        super().__init__(f"isolated conversion worker failed: {classification}")


ProgressListener = Callable[[int, str, ConversionProgress], None]
WorkerTarget = Callable[[Connection, Connection, Connection], None]


@dataclass(frozen=True, slots=True)
class SupervisorSnapshot:
    active_generation: int | None
    pending_generation: int | None
    active_pid: int | None
    started_workers: int
    reaped_workers: int
    forced_terminations: int
    maximum_simultaneous_workers: int
    latest_pending_start_delay_seconds: float | None
    closed: bool


@dataclass(slots=True)
class _Slot:
    generation: int
    bundle_fingerprint: str
    request: ConversionRequest
    observation: ObservationOptions
    progress: ProgressListener | None
    future: Future[ConversionResult]
    submitted_at: float


@dataclass(slots=True)
class _Active:
    slot: _Slot
    worker_request: WorkerRequest
    process: object
    event_connection: Connection
    control_connection: Connection
    cancel_requested_at: float | None = None
    cancel_reason: str | None = None
    cancel_frame_sent: bool = False
    terminate_sent: bool = False
    kill_sent: bool = False
    terminal_event: WorkerEvent | None = None
    protocol_failure: str | None = None


class ProcessConversionSupervisor:
    """One-process/one-latest-pending supervisor for conversion requests.

    The calling thread only mutates bounded scheduler state. Process creation,
    JSON encoding, pipe traffic, validation, escalation, joining, and Future
    completion all belong to the coordinator thread.
    """

    def __init__(
        self,
        *,
        context_name: str = "spawn",
        worker_target: WorkerTarget = worker_main,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if context_name != "spawn":
            raise ValueError("PyCForge conversion workers require spawn isolation")
        self._context = get_context(context_name)
        self._worker_target = worker_target
        self._clock = clock
        self._condition = Condition(RLock())
        self._active: _Active | None = None
        self._pending: _Slot | None = None
        self._retired: list[tuple[_Slot, BaseException]] = []
        self._closed = False
        self._started_workers = 0
        self._reaped_workers = 0
        self._forced_terminations = 0
        self._maximum_simultaneous_workers = 0
        self._last_reaped_at: float | None = None
        self._latest_pending_start_delay: float | None = None
        self._thread = Thread(
            target=self._coordinate,
            name="pycforge-process-supervisor",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        *,
        generation: int,
        bundle_fingerprint: str,
        request: ConversionRequest,
        progress: ProgressListener | None = None,
        observation: ObservationOptions | None = None,
    ) -> Future[ConversionResult]:
        if not isinstance(generation, int) or isinstance(generation, bool):
            raise TypeError("request generation must be an integer")
        if generation < 1:
            raise ValueError("request generation must be positive")
        if not isinstance(bundle_fingerprint, str) or not bundle_fingerprint:
            raise ValueError("bundle fingerprint must be non-empty")
        if not isinstance(request, ConversionRequest):
            raise TypeError("isolated conversion requires ConversionRequest")
        future: Future[ConversionResult] = Future()
        slot = _Slot(
            generation,
            bundle_fingerprint,
            request,
            observation or ObservationOptions("Full", True),
            progress,
            future,
            self._clock(),
        )
        with self._condition:
            if self._closed:
                raise RuntimeError("conversion supervisor is closed")
            replaced = self._pending
            self._pending = slot
            if replaced is not None:
                self._retired.append(
                    (replaced, ConversionSuperseded("request superseded"))
                )
            if self._active is not None:
                self._request_cancel_locked(self._active, "superseded")
            self._condition.notify_all()
        return future

    def cancel(self, generation: int | None = None) -> None:
        """Request cancellation without waiting for pipe or process work."""

        with self._condition:
            if self._pending is not None and (
                generation is None or self._pending.generation == generation
            ):
                pending = self._pending
                self._pending = None
                self._retired.append(
                    (pending, ConversionCancelled("request canceled"))
                )
            if self._active is not None and (
                generation is None or self._active.slot.generation == generation
            ):
                self._request_cancel_locked(self._active, "canceled")
            self._condition.notify_all()

    def close(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Accept shutdown immediately; reap the worker on the coordinator."""

        with self._condition:
            if not self._closed:
                self._closed = True
                if self._pending is not None:
                    self._retired.append(
                        (
                            self._pending,
                            ConversionCancelled("supervisor closed"),
                        )
                    )
                    self._pending = None
                if self._active is not None:
                    self._request_cancel_locked(self._active, "closed")
                self._condition.notify_all()
        if wait and current_thread() is not self._thread:
            self._thread.join(timeout)

    def wait_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else self._clock() + timeout
        with self._condition:
            while self._active is not None or self._pending is not None:
                remaining = None if deadline is None else deadline - self._clock()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    @property
    def snapshot(self) -> SupervisorSnapshot:
        with self._condition:
            active = self._active
            return SupervisorSnapshot(
                active_generation=(
                    None if active is None else active.slot.generation
                ),
                pending_generation=(
                    None if self._pending is None else self._pending.generation
                ),
                active_pid=(
                    None
                    if active is None
                    else getattr(active.process, "pid", None)
                ),
                started_workers=self._started_workers,
                reaped_workers=self._reaped_workers,
                forced_terminations=self._forced_terminations,
                maximum_simultaneous_workers=self._maximum_simultaneous_workers,
                latest_pending_start_delay_seconds=self._latest_pending_start_delay,
                closed=self._closed,
            )

    def _request_cancel_locked(self, active: _Active, reason: str) -> None:
        if active.cancel_requested_at is None:
            active.cancel_requested_at = self._clock()
            active.cancel_reason = reason
        elif reason == "closed":
            active.cancel_reason = reason

    def _coordinate(self) -> None:
        while True:
            self._complete_retired()
            with self._condition:
                if self._active is None and self._pending is not None:
                    slot = self._pending
                    self._pending = None
                else:
                    slot = None
                should_exit = (
                    self._closed
                    and self._active is None
                    and self._pending is None
                    and not self._retired
                )
            if should_exit:
                return
            if slot is not None:
                self._start(slot)
                continue
            with self._condition:
                active = self._active
                if active is None:
                    self._condition.wait(POLL_SECONDS)
                    continue
            self._service(active)

    def _complete_retired(self) -> None:
        with self._condition:
            retired = tuple(self._retired)
            self._retired.clear()
        for slot, failure in retired:
            if not slot.future.done():
                slot.future.set_exception(failure)

    def _start(self, slot: _Slot) -> None:
        try:
            request = WorkerRequest.create(
                slot.generation,
                slot.bundle_fingerprint,
                slot.request,
                slot.observation,
            )
            payload = encode_request(request)
            request_receive, request_send = self._context.Pipe(duplex=False)
            event_receive, event_send = self._context.Pipe(duplex=False)
            control_receive, control_send = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=self._worker_target,
                args=(request_receive, event_send, control_receive),
                name=f"pycforge-conversion-{slot.generation}",
                daemon=True,
            )
            process.start()
            request_receive.close()
            event_send.close()
            control_receive.close()
            request_send.send_bytes(payload)
            request_send.close()
            active = _Active(
                slot,
                request,
                process,
                event_receive,
                control_send,
            )
        except Exception:
            for connection_name in (
                "request_receive",
                "request_send",
                "event_receive",
                "event_send",
                "control_receive",
                "control_send",
            ):
                connection = locals().get(connection_name)
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
            if "process" in locals() and process.is_alive():
                process.terminate()
                process.join(0.1)
            if not slot.future.done():
                slot.future.set_exception(WorkerFailure("startup-failure"))
            with self._condition:
                self._condition.notify_all()
            return

        with self._condition:
            self._active = active
            self._started_workers += 1
            self._maximum_simultaneous_workers = max(
                self._maximum_simultaneous_workers,
                1,
            )
            if self._last_reaped_at is not None:
                self._latest_pending_start_delay = max(
                    0.0,
                    self._clock() - self._last_reaped_at,
                )
            if self._closed:
                self._request_cancel_locked(active, "closed")
            elif self._pending is not None:
                self._request_cancel_locked(active, "superseded")
            self._condition.notify_all()

    def _service(self, active: _Active) -> None:
        if active is not self._active:
            return
        self._drain_events(active)
        now = self._clock()
        self._service_cancellation(active, now)
        process = active.process
        if not process.is_alive():
            try:
                process.join(0)
            except Exception:
                pass
            self._drain_events(active)
            self._finish_active(active)
            return
        with self._condition:
            self._condition.wait(POLL_SECONDS)

    def _drain_events(self, active: _Active) -> None:
        for _ in range(64):
            try:
                if not active.event_connection.poll(0):
                    return
                event = receive_event(
                    active.event_connection,
                    expected=active.worker_request,
                )
            except (EOFError, OSError, BrokenPipeError):
                return
            except Exception:
                active.protocol_failure = "malformed-worker-envelope"
                return
            if event.progress is not None:
                listener = active.slot.progress
                if listener is not None and active.cancel_requested_at is None:
                    try:
                        listener(
                            active.slot.generation,
                            active.slot.bundle_fingerprint,
                            event.progress,
                        )
                    except Exception:
                        pass
            elif event.result is not None or event.failure_classification is not None:
                if active.terminal_event is not None:
                    active.protocol_failure = "duplicate-terminal-envelope"
                else:
                    active.terminal_event = event

    def _service_cancellation(self, active: _Active, now: float) -> None:
        requested = active.cancel_requested_at
        if requested is None:
            return
        if not active.cancel_frame_sent:
            try:
                send_cancel(active.control_connection, active.worker_request)
            except (EOFError, OSError, BrokenPipeError):
                pass
            active.cancel_frame_sent = True
        elapsed = now - requested
        immediate = active.cancel_reason == "closed"
        if (
            not active.terminate_sent
            and (immediate or elapsed >= COOPERATIVE_CANCEL_GRACE_SECONDS)
            and active.process.is_alive()
        ):
            try:
                active.process.terminate()
            except Exception:
                pass
            active.terminate_sent = True
            self._forced_terminations += 1
        if (
            not active.kill_sent
            and elapsed >= KILL_ESCALATION_SECONDS
            and active.process.is_alive()
        ):
            try:
                active.process.kill()
            except Exception:
                pass
            active.kill_sent = True
        if elapsed >= FORCED_RECLAMATION_SECONDS and active.process.is_alive():
            try:
                active.process.kill()
            except Exception:
                pass

    def _finish_active(self, active: _Active) -> None:
        for connection in (active.event_connection, active.control_connection):
            try:
                connection.close()
            except Exception:
                pass
        failure: BaseException | None = None
        result: ConversionResult | None = None
        if active.cancel_requested_at is not None:
            failure_type = (
                ConversionSuperseded
                if active.cancel_reason == "superseded"
                else ConversionCancelled
            )
            failure = failure_type(
                f"request {active.cancel_reason or 'canceled'}"
            )
        elif active.protocol_failure is not None:
            failure = WorkerFailure(active.protocol_failure)
        elif active.terminal_event is None:
            failure = WorkerFailure("abrupt-worker-exit")
        elif active.terminal_event.failure_classification is not None:
            failure = WorkerFailure(
                active.terminal_event.failure_classification
            )
        elif active.terminal_event.result is None:
            failure = WorkerFailure("missing-terminal-result")
        else:
            result = active.terminal_event.result

        future = active.slot.future
        if not future.done():
            if failure is not None:
                future.set_exception(failure)
            else:
                assert result is not None
                future.set_result(result)
        with self._condition:
            if self._active is active:
                self._active = None
            self._reaped_workers += 1
            self._last_reaped_at = self._clock()
            self._condition.notify_all()


__all__ = [
    "COOPERATIVE_CANCEL_GRACE_SECONDS",
    "FORCED_RECLAMATION_SECONDS",
    "ConversionCancelled",
    "ConversionSuperseded",
    "ConversionSupervisorError",
    "ProcessConversionSupervisor",
    "SupervisorSnapshot",
    "WorkerFailure",
]
