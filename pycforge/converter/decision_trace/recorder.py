from __future__ import annotations

from copy import deepcopy
from threading import Lock


class DecisionTraceRecorder:
    """Bounded recorder for deterministic, level-filtered trace events."""

    _SUMMARY_KINDS = frozenset({"stage_enter", "stage_completed"})
    _DECISION_KINDS = _SUMMARY_KINDS | {"rule_plan"}

    def __init__(self, level: str, limit: int, fail_on_record: bool = False) -> None:
        self.level = level
        self.enabled = level != "None"
        self.limit = limit
        self.fail_on_record = fail_on_record
        self._events: list[dict[str, object]] = []
        self._truncated = False
        self._failed = False
        self._lock = Lock()

    def _includes(self, event: dict[str, object]) -> bool:
        kind = event.get("kind")
        if self.level == "Summary":
            return kind in self._SUMMARY_KINDS
        if self.level == "Decisions":
            return kind in self._DECISION_KINDS
        return self.level == "Full"

    def record(self, event: dict[str, object]) -> None:
        if not self.enabled or not self._includes(event):
            return
        try:
            if self.fail_on_record:
                raise RuntimeError("injected observer failure")
            with self._lock:
                if len(self._events) >= self.limit:
                    self._truncated = True
                else:
                    self._events.append(deepcopy(event))
        except Exception:
            self._failed = True

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "level": self.level,
                "events": tuple(deepcopy(self._events)),
                "truncated": self._truncated,
                "observer_failed": self._failed,
            }
