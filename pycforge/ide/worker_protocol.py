"""Public facade for the bounded isolated-converter worker protocol.

Frames are canonical JSON transported through ``send_bytes`` and
``recv_bytes`` only.  The cohesive private codec modules keep request,
result/event, and low-level JSON validation responsibilities separate while
this module preserves the original Phase 15A import surface.
"""

from __future__ import annotations

from ._worker_event_codec import (
    decode_event,
    encode_failure,
    encode_progress,
    encode_terminal,
    receive_event,
    send_event,
)
from ._worker_protocol_types import (
    FAILURE_CLASSIFICATIONS,
    MAX_CONTROL_BYTES,
    MAX_DIAGNOSTICS,
    MAX_EVENT_BYTES,
    MAX_FAILURE_MESSAGE_CHARS,
    MAX_JSON_DEPTH,
    MAX_REQUEST_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_DOCUMENTS,
    PROTOCOL_SCHEMA,
    ByteConnection,
    WorkerControl,
    WorkerEvent,
    WorkerProtocolError,
    WorkerRequest,
)
from ._worker_request_codec import (
    decode_control,
    decode_request,
    encode_cancel,
    encode_request,
    receive_control,
    receive_request,
    send_cancel,
    send_request,
)
from ._worker_request_data import bundle_fingerprint_for_request


__all__ = [
    "FAILURE_CLASSIFICATIONS",
    "MAX_CONTROL_BYTES",
    "MAX_DIAGNOSTICS",
    "MAX_EVENT_BYTES",
    "MAX_FAILURE_MESSAGE_CHARS",
    "MAX_JSON_DEPTH",
    "MAX_REQUEST_BYTES",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_DOCUMENTS",
    "PROTOCOL_SCHEMA",
    "ByteConnection",
    "WorkerControl",
    "WorkerEvent",
    "WorkerProtocolError",
    "WorkerRequest",
    "bundle_fingerprint_for_request",
    "decode_control",
    "decode_event",
    "decode_request",
    "encode_cancel",
    "encode_failure",
    "encode_progress",
    "encode_request",
    "encode_terminal",
    "receive_control",
    "receive_event",
    "receive_request",
    "send_cancel",
    "send_event",
    "send_request",
]
