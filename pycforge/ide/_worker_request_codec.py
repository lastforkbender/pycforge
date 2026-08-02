"""Request and cancellation envelope codec."""

from __future__ import annotations

from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.request import ConversionRequest, ObservationOptions

from ._worker_protocol_json import (
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
    MAX_CONTROL_BYTES,
    MAX_REQUEST_BYTES,
    PROTOCOL_SCHEMA,
    ByteConnection,
    WorkerControl,
    WorkerProtocolError,
    WorkerRequest,
)
from ._worker_request_data import (
    _observation_from_data,
    _observation_to_data,
    _request_from_data,
    _request_to_data,
    bundle_fingerprint_for_request,
)


def create_worker_request(
    generation: int,
    bundle_fingerprint: str,
    request: ConversionRequest,
    observation: ObservationOptions | None = None,
) -> WorkerRequest:
    observation = observation or ObservationOptions()
    core = _request_envelope_core(
        generation, bundle_fingerprint, request, observation
    )
    return WorkerRequest(
        generation,
        bundle_fingerprint,
        request,
        observation,
        _transport_fingerprint(core),
    )


def encode_request(request: WorkerRequest) -> bytes:
    _validate_worker_request(request)
    core = _request_envelope_core(
        request.generation,
        request.bundle_fingerprint,
        request.request,
        request.observation,
    )
    if request.transport_fingerprint != _transport_fingerprint(core):
        raise WorkerProtocolError("worker request transport fingerprint mismatch")
    return _encode_bounded(
        {**core, "transport_fingerprint": request.transport_fingerprint},
        MAX_REQUEST_BYTES,
        "request",
    )


def decode_request(frame: bytes) -> WorkerRequest:
    value = _decode_bounded(frame, MAX_REQUEST_BYTES, "request")
    data = _object(value, "request envelope")
    _exact_fields(
        data,
        {
            "schema",
            "kind",
            "generation",
            "bundle_fingerprint",
            "request",
            "observation",
            "transport_fingerprint",
        },
        "request envelope",
    )
    if data["schema"] != PROTOCOL_SCHEMA or data["kind"] != "request":
        raise WorkerProtocolError("incompatible worker request envelope")
    generation = _generation(data["generation"])
    bundle_fingerprint = _sha256(data["bundle_fingerprint"], "bundle fingerprint")
    conversion_request = _request_from_data(data["request"])
    observation = _observation_from_data(data["observation"])
    supplied = _sha256(data["transport_fingerprint"], "transport fingerprint")
    core = {
        "schema": PROTOCOL_SCHEMA,
        "kind": "request",
        "generation": generation,
        "bundle_fingerprint": bundle_fingerprint,
        "request": _request_to_data(conversion_request),
        "observation": _observation_to_data(observation),
    }
    expected = _transport_fingerprint(core)
    if supplied != expected:
        raise WorkerProtocolError("worker request transport fingerprint mismatch")
    result = WorkerRequest(
        generation,
        bundle_fingerprint,
        conversion_request,
        observation,
        supplied,
    )
    _validate_worker_request(result)
    return result


def encode_cancel(request: WorkerRequest) -> bytes:
    _validate_worker_request(request)
    return _encode_bounded(
        {
            "schema": PROTOCOL_SCHEMA,
            "kind": "cancel",
            "generation": request.generation,
            "bundle_fingerprint": request.bundle_fingerprint,
            "transport_fingerprint": request.transport_fingerprint,
        },
        MAX_CONTROL_BYTES,
        "control",
    )


def decode_control(frame: bytes) -> WorkerControl:
    value = _decode_bounded(frame, MAX_CONTROL_BYTES, "control")
    data = _object(value, "control envelope")
    _exact_fields(
        data,
        {
            "schema",
            "kind",
            "generation",
            "bundle_fingerprint",
            "transport_fingerprint",
        },
        "control envelope",
    )
    if data["schema"] != PROTOCOL_SCHEMA or data["kind"] != "cancel":
        raise WorkerProtocolError("incompatible worker control envelope")
    return WorkerControl(
        _generation(data["generation"]),
        _sha256(data["bundle_fingerprint"], "bundle fingerprint"),
        _sha256(data["transport_fingerprint"], "transport fingerprint"),
    )


def send_request(connection: ByteConnection, request: WorkerRequest) -> None:
    _send_frame(connection, encode_request(request), MAX_REQUEST_BYTES, "request")


def receive_request(connection: ByteConnection) -> WorkerRequest:
    return decode_request(_receive_frame(connection, MAX_REQUEST_BYTES, "request"))


def send_cancel(connection: ByteConnection, request: WorkerRequest) -> None:
    _send_frame(connection, encode_cancel(request), MAX_CONTROL_BYTES, "control")


def receive_control(connection: ByteConnection) -> WorkerControl:
    return decode_control(_receive_frame(connection, MAX_CONTROL_BYTES, "control"))


def _request_envelope_core(
    generation: int,
    bundle_fingerprint: str,
    request: ConversionRequest,
    observation: ObservationOptions,
) -> dict[str, object]:
    return {
        "schema": PROTOCOL_SCHEMA,
        "kind": "request",
        "generation": generation,
        "bundle_fingerprint": bundle_fingerprint,
        "request": _request_to_data(request),
        "observation": _observation_to_data(observation),
    }


def _transport_fingerprint(value: object) -> str:
    return fingerprint("worker-request-transport", value).value


def _validate_worker_request(request: WorkerRequest) -> None:
    if not isinstance(request, WorkerRequest):
        raise WorkerProtocolError("worker request envelope is malformed")
    _generation(request.generation)
    _sha256(request.bundle_fingerprint, "bundle fingerprint")
    _sha256(request.transport_fingerprint, "transport fingerprint")
    _request_to_data(request.request)
    _observation_to_data(request.observation)
    if request.bundle_fingerprint != bundle_fingerprint_for_request(request.request):
        raise WorkerProtocolError("worker request bundle fingerprint mismatch")
