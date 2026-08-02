from __future__ import annotations

from copy import deepcopy
from threading import Lock


class TelemetrySink:
    """Best-effort operational observer isolated from semantic products."""

    def __init__(self, enabled: bool, limit: int, fail_on_record: bool = False) -> None:
        self.enabled = enabled
        self.limit = limit
        self.fail_on_record = fail_on_record
        self._events: list[dict[str, object]] = []
        self._dropped = 0
        self._failed = False
        self._lock = Lock()

    def record(self, event: dict[str, object]) -> None:
        if not self.enabled:
            return
        try:
            if self.fail_on_record:
                raise RuntimeError("injected observer failure")
            with self._lock:
                if len(self._events) >= self.limit:
                    self._dropped += 1
                else:
                    self._events.append(deepcopy(event))
        except Exception:
            self._failed = True

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "events": tuple(deepcopy(self._events)),
                "dropped": self._dropped,
                "observer_failed": self._failed,
            }
