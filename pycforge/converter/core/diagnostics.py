from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from threading import Lock
from .enums import Severity
from .stage_artifact import freeze_value

@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    stage: str
    message: str
    effect_on_status: bool = True
    source_span: dict[str, object]|None = None
    related_spans: tuple[dict[str, object], ...] = ()
    causal_diagnostic_id: str | None = None
    target_contract: str | None = None
    semantic_policy: str | None = None
    rule_id: str | None = None
    fact_references: tuple[str, ...] = ()
    obligation_references: tuple[str, ...] = ()
    explanation: str | None = None
    remediation: str | None = None
    approximation_code: str | None = None
    semantic_delta: str | None = None
    source_module_id: str | None = None
    source_logical_name: str | None = None

    def __post_init__(self) -> None:
        if self.source_span is not None:
            object.__setattr__(self, "source_span", freeze_value(self.source_span))
        object.__setattr__(self, "related_spans", tuple(freeze_value(item) for item in self.related_spans))
        object.__setattr__(self, "fact_references", tuple(self.fact_references))
        object.__setattr__(self, "obligation_references", tuple(self.obligation_references))

    @property
    def diagnostic_id(self) -> str:
        identity = {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "source_span": self.source_span,
            "rule_id": self.rule_id,
            "cause": self.causal_diagnostic_id,
        }
        raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return "diag-" + hashlib.sha256(raw).hexdigest()[:20]

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnostic_id": self.diagnostic_id,
            "code": self.code,
            "severity": self.severity.value,
            "stage": self.stage,
            "message": self.message,
            "effect_on_status": self.effect_on_status,
            "source_span": self.source_span,
            "related_spans": list(self.related_spans),
            "causal_diagnostic_id": self.causal_diagnostic_id,
            "target_contract": self.target_contract,
            "semantic_policy": self.semantic_policy,
            "rule_id": self.rule_id,
            "fact_references": list(self.fact_references),
            "obligation_references": list(self.obligation_references),
            "explanation": self.explanation,
            "remediation": self.remediation,
            "approximation_code": self.approximation_code,
            "semantic_delta": self.semantic_delta,
            "source_module_id": self.source_module_id,
            "source_logical_name": self.source_logical_name,
        }

class DiagnosticCollector:
    def __init__(self, limit: int, document_order: tuple[str, ...] = ()) -> None:
        self._limit=limit; self._items:list[Diagnostic]=[]; self._ids:set[str]=set(); self._lock=Lock()
        self._document_order={document_id:ordinal for ordinal,document_id in enumerate(document_order)}
    def add(self, diagnostic: Diagnostic) -> None:
        with self._lock:
            if diagnostic.diagnostic_id in self._ids:
                return
            if len(self._items) < self._limit:
                self._items.append(diagnostic)
                self._ids.add(diagnostic.diagnostic_id)
    def snapshot(self) -> tuple[Diagnostic, ...]:
        with self._lock:
            def key(diagnostic: Diagnostic) -> tuple[object, ...]:
                span = diagnostic.source_span or {}
                start = span.get("start", {}) if isinstance(span, dict) else {}
                offset = start.get("offset") if isinstance(start, dict) else None
                document_id = span.get("document_id") if isinstance(span, dict) else None
                document_ordinal = -1 if document_id is None else self._document_order.get(document_id, 2**31 - 1)
                return (document_ordinal, offset if isinstance(offset, int) else -1, diagnostic.stage, diagnostic.severity.value, diagnostic.code, diagnostic.diagnostic_id)
            return tuple(sorted(self._items, key=key))
