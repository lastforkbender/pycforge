from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class ValueCategory(str, Enum):
    INTEGER = "integer-like"
    FLOAT = "floating-like"
    BOOLEAN = "boolean-like"
    STRING = "string-like"
    LIST = "fixed-list-like"
    TUPLE = "fixed-tuple-like"
    DICTIONARY = "fixed-dictionary-like"
    RECORD = "static-record-like"
    NONE = "none-like"
    CALLABLE = "callable-like"
    UNKNOWN = "unknown"
    CONTRADICTORY = "contradictory"


class EffectKind(str, Enum):
    PURE = "pure-value-construction"
    READS_STATE = "reads-state"
    WRITES_STATE = "writes-state"
    MAY_FAIL = "may-encounter-unsupported-python-failure"
    CONTROL_FLOW = "control-flow-boundary"


class SupportState(str, Enum):
    SUPPORTED_DIRECT = "SupportedDirect"
    SUPPORTED_WITH_HELPER = "SupportedWithHelper"
    SUPPORTED_APPROXIMATION = "SupportedApproximation"
    UNSUPPORTED = "Unsupported"
    BLOCKED = "BlockedByDependency"


@dataclass(frozen=True, slots=True)
class FactProvenance:
    source_node_ids: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"source_node_ids": list(self.source_node_ids), "evidence": list(self.evidence)}


@dataclass(frozen=True, slots=True)
class FactRecord:
    key: str
    value: Any
    provenance: FactProvenance

    def to_dict(self) -> dict[str, Any]:
        value = self.value.value if isinstance(self.value, Enum) else self.value
        if hasattr(value, "to_dict"):
            value = value.to_dict()
        return {"key": self.key, "value": value, "provenance": self.provenance.to_dict()}


@dataclass(frozen=True, slots=True)
class FactTable:
    schema_version: str
    table_id: str
    producer_stage: str
    key_domain: str
    completeness: Completeness
    invalidation_dependencies: tuple[str, ...]
    records: tuple[FactRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "table_id": self.table_id,
            "producer_stage": self.producer_stage,
            "key_domain": self.key_domain,
            "completeness": self.completeness.value,
            "invalidation_dependencies": list(self.invalidation_dependencies),
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True, slots=True)
class ScopeFact:
    scope_id: str
    scope_kind: str
    owner_node_id: str
    parent_scope_id: str | None
    child_scope_ids: tuple[str, ...]
    binding_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "scope_kind": self.scope_kind,
            "owner_node_id": self.owner_node_id,
            "parent_scope_id": self.parent_scope_id,
            "child_scope_ids": list(self.child_scope_ids),
            "binding_ids": list(self.binding_ids),
        }


@dataclass(frozen=True, slots=True)
class BindingFact:
    binding_id: str
    scope_id: str
    source_name: str
    binding_kind: str
    declaration_node_id: str
    occurrence_node_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "scope_id": self.scope_id,
            "source_name": self.source_name,
            "binding_kind": self.binding_kind,
            "declaration_node_id": self.declaration_node_id,
            "occurrence_node_ids": list(self.occurrence_node_ids),
        }


@dataclass(frozen=True, slots=True)
class RepresentationPlan:
    plan_id: str
    decision_key: str
    c_type: str | None
    passing: str
    ownership: str
    lifetime_region: str
    obligations: tuple[str, ...]
    unresolved_obligations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "decision_key": self.decision_key,
            "c_type": self.c_type,
            "passing": self.passing,
            "ownership": self.ownership,
            "lifetime_region": self.lifetime_region,
            "obligations": list(self.obligations),
            "unresolved_obligations": list(self.unresolved_obligations),
        }


@dataclass(frozen=True, slots=True)
class NamePlan:
    binding_id: str
    generated_name: str

    def to_dict(self) -> dict[str, str]:
        return {"binding_id": self.binding_id, "generated_name": self.generated_name}
