"""Immutable facts for the Phase 11 fixed local-container profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.contracts.configuration import MAX_CONTAINER_ELEMENTS



@dataclass(frozen=True, slots=True)
class ContainerShapeFact:
    literal_node_id: str
    container_kind: str
    capacity: int
    element_node_ids: tuple[str, ...]
    key_node_ids: tuple[str, ...]
    value_node_ids: tuple[str, ...]
    element_category: ValueCategory
    key_category: ValueCategory
    value_category: ValueCategory
    key_values: tuple[int | str, ...]
    storage_model: str
    mutable: bool
    valid: bool
    diagnostic_code: str | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "literal_node_id": self.literal_node_id,
            "container_kind": self.container_kind,
            "capacity": self.capacity,
            "element_node_ids": list(self.element_node_ids),
            "key_node_ids": list(self.key_node_ids),
            "value_node_ids": list(self.value_node_ids),
            "element_category": self.element_category.value,
            "key_category": self.key_category.value,
            "value_category": self.value_category.value,
            "key_values": list(self.key_values),
            "storage_model": self.storage_model,
            "mutable": self.mutable,
            "valid": self.valid,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ContainerBindingFact:
    binding_id: str
    source_name: str
    assignment_node_id: str
    target_node_id: str
    literal_node_id: str
    container_kind: str
    capacity: int
    element_category: ValueCategory
    key_category: ValueCategory
    value_category: ValueCategory
    allowed_use_node_ids: tuple[str, ...]
    invalid_use_node_ids: tuple[str, ...]
    valid: bool
    diagnostic_code: str | None
    rejection_node_id: str | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "source_name": self.source_name,
            "assignment_node_id": self.assignment_node_id,
            "target_node_id": self.target_node_id,
            "literal_node_id": self.literal_node_id,
            "container_kind": self.container_kind,
            "capacity": self.capacity,
            "element_category": self.element_category.value,
            "key_category": self.key_category.value,
            "value_category": self.value_category.value,
            "allowed_use_node_ids": list(self.allowed_use_node_ids),
            "invalid_use_node_ids": list(self.invalid_use_node_ids),
            "valid": self.valid,
            "diagnostic_code": self.diagnostic_code,
            "rejection_node_id": self.rejection_node_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ContainerAccessFact:
    subscript_node_id: str
    binding_id: str | None
    container_kind: str | None
    slice_node_id: str | None
    result_category: ValueCategory
    resolved_offset: int | None
    source_index: int | None
    key_value: int | str | None
    supported: bool
    diagnostic_code: str | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscript_node_id": self.subscript_node_id,
            "binding_id": self.binding_id,
            "container_kind": self.container_kind,
            "slice_node_id": self.slice_node_id,
            "result_category": self.result_category.value,
            "resolved_offset": self.resolved_offset,
            "source_index": self.source_index,
            "key_value": self.key_value,
            "supported": self.supported,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ContainerIterationFact:
    for_node_id: str
    binding_id: str | None
    container_kind: str | None
    target_node_id: str | None
    target_category: ValueCategory
    capacity: int
    order_policy: str
    supported: bool
    diagnostic_code: str | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "for_node_id": self.for_node_id,
            "binding_id": self.binding_id,
            "container_kind": self.container_kind,
            "target_node_id": self.target_node_id,
            "target_category": self.target_category.value,
            "capacity": self.capacity,
            "order_policy": self.order_policy,
            "supported": self.supported,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
        }
