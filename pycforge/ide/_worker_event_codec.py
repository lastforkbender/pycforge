"""Progress, terminal-result, and worker-failure event codec."""

from __future__ import annotations

from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.result import ConversionResult

from ._worker_protocol_json import (
    _contains_surrogate,
    _decode_bounded,
    _encode_bounded,
    _exact_fields,
    _generation,
    _object,
    _receive_frame,
    _send_frame,
    _sha256,
)
from ._worker_protocol_types import (
    FAILURE_CLASSIFICATIONS,
    MAX_EVENT_BYTES,
    MAX_FAILURE_MESSAGE_CHARS,
    PROTOCOL_SCHEMA,
    ByteConnection,
    WorkerEvent,
    WorkerProtocolError,
    WorkerRequest,
)
from ._worker_request_codec import _validate_worker_request
from ._worker_result_data import (
    _mappings_from_data,
    _progress_from_data,
    _result_from_data,
    _result_to_data,
    _validate_result_mappings,
)


_ENVELOPE_FIELDS = frozenset(
    {
        "schema",
        "kind",
        "generation",
        "bundle_fingerprint",
        "transport_fingerprint",
        "progress",
        "result",
        "mappings",
        "failure_classification",
        "message",
    }
)


def encode_progress(request: WorkerRequest, progress: ConversionProgress) -> bytes:
    _validate_worker_request(request)
    if not isinstance(progress, ConversionProgress):
        raise WorkerProtocolError("progress event must be ConversionProgress")
    return _encode_event(
        request,
        "progress",
        progress={
            "state": progress.state,
            "stage_id": progress.stage_id,
            "completed_stages": progress.completed_stages,
            "total_stages": progress.total_stages,
        },
    )


def encode_terminal(request: WorkerRequest, result: ConversionResult) -> bytes:
    _validate_worker_request(request)
    if not isinstance(result, ConversionResult):
        raise WorkerProtocolError("terminal event must contain ConversionResult")
    artifact = result.stage_artifact
    mappings: list[object] = []
    if artifact is not None:
        raw_mappings = artifact.payload.get("source_output_mappings", ())
        if not isinstance(raw_mappings, (tuple, list)):
            raise WorkerProtocolError("terminal source/output mappings are malformed")
        mappings = list(raw_mappings)
    return _encode_event(
        request,
        "terminal",
        result=_result_to_data(result),
        mappings=mappings,
    )


def encode_failure(
    request: WorkerRequest | None,
    failure_classification: str,
    message: str,
) -> bytes:
    if failure_classification not in FAILURE_CLASSIFICATIONS:
        raise WorkerProtocolError("unknown worker failure classification")
    if (
        not isinstance(message, str)
        or not message
        or len(message) > MAX_FAILURE_MESSAGE_CHARS
        or _contains_surrogate(message)
    ):
        raise WorkerProtocolError("worker failure message is malformed")
    return _encode_event(
        request,
        "failure",
        failure_classification=failure_classification,
        message=message,
    )


