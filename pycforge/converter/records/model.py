"""Immutable facts for the Phase 13 bounded static-record profile.

This module deliberately describes source semantics only.  It has no C IR,
renderer, allocation, or runtime dependency, which keeps the representation
gate independently testable before lowering is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycforge.converter.analysis.model import ValueCategory


MAX_RECORD_FIELDS = 64


class RecordValueCategory(str, Enum):
    DEFINITION = "immutable-static-record-definition"
    INSTANCE = "immutable-static-record-like"


class RecordAnalysisError(Exception):
    """Deterministic source rejection raised by static-record analysis."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node_id: str,
        module_id: str,
        document_id: str,
        logical_name: str,
        source_span: dict[str, Any] | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.node_id = node_id
        self.module_id = module_id
        self.document_id = document_id
        self.logical_name = logical_name
        self.source_span = source_span

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "source_span": self.source_span,
        }


class RecordAnalysisCanceled(Exception):
    """Internal cooperative-cancellation signal for static-record analysis."""


@dataclass(frozen=True, slots=True)
class RecordDefinitionFact:
    record_id: str
    class_node_id: str
    class_binding_id: str
    source_name: str
    flattened_name: str
    module_id: str
    document_id: str
    logical_name: str
    field_ids: tuple[str, ...]
    initializer_id: str
    category: RecordValueCategory
    storage_model: str
    ownership_model: str
    lifetime_model: str
    aliasing_model: str
    cleanup_model: str
    nullability_model: str
    mutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "class_node_id": self.class_node_id,
            "class_binding_id": self.class_binding_id,
            "source_name": self.source_name,
            "flattened_name": self.flattened_name,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "field_ids": list(self.field_ids),
            "initializer_id": self.initializer_id,
            "category": self.category.value,
            "storage_model": self.storage_model,
            "ownership_model": self.ownership_model,
            "lifetime_model": self.lifetime_model,
            "aliasing_model": self.aliasing_model,
            "cleanup_model": self.cleanup_model,
            "nullability_model": self.nullability_model,
            "mutable": self.mutable,
        }


@dataclass(frozen=True, slots=True)
class RecordFieldFact:
    field_id: str
    record_id: str
    class_node_id: str
    declaration_node_id: str
    target_node_id: str
    annotation_node_id: str
    source_name: str
    ordinal: int
    category: ValueCategory
    module_id: str
    document_id: str
    logical_name: str
    mutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "record_id": self.record_id,
            "class_node_id": self.class_node_id,
            "declaration_node_id": self.declaration_node_id,
            "target_node_id": self.target_node_id,
            "annotation_node_id": self.annotation_node_id,
            "source_name": self.source_name,
            "ordinal": self.ordinal,
            "category": self.category.value,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "mutable": self.mutable,
        }


@dataclass(frozen=True, slots=True)
class RecordInitializerFact:
    initializer_id: str
    record_id: str
    function_node_id: str
    arguments_node_id: str
    self_parameter_node_id: str
    parameter_node_ids: tuple[str, ...]
    assignment_node_ids: tuple[str, ...]
    field_ids: tuple[str, ...]
    module_id: str
    document_id: str
    logical_name: str
    receiver_model: str
    evaluation_order: str
    initialization_completeness: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "initializer_id": self.initializer_id,
            "record_id": self.record_id,
            "function_node_id": self.function_node_id,
            "arguments_node_id": self.arguments_node_id,
            "self_parameter_node_id": self.self_parameter_node_id,
            "parameter_node_ids": list(self.parameter_node_ids),
            "assignment_node_ids": list(self.assignment_node_ids),
            "field_ids": list(self.field_ids),
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "receiver_model": self.receiver_model,
            "evaluation_order": self.evaluation_order,
            "initialization_completeness": self.initialization_completeness,
        }


@dataclass(frozen=True, slots=True)
class RecordInstanceFact:
    instance_id: str
    record_id: str
    class_node_id: str
    owner_function_node_id: str
    construction_node_id: str
    assignment_node_id: str
    target_node_id: str
    binding_id: str
    source_name: str
    argument_node_ids: tuple[str, ...]
    module_id: str
    document_id: str
    logical_name: str
    category: RecordValueCategory
    storage_model: str
    ownership_model: str
    lifetime_model: str
    aliasing_model: str
    cleanup_model: str
    nullability_model: str
    allocation_model: str
    mutable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "record_id": self.record_id,
            "class_node_id": self.class_node_id,
            "owner_function_node_id": self.owner_function_node_id,
            "construction_node_id": self.construction_node_id,
            "assignment_node_id": self.assignment_node_id,
            "target_node_id": self.target_node_id,
            "binding_id": self.binding_id,
            "source_name": self.source_name,
            "argument_node_ids": list(self.argument_node_ids),
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "category": self.category.value,
            "storage_model": self.storage_model,
            "ownership_model": self.ownership_model,
            "lifetime_model": self.lifetime_model,
            "aliasing_model": self.aliasing_model,
            "cleanup_model": self.cleanup_model,
            "nullability_model": self.nullability_model,
            "allocation_model": self.allocation_model,
            "mutable": self.mutable,
        }


@dataclass(frozen=True, slots=True)
class RecordInstanceBindingFact:
    binding_id: str
    instance_id: str
    record_id: str
    source_name: str
    declaration_node_id: str
    occurrence_node_ids: tuple[str, ...]
    allowed_field_access_node_ids: tuple[str, ...]
    owner_function_node_id: str
    module_id: str
    document_id: str
    logical_name: str
    category: RecordValueCategory
    single_assignment: bool
    noalias: bool
    escapes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "instance_id": self.instance_id,
            "record_id": self.record_id,
            "source_name": self.source_name,
            "declaration_node_id": self.declaration_node_id,
            "occurrence_node_ids": list(self.occurrence_node_ids),
            "allowed_field_access_node_ids": list(self.allowed_field_access_node_ids),
            "owner_function_node_id": self.owner_function_node_id,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "category": self.category.value,
            "single_assignment": self.single_assignment,
            "noalias": self.noalias,
            "escapes": self.escapes,
        }


@dataclass(frozen=True, slots=True)
class RecordFieldAccessFact:
    access_node_id: str
    instance_id: str
    binding_id: str
    record_id: str
    field_id: str
    field_name: str
    field_category: ValueCategory
    owner_function_node_id: str
    module_id: str
    document_id: str
    logical_name: str
    access_mode: str
    statically_bound: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_node_id": self.access_node_id,
            "instance_id": self.instance_id,
            "binding_id": self.binding_id,
            "record_id": self.record_id,
            "field_id": self.field_id,
            "field_name": self.field_name,
            "field_category": self.field_category.value,
            "owner_function_node_id": self.owner_function_node_id,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "access_mode": self.access_mode,
            "statically_bound": self.statically_bound,
        }


@dataclass(frozen=True, slots=True)
class StaticRecordAnalysis:
    definitions: tuple[RecordDefinitionFact, ...]
    fields: tuple[RecordFieldFact, ...]
    initializers: tuple[RecordInitializerFact, ...]
    instances: tuple[RecordInstanceFact, ...]
    bindings: tuple[RecordInstanceBindingFact, ...]
    accesses: tuple[RecordFieldAccessFact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "definitions": [item.to_dict() for item in self.definitions],
            "fields": [item.to_dict() for item in self.fields],
            "initializers": [item.to_dict() for item in self.initializers],
            "instances": [item.to_dict() for item in self.instances],
            "bindings": [item.to_dict() for item in self.bindings],
            "accesses": [item.to_dict() for item in self.accesses],
        }
