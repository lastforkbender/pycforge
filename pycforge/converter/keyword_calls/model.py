"""Immutable evidence for exact direct keyword-call binding.

Phase 14C does not add a Python runtime binder.  These records prove at
conversion time that an already-resolved source function receives every
argument exactly once.  Argument *evaluation* order and formal-parameter
order are represented separately because conflating them would change Python
semantics when keyword values contain nested calls.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


KEYWORD_CALL_FACT_SCHEMA = "fact-table/0.14.2"
KEYWORD_CALL_TABLE_ID = "keyword-call-binding-facts"
KEYWORD_CALL_KEY_DOMAIN = "keyword-call-node-id"
KEYWORD_CALL_LOWERING_SHAPE = (
    "source-order-temporaries-formal-order-references-v1"
)
KEYWORD_CALL_RULE_ID = "phase14.keyword_call.exact_binding"
KEYWORD_CALL_RULE_VERSION = "0.14.2"
KEYWORD_CALL_TABLE_DEPENDENCIES = (
    "binding-facts",
    "function-signature-facts",
    "value-category-facts",
    "call-target-facts",
    "evaluation-order-facts",
)
KEYWORD_CALL_PROVENANCE_EVIDENCE = (
    "direct-source-target",
    "exact-explicit-keyword-names",
    "complete-parameter-coverage",
    "source-order-evaluation",
    "formal-order-reference-permutation",
    "single-evaluation",
)
CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE = "PYC2911"
CUMULATIVE_KEYWORD_TARGET_REASON = (
    "Keyword-call target is outside the eligible direct source-function profile"
)
KEYWORD_CALL_OBLIGATIONS = (
    "direct-source-target-resolved-once",
    "explicit-keywords-only-no-unpacking",
    "positional-prefix-bound-in-order",
    "keyword-names-bound-to-positional-or-keyword-parameters",
    "parameter-coverage-exact",
    "argument-representations-compatible-after-binding",
    "source-arguments-evaluated-left-to-right-once",
    "argument-temporaries-reordered-only-after-evaluation",
    "c-call-arguments-in-formal-order",
    "parameter-ownership-boundary-explicit",
    "runtime-binding-failure-absent",
    "allocation-and-cleanup-absent",
    "structured-c-ir-only",
    "source-provenance-anchored",
    "cancellation-safe-points-honored",
    "target-contract-exact",
)


class KeywordCallAnalysisCanceled(Exception):
    """Raised when cooperative cancellation retires keyword-call analysis."""


class KeywordCallValidationCanceled(Exception):
    """Raised when independent keyword-call reconstruction is canceled."""


class KeywordCallAnalysisError(Exception):
    """A bounded source-facing failure that cannot be serialized as a fact."""

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
class KeywordArgumentBindingFact:
    """Binding of one source-order argument value to at most one parameter."""

    source_argument_node_id: str
    keyword_node_id: str | None
    keyword_name: str | None
    source_ordinal: int
    parameter_node_id: str | None
    parameter_name: str | None
    parameter_ordinal: int | None
    category: str
    expected_category: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_argument_node_id": self.source_argument_node_id,
            "keyword_node_id": self.keyword_node_id,
            "keyword_name": self.keyword_name,
            "source_ordinal": self.source_ordinal,
            "parameter_node_id": self.parameter_node_id,
            "parameter_name": self.parameter_name,
            "parameter_ordinal": self.parameter_ordinal,
            "category": self.category,
            "expected_category": self.expected_category,
        }


@dataclass(frozen=True, slots=True)
class KeywordCallRejection:
    call_node_id: str
    diagnostic_code: str
    reason: str
    rejection_node_id: str
    source_span: dict[str, object] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_node_id": self.call_node_id,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
            "rejection_node_id": self.rejection_node_id,
            "source_span": self.source_span,
        }


@dataclass(frozen=True, slots=True)
class KeywordCallBindingFact:
    binding_id: str
    call_node_id: str
    callee_node_id: str
    target_function_node_id: str
    target_binding_id: str
    target_name: str
    positional_only_parameter_count: int
    parameter_node_ids: tuple[str, ...]
    parameter_names: tuple[str, ...]
    parameter_categories: tuple[str, ...]
    positional_argument_node_ids: tuple[str, ...]
    keyword_node_ids: tuple[str, ...]
    keyword_names: tuple[str | None, ...]
    keyword_value_node_ids: tuple[str, ...]
    argument_bindings: tuple[KeywordArgumentBindingFact, ...]
    source_argument_node_ids: tuple[str, ...]
    source_argument_categories: tuple[str, ...]
    source_to_parameter_ordinals: tuple[int | None, ...]
    parameter_argument_node_ids: tuple[str | None, ...]
    parameter_to_source_ordinals: tuple[int | None, ...]
    evaluation_order: tuple[str, ...]
    arguments_evaluated_once: bool
    parameter_coverage_exact: bool
    lowering_shape: str
    allocation_model: str
    cleanup_model: str
    runtime_binding_failure: str
    supported: bool
    diagnostic_code: str | None
    reason: str | None
    rejection_node_id: str | None

    @property
    def rule_facts(self) -> tuple[str, ...]:
        return (
            f"keyword-call-binding:{self.binding_id}",
            f"keyword-call:{self.call_node_id}",
            f"keyword-call-target:{self.target_binding_id}",
            f"keyword-source-argument-count:{len(self.source_argument_node_ids)}",
            f"keyword-parameter-count:{len(self.parameter_node_ids)}",
            f"keyword-call-lowering-shape:{self.lowering_shape}",
        )

    @property
    def explanation_tokens(self) -> tuple[str, ...]:
        return (
            "keyword-call-binding",
            self.target_name,
            "source-order-arguments",
            str(len(self.source_argument_node_ids)),
            "formal-order-parameters",
            str(len(self.parameter_node_ids)),
            "lowered-as",
            self.lowering_shape,
        )

    @property
    def provenance_node_ids(self) -> tuple[str, ...]:
        values = (
            self.call_node_id,
            self.callee_node_id,
            self.target_function_node_id,
            *self.parameter_node_ids,
            *self.positional_argument_node_ids,
            *self.keyword_node_ids,
            *self.keyword_value_node_ids,
        )
        return tuple(dict.fromkeys(values))

    @property
    def call_target_overrides(self) -> dict[str, Any]:
        """Fields used to replace the predecessor's keyword rejection fact."""

        return {
            "argument_node_ids": self.source_argument_node_ids,
            "argument_categories": self.source_argument_categories,
            "evaluation_order": self.evaluation_order,
            "arguments_evaluated_once": self.arguments_evaluated_once,
            "resolution": (
                "understood-source-function"
                if self.supported
                else "ineligible-source-function"
            ),
            "supported": self.supported,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "call_node_id": self.call_node_id,
            "callee_node_id": self.callee_node_id,
            "target_function_node_id": self.target_function_node_id,
            "target_binding_id": self.target_binding_id,
            "target_name": self.target_name,
            "positional_only_parameter_count": self.positional_only_parameter_count,
            "parameter_node_ids": list(self.parameter_node_ids),
            "parameter_names": list(self.parameter_names),
            "parameter_categories": list(self.parameter_categories),
            "positional_argument_node_ids": list(self.positional_argument_node_ids),
            "keyword_node_ids": list(self.keyword_node_ids),
            "keyword_names": list(self.keyword_names),
            "keyword_value_node_ids": list(self.keyword_value_node_ids),
            "argument_bindings": [item.to_dict() for item in self.argument_bindings],
            "source_argument_node_ids": list(self.source_argument_node_ids),
            "source_argument_categories": list(self.source_argument_categories),
            "source_to_parameter_ordinals": list(self.source_to_parameter_ordinals),
            "parameter_argument_node_ids": list(self.parameter_argument_node_ids),
            "parameter_to_source_ordinals": list(self.parameter_to_source_ordinals),
            "evaluation_order": list(self.evaluation_order),
            "arguments_evaluated_once": self.arguments_evaluated_once,
            "parameter_coverage_exact": self.parameter_coverage_exact,
            "lowering_shape": self.lowering_shape,
            "allocation_model": self.allocation_model,
            "cleanup_model": self.cleanup_model,
            "runtime_binding_failure": self.runtime_binding_failure,
            "supported": self.supported,
            "diagnostic_code": self.diagnostic_code,
            "reason": self.reason,
            "rejection_node_id": self.rejection_node_id,
        }


