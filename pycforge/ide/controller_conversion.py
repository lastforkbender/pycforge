from __future__ import annotations

from concurrent.futures import CancelledError, Future
from dataclasses import replace

from pycforge.converter.core.enums import ResultStatus, Severity
from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.request import SourceBundle
from pycforge.converter.core.stage_artifact import freeze_value

from .model import WorkspaceState
from .revisions import WorkspaceRevision
from .session_history import (
    ConversionHistoryEntry,
    append_conversion_history,
)
from .supervisor import (
    ConversionCancelled,
    ConversionSuperseded,
    WorkerFailure,
)


class ConversionControllerMixin:
    """Isolated-conversion lifecycle mixed into the workspace controller."""

    def convert_async(self) -> Future:
        with self._lock:
            if self._closed:
                raise RuntimeError("workspace controller is closed")
            if not self.snapshot.revision_authenticated:
                revision_future = self._revision_future
                if revision_future is None:
                    raise RuntimeError(
                        "workspace revision is not authenticated"
                    )
                deferred: Future = Future()
                revision_future.add_done_callback(
                    lambda completed: self._submit_after_revision(
                        completed,
                        deferred,
                    )
                )
                return deferred
            return self._submit_authenticated_revision()

    def convert(self):
        return self.convert_async().result()

    def cancel(self) -> None:
        with self._lock:
            current = self.snapshot
            if current.state is not WorkspaceState.CONVERTING:
                return
            self._publish(
                replace(
                    current,
                    state=WorkspaceState.CANCEL_REQUESTED,
                    stale_reason=(
                        "cancel-requested"
                        if current.generated_c is not None
                        else None
                    ),
                    worker_failure_reason=None,
                )
            )
            self._supervisor.cancel(current.request_sequence)

    def _submit_after_revision(
        self,
        revision_future: Future[WorkspaceRevision],
        deferred: Future,
    ) -> None:
        if deferred.done():
            return
        try:
            revision_future.result()
            submitted = self.convert_async()
        except CancelledError:
            deferred.set_exception(
                ConversionSuperseded(
                    "workspace revision was superseded before conversion"
                )
            )
            return
        except BaseException as exc:
            deferred.set_exception(exc)
            return

        def bridge(completed: Future) -> None:
            if deferred.done():
                return
            try:
                deferred.set_result(completed.result())
            except BaseException as exc:
                deferred.set_exception(exc)

        submitted.add_done_callback(bridge)

    def _submit_authenticated_revision(self) -> Future:
        current = self.snapshot
        revision = self._current_revision
        if (
            revision.generation != current.revision_generation
            or revision.bundle_fingerprint != current.bundle_fingerprint
        ):
            raise RuntimeError("workspace revision identity is unsettled")
        self._request_sequence += 1
        sequence = self._request_sequence
        revision_generation = revision.generation
        bundle_fingerprint = revision.bundle_fingerprint
        self._publish(
            replace(
                current,
                state=WorkspaceState.CONVERTING,
                request_sequence=sequence,
                stale_reason=None,
                worker_failure_reason=None,
                active_stage=None,
                completed_stages=0,
                total_stages=0,
            )
        )
        public: Future = Future()
        try:
            isolated = self._supervisor.submit(
                generation=sequence,
                bundle_fingerprint=bundle_fingerprint,
                request=revision.request,
                progress=self._report_progress,
            )
        except BaseException as exc:
            self._fail_conversion(
                sequence,
                revision_generation,
                bundle_fingerprint,
                revision.request_fingerprint.value,
                "worker-startup-failure",
            )
            public.set_exception(exc)
            return public
        isolated.add_done_callback(
            lambda completed: self._conversion_finished(
                completed,
                public,
                sequence,
                revision_generation,
                bundle_fingerprint,
                revision,
            )
        )
        return public

    def _conversion_finished(
        self,
        isolated: Future,
        public: Future,
        sequence: int,
        revision_generation: int,
        bundle_fingerprint: str,
        revision: WorkspaceRevision,
    ) -> None:
        try:
            result = isolated.result()
        except (ConversionCancelled, ConversionSuperseded, CancelledError) as exc:
            self._finish_cancellation(
                sequence,
                revision_generation,
                bundle_fingerprint,
                revision.request_fingerprint.value,
            )
            if not public.done():
                public.set_exception(exc)
            return
        except BaseException as exc:
            reason = (
                exc.classification
                if isinstance(exc, WorkerFailure)
                else "worker-failure"
            )
            self._fail_conversion(
                sequence,
                revision_generation,
                bundle_fingerprint,
                revision.request_fingerprint.value,
                reason,
            )
            if not public.done():
                public.set_exception(exc)
            return
        if result.request_fingerprint != revision.request_fingerprint:
            failure = WorkerFailure("request-fingerprint-mismatch")
            self._fail_conversion(
                sequence,
                revision_generation,
                bundle_fingerprint,
                revision.request_fingerprint.value,
                failure.classification,
            )
            if not public.done():
                public.set_exception(failure)
            return
        self._publish_result(
            sequence,
            revision_generation,
            bundle_fingerprint,
            revision.source_bundle,
            result,
        )
        if not public.done():
            public.set_result(result)

    def _publish_result(
        self,
        sequence: int,
        revision_generation: int,
        bundle_fingerprint: str,
        source_bundle: SourceBundle,
        result,
    ) -> None:
        generated_c = result.generated_c
        index_job: tuple[int, str] | None = None
        with self._lock:
            current = self.snapshot
            if (
                sequence != self._request_sequence
                or sequence != current.request_sequence
                or revision_generation != current.revision_generation
                or current.bundle_fingerprint != bundle_fingerprint
            ):
                return
            state = self._state_for(result)
            payload = (
                result.stage_artifact.payload
                if result.stage_artifact
                else {}
            )
            conversion_summary = result.conversion_summary or {}
            summary = (
                ("status", result.status.value),
                ("last_completed_stage", result.last_completed_stage or ""),
                (
                    "request_fingerprint",
                    result.request_fingerprint.value
                    if result.request_fingerprint
                    else "",
                ),
                (
                    "output_fingerprint",
                    result.output_fingerprint.value
                    if result.output_fingerprint
                    else "",
                ),
                ("modules", str(len(source_bundle.companions) + 1)),
                ("functions", str(len(conversion_summary.get("functions", ())))),
                ("calls", str(len(conversion_summary.get("calls", ())))),
                ("helpers", str(len(conversion_summary.get("helpers", ())))),
            )
            published = result.generated_c is not None
            completed_stage_count = len(result.stage_order)
            total_stage_count = max(
                current.total_stages,
                completed_stage_count,
            )
            history = append_conversion_history(
                current.conversion_history,
                ConversionHistoryEntry(
                    request_sequence=sequence,
                    revision_generation=revision_generation,
                    bundle_fingerprint=bundle_fingerprint,
                    request_fingerprint=(
                        result.request_fingerprint.value
                        if result.request_fingerprint
                        else None
                    ),
                    output_fingerprint=(
                        result.output_fingerprint.value
                        if result.output_fingerprint
                        else None
                    ),
                    status=result.status.value,
                    diagnostic_count=len(result.diagnostics),
                    completed_stage_count=completed_stage_count,
                    total_stage_count=total_stage_count,
                    stage=result.last_completed_stage,
                    published=published,
                    reason=self._result_history_reason(state, published),
                ),
            )
            if published:
                assert generated_c is not None
                self._result_output_index = None
                self._output_index_generation += 1
                index_job = (
                    self._output_index_generation,
                    generated_c,
                )
            snapshot = replace(
                current,
                generated_c=(
                    result.generated_c if published else current.generated_c
                ),
                state=state,
                diagnostics=tuple(
                    freeze_value(diagnostic.to_dict())
                    for diagnostic in result.diagnostics
                ),
                summary=summary,
                decision_trace=result.decision_trace,
                telemetry=result.telemetry,
                conversion_summary=result.conversion_summary,
                mappings=(
                    tuple(payload.get("source_output_mappings", ()))
                    if published
                    else current.mappings
                ),
                conversion_history=history,
                result_source_fingerprint=(
                    bundle_fingerprint
                    if published
                    else current.result_source_fingerprint
                ),
                result_bundle_fingerprint=(
                    bundle_fingerprint
                    if published
                    else current.result_bundle_fingerprint
                ),
                result_revision_generation=(
                    revision_generation
                    if published
                    else current.result_revision_generation
                ),
                result_state=state if published else current.result_state,
                stale_reason=(
                    None
                    if published
                    else (
                        "conversion-not-published"
                        if current.generated_c is not None
                        else None
                    )
                ),
                active_stage=None,
                completed_stages=completed_stage_count,
                total_stages=total_stage_count,
                worker_failure_reason=(
                    "converter-internal-failure"
                    if state is WorkspaceState.FAILED
                    else None
                ),
            )
            self._publish(snapshot)
        if index_job is not None:
            try:
                self._output_index_service.submit(*index_job)
            except RuntimeError:
                # Close may retire deferred presentation work immediately
                # after the terminal result is safely published.
                pass

    def _fail_conversion(
        self,
        sequence: int,
        revision_generation: int,
        bundle_fingerprint: str,
        request_fingerprint: str,
        reason: str,
    ) -> None:
        with self._lock:
            current = self.snapshot
            if (
                sequence != self._request_sequence
                or current.request_sequence != sequence
                or current.revision_generation != revision_generation
                or current.bundle_fingerprint != bundle_fingerprint
                or current.state
                not in {
                    WorkspaceState.CONVERTING,
                    WorkspaceState.CANCEL_REQUESTED,
                }
            ):
                return
            history = append_conversion_history(
                current.conversion_history,
                ConversionHistoryEntry(
                    request_sequence=sequence,
                    revision_generation=revision_generation,
                    bundle_fingerprint=bundle_fingerprint,
                    request_fingerprint=request_fingerprint,
                    output_fingerprint=None,
                    status="WorkerFailure",
                    diagnostic_count=0,
                    completed_stage_count=current.completed_stages,
                    total_stage_count=current.total_stages,
                    stage=current.active_stage,
                    published=False,
                    reason=reason,
                ),
            )
            self._publish(
                replace(
                    current,
                    state=WorkspaceState.FAILED,
                    diagnostics=(),
                    summary=(),
                    decision_trace=None,
                    telemetry=None,
                    conversion_summary=None,
                    stale_reason=(
                        "conversion-failed"
                        if current.generated_c is not None
                        else None
                    ),
                    active_stage=None,
                    completed_stages=0,
                    total_stages=0,
                    worker_failure_reason=reason,
                    conversion_history=history,
                )
            )

    def _finish_cancellation(
        self,
        sequence: int,
        revision_generation: int,
        bundle_fingerprint: str,
        request_fingerprint: str,
    ) -> None:
        with self._lock:
            current = self.snapshot
            if (
                sequence != self._request_sequence
                or current.request_sequence != sequence
                or current.revision_generation != revision_generation
                or current.bundle_fingerprint != bundle_fingerprint
                or current.state
                not in {
                    WorkspaceState.CONVERTING,
                    WorkspaceState.CANCEL_REQUESTED,
                }
            ):
                return
            history = append_conversion_history(
                current.conversion_history,
                ConversionHistoryEntry(
                    request_sequence=sequence,
                    revision_generation=revision_generation,
                    bundle_fingerprint=bundle_fingerprint,
                    request_fingerprint=request_fingerprint,
                    output_fingerprint=None,
                    status=ResultStatus.CANCELED.value,
                    diagnostic_count=0,
                    completed_stage_count=current.completed_stages,
                    total_stage_count=current.total_stages,
                    stage=current.active_stage,
                    published=False,
                    reason="conversion-canceled",
                ),
            )
            self._publish(
                replace(
                    current,
                    state=WorkspaceState.CANCELED,
                    diagnostics=(),
                    summary=(),
                    decision_trace=None,
                    telemetry=None,
                    conversion_summary=None,
                    stale_reason=(
                        "conversion-canceled"
                        if current.generated_c is not None
                        else None
                    ),
                    active_stage=None,
                    completed_stages=0,
                    total_stages=0,
                    worker_failure_reason=None,
                    conversion_history=history,
                )
            )

    def _report_progress(
        self,
        sequence: int,
        bundle_fingerprint: str,
        event: ConversionProgress,
    ) -> None:
        with self._lock:
            current = self.snapshot
            if (
                sequence != self._request_sequence
                or current.request_sequence != sequence
                or current.bundle_fingerprint != bundle_fingerprint
                or current.state is not WorkspaceState.CONVERTING
            ):
                return
            self._publish(
                replace(
                    current,
                    active_stage=event.stage_id,
                    completed_stages=event.completed_stages,
                    total_stages=event.total_stages,
                )
            )

    @staticmethod
    def _state_for(result) -> WorkspaceState:
        if result.status is ResultStatus.CANCELED:
            return WorkspaceState.CANCELED
        if result.status is ResultStatus.REJECTED:
            return WorkspaceState.REJECTED
        if result.status is ResultStatus.INTERNAL_FAILURE:
            return WorkspaceState.FAILED
        severities = {diagnostic.severity for diagnostic in result.diagnostics}
        if Severity.APPROXIMATION in severities:
            return WorkspaceState.APPROXIMATION
        trace = result.decision_trace or {}
        telemetry = result.telemetry or {}
        if (
            trace.get("truncated")
            or trace.get("observer_failed")
            or telemetry.get("dropped")
            or telemetry.get("observer_failed")
        ):
            return WorkspaceState.OBSERVER_INCOMPLETE
        if Severity.WARNING in severities:
            return WorkspaceState.WARNING
        return WorkspaceState.CONVERTED

    @staticmethod
    def _result_history_reason(
        state: WorkspaceState,
        published: bool,
    ) -> str | None:
        if published:
            return None
        if state is WorkspaceState.REJECTED:
            return "converter-rejected"
        if state is WorkspaceState.FAILED:
            return "converter-internal-failure"
        if state is WorkspaceState.CANCELED:
            return "converter-canceled"
        return "conversion-not-published"


__all__ = ["ConversionControllerMixin"]
