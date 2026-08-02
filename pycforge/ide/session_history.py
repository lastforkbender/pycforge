"""Bounded, payload-free conversion history for the current application session.

History is a presentation observer.  It records only immutable identities and
small terminal-state facts.  It deliberately has no source text, generated C,
diagnostic bodies, artifacts, timestamps, or persistence contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


MAX_CONVERSION_HISTORY_ENTRIES = 64
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_MAX_STATUS_CHARS = 64
_MAX_STAGE_CHARS = 128
_MAX_REASON_CHARS = 128


def _require_count(value: object, label: str, *, positive: bool = False) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < (1 if positive else 0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be a {qualifier} integer")


def _require_fingerprint(value: object, label: str, *, optional: bool) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or _FINGERPRINT.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical SHA-256 value")


def _require_label(
    value: object,
    label: str,
    *,
    maximum: int,
    optional: bool,
) -> None:
    if value is None and optional:
        return
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{label} is empty, oversized, or contains controls")


@dataclass(frozen=True, slots=True)
class ConversionHistoryEntry:
    """One accepted terminal observation for the current request."""

    request_sequence: int
    revision_generation: int
    bundle_fingerprint: str
    request_fingerprint: str | None
    output_fingerprint: str | None
    status: str
    diagnostic_count: int
    completed_stage_count: int
    total_stage_count: int
    stage: str | None
    published: bool
    reason: str | None

    def __post_init__(self) -> None:
        _require_count(
            self.request_sequence,
            "request sequence",
            positive=True,
        )
        _require_count(self.revision_generation, "revision generation")
        _require_fingerprint(
            self.bundle_fingerprint,
            "bundle fingerprint",
            optional=False,
        )
        _require_fingerprint(
            self.request_fingerprint,
            "request fingerprint",
            optional=True,
        )
        _require_fingerprint(
            self.output_fingerprint,
            "output fingerprint",
            optional=True,
        )
        _require_label(
            self.status,
            "status",
            maximum=_MAX_STATUS_CHARS,
            optional=False,
        )
        _require_count(self.diagnostic_count, "diagnostic count")
        _require_count(
            self.completed_stage_count,
            "completed stage count",
        )
        _require_count(self.total_stage_count, "total stage count")
        if self.completed_stage_count > self.total_stage_count:
            raise ValueError(
                "completed stage count cannot exceed total stage count"
            )
        _require_label(
            self.stage,
            "stage",
            maximum=_MAX_STAGE_CHARS,
            optional=True,
        )
        if not isinstance(self.published, bool):
            raise TypeError("published must be a boolean")
        _require_label(
            self.reason,
            "reason",
            maximum=_MAX_REASON_CHARS,
            optional=True,
        )


def append_conversion_history(
    history: tuple[ConversionHistoryEntry, ...],
    entry: ConversionHistoryEntry,
) -> tuple[ConversionHistoryEntry, ...]:
    """Append one request exactly once and retain the newest 64 entries."""

    if not isinstance(history, tuple) or any(
        not isinstance(item, ConversionHistoryEntry) for item in history
    ):
        raise TypeError("conversion history must be an entry tuple")
    if not isinstance(entry, ConversionHistoryEntry):
        raise TypeError("conversion history entry has the wrong type")
    if any(
        item.request_sequence == entry.request_sequence for item in history
    ):
        return history
    return (history + (entry,))[-MAX_CONVERSION_HISTORY_ENTRIES:]


__all__ = [
    "MAX_CONVERSION_HISTORY_ENTRIES",
    "ConversionHistoryEntry",
    "append_conversion_history",
]
