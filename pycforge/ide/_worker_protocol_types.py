"""Shared immutable types and bounds for the worker protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.request import ConversionRequest, ObservationOptions
from pycforge.converter.core.result import ConversionResult


PROTOCOL_SCHEMA = "pycforge.worker-protocol/0.1"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_CONTROL_BYTES = 4 * 1024
MAX_EVENT_BYTES = 128 * 1024 * 1024
MAX_SOURCE_BYTES = 1_000_000
MAX_SOURCE_DOCUMENTS = 64
MAX_JSON_DEPTH = 256
MAX_DIAGNOSTICS = 1_000
MAX_FAILURE_MESSAGE_CHARS = 1_000

FAILURE_CLASSIFICATIONS = frozenset(
    {
        "protocol-error",
        "request-transport-error",
        "worker-resource-exhaustion",
        "worker-internal-error",
    }
)


class WorkerProtocolError(ValueError):
    """A frame is malformed, incompatible, oversized, or fails custody checks."""


class ByteConnection(Protocol):
    """The deliberately narrow subset of a multiprocessing connection we use."""

    def send_bytes(self, buffer: bytes) -> None: ...

    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    generation: int
    bundle_fingerprint: str
    request: ConversionRequest
    observation: ObservationOptions
    transport_fingerprint: str

    @classmethod
    def create(
        cls,
        generation: int,
        bundle_fingerprint: str,
        request: ConversionRequest,
        observation: ObservationOptions | None = None,
    ) -> "WorkerRequest":
        from ._worker_request_codec import create_worker_request

        return create_worker_request(
            generation,
            bundle_fingerprint,
            request,
            observation,
        )


@dataclass(frozen=True, slots=True)
class WorkerControl:
    generation: int
    bundle_fingerprint: str
    transport_fingerprint: str


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    kind: str
    generation: int | None
    bundle_fingerprint: str | None
    transport_fingerprint: str | None
    progress: ConversionProgress | None = None
    result: ConversionResult | None = None
    mappings: tuple[dict[str, Any], ...] = ()
    failure_classification: str | None = None
    message: str | None = None