def decode_event(
    frame: bytes,
    *,
    expected: WorkerRequest | None = None,
    expected_generation: int | None = None,
    expected_bundle_fingerprint: str | None = None,
    expected_transport_fingerprint: str | None = None,
) -> WorkerEvent:
    value = _decode_bounded(frame, MAX_EVENT_BYTES, "event")
    data = _object(value, "event envelope")
    _exact_fields(data, _ENVELOPE_FIELDS, "event envelope")
    if data["schema"] != PROTOCOL_SCHEMA:
        raise WorkerProtocolError("incompatible worker event schema")
    kind = data["kind"]
    if kind not in {"progress", "terminal", "failure"}:
        raise WorkerProtocolError("unknown worker event kind")

    identities = (
        data["generation"],
        data["bundle_fingerprint"],
        data["transport_fingerprint"],
    )
    if all(item is None for item in identities):
        if kind != "failure":
            raise WorkerProtocolError("non-failure event lacks request identity")
        generation = None
        bundle_fingerprint = None
        transport_fingerprint = None
    elif any(item is None for item in identities):
        raise WorkerProtocolError("worker event has partial request identity")
    else:
        generation = _generation(data["generation"])
        bundle_fingerprint = _sha256(
            data["bundle_fingerprint"], "bundle fingerprint"
        )
        transport_fingerprint = _sha256(
            data["transport_fingerprint"], "transport fingerprint"
        )

    if expected is not None:
        _validate_worker_request(expected)
        expected_generation = expected.generation
        expected_bundle_fingerprint = expected.bundle_fingerprint
        expected_transport_fingerprint = expected.transport_fingerprint
    if generation is not None:
        if (
            expected_generation is not None
            and generation != _generation(expected_generation)
        ):
            raise WorkerProtocolError("worker event generation mismatch")
        if (
            expected_bundle_fingerprint is not None
            and bundle_fingerprint
            != _sha256(expected_bundle_fingerprint, "expected bundle fingerprint")
        ):
            raise WorkerProtocolError("worker event bundle fingerprint mismatch")
        if (
            expected_transport_fingerprint is not None
            and transport_fingerprint
            != _sha256(
                expected_transport_fingerprint,
                "expected transport fingerprint",
            )
        ):
            raise WorkerProtocolError("worker event transport fingerprint mismatch")

    progress: ConversionProgress | None = None
    result: ConversionResult | None = None
    mappings: tuple[dict[str, object], ...] = ()
    failure_classification: str | None = None
    message: str | None = None

    if kind == "progress":
        if any(
            data[key] is not None
            for key in ("result", "failure_classification", "message")
        ) or data["mappings"] != []:
            raise WorkerProtocolError("progress event contains terminal fields")
        progress = _progress_from_data(data["progress"])
    elif kind == "terminal":
        if (
            data["progress"] is not None
            or data["failure_classification"] is not None
            or data["message"] is not None
        ):
            raise WorkerProtocolError("terminal event contains non-terminal fields")
        result = _result_from_data(data["result"])
        mappings = _mappings_from_data(data["mappings"])
        _validate_result_mappings(result, mappings)
    else:
        if (
            data["progress"] is not None
            or data["result"] is not None
            or data["mappings"] != []
        ):
            raise WorkerProtocolError("failure event contains conversion fields")
        failure_classification = data["failure_classification"]
        message = data["message"]
        if failure_classification not in FAILURE_CLASSIFICATIONS:
            raise WorkerProtocolError("unknown worker failure classification")
        if (
            not isinstance(message, str)
            or not message
            or len(message) > MAX_FAILURE_MESSAGE_CHARS
            or _contains_surrogate(message)
        ):
            raise WorkerProtocolError("worker failure message is malformed")

    return WorkerEvent(
        kind,
        generation,
        bundle_fingerprint,
        transport_fingerprint,
        progress,
        result,
        mappings,
        failure_classification,
        message,
    )


def send_event(connection: ByteConnection, frame: bytes) -> None:
    _send_frame(connection, frame, MAX_EVENT_BYTES, "event")


def receive_event(
    connection: ByteConnection,
    *,
    expected: WorkerRequest | None = None,
) -> WorkerEvent:
    return decode_event(
        _receive_frame(connection, MAX_EVENT_BYTES, "event"),
        expected=expected,
    )


def _encode_event(
    request: WorkerRequest | None,
    kind: str,
    *,
    progress: object = None,
    result: object = None,
    mappings: list[object] | None = None,
    failure_classification: str | None = None,
    message: str | None = None,
) -> bytes:
    if request is not None:
        _validate_worker_request(request)
    data = {
        "schema": PROTOCOL_SCHEMA,
        "kind": kind,
        "generation": None if request is None else request.generation,
        "bundle_fingerprint": (
            None if request is None else request.bundle_fingerprint
        ),
        "transport_fingerprint": (
            None if request is None else request.transport_fingerprint
        ),
        "progress": progress,
        "result": result,
        "mappings": [] if mappings is None else mappings,
        "failure_classification": failure_classification,
        "message": message,
    }
    return _encode_bounded(data, MAX_EVENT_BYTES, "event")
