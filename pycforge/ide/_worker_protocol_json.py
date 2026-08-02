"""Strict canonical-JSON parsing and byte-only connection framing."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pycforge.converter.core.fingerprint import canonical_json

from ._worker_protocol_types import (
    MAX_JSON_DEPTH,
    ByteConnection,
    WorkerProtocolError,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _send_frame(
    connection: ByteConnection,
    frame: bytes,
    maximum: int,
    role: str,
) -> None:
    if not isinstance(frame, bytes) or len(frame) > maximum:
        raise WorkerProtocolError(f"worker {role} frame exceeds protocol bounds")
    connection.send_bytes(frame)


def _receive_frame(
    connection: ByteConnection,
    maximum: int,
    role: str,
) -> bytes:
    try:
        frame = connection.recv_bytes(maximum)
    except OSError as exc:
        raise WorkerProtocolError(
            f"worker {role} frame exceeds protocol bounds or is unreadable"
        ) from exc
    if not isinstance(frame, bytes) or len(frame) > maximum:
        raise WorkerProtocolError(f"worker {role} frame exceeds protocol bounds")
    return frame


def _encode_bounded(value: object, maximum: int, role: str) -> bytes:
    try:
        frame = canonical_json(value)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise WorkerProtocolError(f"worker {role} is not canonical JSON") from exc
    if len(frame) > maximum:
        raise WorkerProtocolError(f"worker {role} frame exceeds protocol bounds")
    return frame


def _decode_bounded(frame: bytes, maximum: int, role: str) -> object:
    if not isinstance(frame, bytes) or len(frame) > maximum:
        raise WorkerProtocolError(f"worker {role} frame exceeds protocol bounds")
    try:
        text = frame.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_bounded_json_int,
            parse_float=_finite_json_float,
        )
        _validate_json_tree(value)
        if canonical_json(value) != frame:
            raise WorkerProtocolError(
                f"worker {role} frame is not canonical JSON"
            )
    except WorkerProtocolError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise WorkerProtocolError(f"worker {role} frame is not valid JSON") from exc
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkerProtocolError("worker JSON contains duplicate object keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise WorkerProtocolError(f"worker JSON contains forbidden constant {value}")


def _bounded_json_int(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise WorkerProtocolError("worker JSON integer exceeds protocol bounds")
    return int(value)


def _finite_json_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise WorkerProtocolError("worker JSON number must be finite")
    return result


def _validate_json_tree(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise WorkerProtocolError("worker JSON nesting exceeds protocol bounds")
    if isinstance(value, str):
        if _contains_surrogate(value):
            raise WorkerProtocolError("worker JSON contains invalid Unicode")
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkerProtocolError("worker JSON number must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_tree(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or _contains_surrogate(key):
                raise WorkerProtocolError("worker JSON object key is invalid")
            _validate_json_tree(item, depth + 1)
        return
    raise WorkerProtocolError("worker JSON contains unsupported value")


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _object(value: object, role: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerProtocolError(f"{role} must be an object")
    return value


def _optional_object(value: object, role: str) -> dict[str, Any] | None:
    return None if value is None else _object(value, role)


def _list(value: object, role: str) -> list[Any]:
    if not isinstance(value, list):
        raise WorkerProtocolError(f"{role} must be an array")
    return value


def _exact_fields(
    value: dict[str, Any],
    expected: set[str] | frozenset[str],
    role: str,
) -> None:
    if set(value) != set(expected):
        raise WorkerProtocolError(f"{role} fields are incomplete or unknown")


def _string(value: object, role: str) -> str:
    if not isinstance(value, str) or _contains_surrogate(value):
        raise WorkerProtocolError(f"{role} must be valid Unicode text")
    return value


def _nonempty_string(value: object, role: str) -> str:
    result = _string(value, role)
    if not result:
        raise WorkerProtocolError(f"{role} must be non-empty")
    return result


def _string_list(value: object, role: str) -> tuple[str, ...]:
    return tuple(_string(item, role) for item in _list(value, role))


def _nonnegative_integer(value: object, role: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WorkerProtocolError(f"{role} must be a non-negative integer")
    return value


def _generation(value: object) -> int:
    result = _nonnegative_integer(value, "worker generation")
    if result == 0 or result > 2**63 - 1:
        raise WorkerProtocolError("worker generation is outside protocol bounds")
    return result


def _sha256(value: object, role: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise WorkerProtocolError(f"{role} must be a lowercase SHA-256 value")
    return value