@dataclass(frozen=True, slots=True)
class KeywordCallAnalysis:
    facts: tuple[KeywordCallBindingFact, ...]
    rejections: tuple[KeywordCallRejection, ...]

    @property
    def supported_call_node_ids(self) -> frozenset[str]:
        return frozenset(item.call_node_id for item in self.facts if item.supported)

    @property
    def fact_by_call_node_id(self) -> dict[str, KeywordCallBindingFact]:
        return {item.call_node_id: item for item in self.facts}


def keyword_call_binding_id(call_node_id: str, target_binding_id: str) -> str:
    digest = hashlib.sha256(
        f"{call_node_id}\x1f{target_binding_id}\x1fexact-keyword-binding-v1".encode(
            "utf-8"
        )
    ).hexdigest()
    return "keyword-call-binding-" + digest[:20]


__all__ = [
    "CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE",
    "CUMULATIVE_KEYWORD_TARGET_REASON",
    "KEYWORD_CALL_FACT_SCHEMA",
    "KEYWORD_CALL_KEY_DOMAIN",
    "KEYWORD_CALL_LOWERING_SHAPE",
    "KEYWORD_CALL_OBLIGATIONS",
    "KEYWORD_CALL_PROVENANCE_EVIDENCE",
    "KEYWORD_CALL_RULE_ID",
    "KEYWORD_CALL_RULE_VERSION",
    "KEYWORD_CALL_TABLE_DEPENDENCIES",
    "KEYWORD_CALL_TABLE_ID",
    "KeywordArgumentBindingFact",
    "KeywordCallAnalysis",
    "KeywordCallAnalysisCanceled",
    "KeywordCallAnalysisError",
    "KeywordCallBindingFact",
    "KeywordCallRejection",
    "KeywordCallValidationCanceled",
    "keyword_call_binding_id",
]
