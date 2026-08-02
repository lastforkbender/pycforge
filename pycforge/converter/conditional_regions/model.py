"""Immutable evidence for Phase 14B conditional temporary regions.

The model describes *where* an already-supported scalar operand is evaluated.
It does not describe a new Python expression, invent a target representation,
or authorize a helper/runtime facility.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any


CONDITIONAL_REGION_TABLE_ID = "conditional-region-facts"
CONDITIONAL_REGION_KEY_DOMAIN = "conditional-region-node-id"
CONDITIONAL_REGION_LOWERING_SHAPE = "flat-guarded-assignment-v1"
CONDITIONAL_REGION_TABLE_DEPENDENCIES = (
    "value-category-facts",
    "evaluation-order-facts",
    "call-target-facts",
    "container-access-facts",
    "record-access-facts",
    "numeric-operation-facts",
)
CONDITIONAL_REGION_PROVENANCE_EVIDENCE = (
    "exact-scalar-operands",
    "unconditional-prefix",
    "accumulated-result-guard",
    "left-to-right-once",
    "branch-contained-prerequisites",
    "flat-structured-c-ir",
)

CONDITIONAL_REGION_OBLIGATIONS = (
    "scalar-operand-representations-proved",
    "unconditional-prefix-proved",
    "guard-polarity-proved",
    "short-circuit-order-preserved",
    "operands-evaluated-left-to-right-once",
    "prerequisite-statements-branch-contained",
    "intermediate-values-reused-without-reevaluation",
    "structured-c-ir-only",
    "result-materialized-once",
    "allocation-and-cleanup-absent",
    "runtime-failure-channel-unchanged",
    "source-provenance-anchored",
    "cancellation-safe-points-honored",
    "target-contract-exact",
)


class ConditionalRegionKind(str, Enum):
    BOOLEAN_SHORT_CIRCUIT = "boolean-short-circuit"
    CHAINED_COMPARISON = "chained-comparison"


class ConditionalGuardPolarity(str, Enum):
    NONE = "none"
    WHEN_RESULT_TRUE = "when-result-true"
    WHEN_RESULT_FALSE = "when-result-false"


class ConditionalEvaluationMode(str, Enum):
    UNCONDITIONAL = "unconditional"
    GUARDED = "guarded"


class ConditionalRegionAnalysisCanceled(Exception):
    """Raised internally when cancellation retires conditional analysis."""


class ConditionalRegionValidationCanceled(Exception):
    """Raised when independent reconstruction observes cooperative cancellation."""


class ConditionalRegionAnalysisError(Exception):
    """A source-facing failure to close an otherwise eligible region proof."""

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
class ConditionalOperandPlacementFact:
    operand_node_id: str
    ordinal: int
    category: str
    evaluation_mode: ConditionalEvaluationMode
    guard_polarity: ConditionalGuardPolarity
    guard_after_operand_ordinal: int | None
    requires_statement_prelude: bool
    prerequisite_node_ids: tuple[str, ...]
    legacy_direct_safe: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "operand_node_id": self.operand_node_id,
            "ordinal": self.ordinal,
            "category": self.category,
            "evaluation_mode": self.evaluation_mode.value,
            "guard_polarity": self.guard_polarity.value,
            "guard_after_operand_ordinal": self.guard_after_operand_ordinal,
            "requires_statement_prelude": self.requires_statement_prelude,
            "prerequisite_node_ids": list(self.prerequisite_node_ids),
            "legacy_direct_safe": self.legacy_direct_safe,
        }


@dataclass(frozen=True, slots=True)
class ConditionalRegionFact:
    region_id: str
    region_node_id: str
    region_kind: ConditionalRegionKind
    function_node_id: str
    module_id: str
    document_id: str
    logical_name: str
    operator_node_ids: tuple[str, ...]
    operator_kinds: tuple[str, ...]
    operand_node_ids: tuple[str, ...]
    operand_categories: tuple[str, ...]
    unconditional_prefix_count: int
    placements: tuple[ConditionalOperandPlacementFact, ...]
    guarded_operand_node_ids: tuple[str, ...]
    prerequisite_node_ids: tuple[str, ...]
    result_category: str
    result_c_type: str
    evaluation_order: tuple[str, ...]
    operands_evaluated_once: bool
    lowering_shape: str
    allocation_model: str
    cleanup_model: str
    runtime_failure_channel: str
    target_contract: str

    @property
    def guarded_operand_count(self) -> int:
        return len(self.operand_node_ids) - self.unconditional_prefix_count

    @property
    def rule_facts(self) -> tuple[str, ...]:
        return (
            f"conditional-region:{self.region_node_id}",
            f"conditional-region-kind:{self.region_kind.value}",
            f"conditional-unconditional-prefix:{self.unconditional_prefix_count}",
            f"conditional-guarded-operand-count:{self.guarded_operand_count}",
            f"conditional-lowering-shape:{self.lowering_shape}",
            f"conditional-target:{self.target_contract}",
        )

    @property
    def explanation_tokens(self) -> tuple[str, ...]:
        return (
            "conditional-region",
            self.region_kind.value,
            "unconditional-prefix",
            str(self.unconditional_prefix_count),
            "guarded-operands",
            str(self.guarded_operand_count),
            "lowered-as",
            self.lowering_shape,
        )

    @property
    def provenance_node_ids(self) -> tuple[str, ...]:
        ordered = (
            self.region_node_id,
            self.function_node_id,
            *self.operator_node_ids,
            *self.operand_node_ids,
            *self.prerequisite_node_ids,
        )
        return tuple(dict.fromkeys(ordered))

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_node_id": self.region_node_id,
            "region_kind": self.region_kind.value,
            "function_node_id": self.function_node_id,
            "module_id": self.module_id,
            "document_id": self.document_id,
            "logical_name": self.logical_name,
            "operator_node_ids": list(self.operator_node_ids),
            "operator_kinds": list(self.operator_kinds),
            "operand_node_ids": list(self.operand_node_ids),
            "operand_categories": list(self.operand_categories),
            "unconditional_prefix_count": self.unconditional_prefix_count,
            "placements": [item.to_dict() for item in self.placements],
            "guarded_operand_node_ids": list(self.guarded_operand_node_ids),
            "prerequisite_node_ids": list(self.prerequisite_node_ids),
            "result_category": self.result_category,
            "result_c_type": self.result_c_type,
            "evaluation_order": list(self.evaluation_order),
            "operands_evaluated_once": self.operands_evaluated_once,
            "lowering_shape": self.lowering_shape,
            "allocation_model": self.allocation_model,
            "cleanup_model": self.cleanup_model,
            "runtime_failure_channel": self.runtime_failure_channel,
            "target_contract": self.target_contract,
        }


@dataclass(frozen=True, slots=True)
class ConditionalRegionAnalysis:
    regions: tuple[ConditionalRegionFact, ...]


def conditional_region_id(node_id: str, kind: ConditionalRegionKind) -> str:
    digest = hashlib.sha256(f"{node_id}\x1f{kind.value}".encode("utf-8")).hexdigest()
    return "conditional-region-" + digest[:20]


__all__ = [
    "CONDITIONAL_REGION_KEY_DOMAIN",
    "CONDITIONAL_REGION_LOWERING_SHAPE",
    "CONDITIONAL_REGION_OBLIGATIONS",
    "CONDITIONAL_REGION_PROVENANCE_EVIDENCE",
    "CONDITIONAL_REGION_TABLE_DEPENDENCIES",
    "CONDITIONAL_REGION_TABLE_ID",
    "ConditionalEvaluationMode",
    "ConditionalGuardPolarity",
    "ConditionalOperandPlacementFact",
    "ConditionalRegionAnalysis",
    "ConditionalRegionAnalysisCanceled",
    "ConditionalRegionAnalysisError",
    "ConditionalRegionValidationCanceled",
    "ConditionalRegionFact",
    "ConditionalRegionKind",
    "conditional_region_id",
]
