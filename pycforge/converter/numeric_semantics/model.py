"""Immutable evidence for the bounded Phase 14A numeric slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FloorArithmeticKind(str, Enum):
    FLOOR_DIVIDE = "floor-divide"
    FLOOR_MODULO = "floor-modulo"


class NumericAnalysisCanceled(Exception):
    """Raised internally when conversion cancellation retires numeric work."""


class NumericAnalysisError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        node_id: str,
        source_span: dict[str, object] | None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.node_id = node_id
        self.source_span = source_span


@dataclass(frozen=True, slots=True)
class NumericOperationFact:
    operation_id: str
    binop_node_id: str
    function_node_id: str
    module_id: str
    document_id: str
    logical_name: str
    operator_node_id: str
    operator_kind: FloorArithmeticKind
    left_node_id: str
    right_node_id: str
    left_category: str
    right_category: str
    result_category: str
    left_c_type: str
    right_c_type: str
    result_c_type: str
    divisor_value: int
    divisor_literal_node_ids: tuple[str, ...]
    literal_shape: str
    divisor_in_admitted_domain: bool
    divisor_nonzero_proved: bool
    negative_one_divisor_excluded: bool
    minimum_signed_divisor_excluded: bool
    helper_requirement: str
    evaluation_order: tuple[str, str]
    operands_evaluated_once: bool
    c_type: str
    failure_policy: str
    support_state: str
    parameter_ownership: str
    result_ownership: str
    allocation_model: str
    cleanup_model: str
    runtime_failure_channel: str
    target_contract: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "binop_node_id": self.binop_node_id,
            "function_node_id": self.function_node_id,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "operator_node_id": self.operator_node_id,
            "operator_kind": self.operator_kind.value,
            "left_node_id": self.left_node_id,
            "right_node_id": self.right_node_id,
            "left_category": self.left_category,
            "right_category": self.right_category,
            "result_category": self.result_category,
            "left_c_type": self.left_c_type,
            "right_c_type": self.right_c_type,
            "result_c_type": self.result_c_type,
            "divisor_value": self.divisor_value,
            "divisor_literal_node_ids": list(self.divisor_literal_node_ids),
            "literal_shape": self.literal_shape,
            "divisor_in_admitted_domain": self.divisor_in_admitted_domain,
            "divisor_nonzero_proved": self.divisor_nonzero_proved,
            "negative_one_divisor_excluded": self.negative_one_divisor_excluded,
            "minimum_signed_divisor_excluded": self.minimum_signed_divisor_excluded,
            "helper_requirement": self.helper_requirement,
            "evaluation_order": list(self.evaluation_order),
            "operands_evaluated_once": self.operands_evaluated_once,
            "c_type": self.c_type,
            "failure_policy": self.failure_policy,
            "support_state": self.support_state,
            "parameter_ownership": self.parameter_ownership,
            "result_ownership": self.result_ownership,
            "allocation_model": self.allocation_model,
            "cleanup_model": self.cleanup_model,
            "runtime_failure_channel": self.runtime_failure_channel,
            "target_contract": self.target_contract,
        }


@dataclass(frozen=True, slots=True)
class BoundedNumericAnalysis:
    operations: tuple[NumericOperationFact, ...]


__all__ = [
    "BoundedNumericAnalysis",
    "FloorArithmeticKind",
    "NumericAnalysisCanceled",
    "NumericAnalysisError",
    "NumericOperationFact",
]
