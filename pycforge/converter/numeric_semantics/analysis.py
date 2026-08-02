"""Closed proof pass for helper-backed integer floor arithmetic."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.ir.python_ir import python_ir_reference_ids
from pycforge.converter.support_templates.factories import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
)

from .model import (
    BoundedNumericAnalysis,
    FloorArithmeticKind,
    NumericAnalysisCanceled,
    NumericAnalysisError,
    NumericOperationFact,
)


_PROHIBITED_CONTEXTS = frozenset(
    {
        "AsyncFor",
        "AsyncFunctionDef",
        "AsyncWith",
        "Await",
        "DictComp",
        "FormattedValue",
        "GeneratorExp",
        "JoinedStr",
        "Lambda",
        "ListComp",
        "Match",
        "NamedExpr",
        "SetComp",
        "Try",
        "TryStar",
        "With",
        "Yield",
        "YieldFrom",
        "comprehension",
    }
)
_MAX_DIRECT_MAGNITUDE = 2**63 - 1


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return prefix + digest


class BoundedNumericAnalyzer:
    """Prove every ``//`` and ``%`` occurrence in an active Phase 14 plan."""

    def __init__(
        self,
        module: dict[str, Any],
        *,
        categories: Mapping[str, ValueCategory],
        function_records: Mapping[str, Mapping[str, Any]],
        supported_call_node_ids: frozenset[str],
        supported_container_access_node_ids: frozenset[str],
        supported_record_access_node_ids: frozenset[str],
        rejected_expression_diagnostics: Mapping[str, tuple[str, str]],
        cancellation: Any,
    ) -> None:
        self.module = module
        self.nodes = {node["node_id"]: node for node in module["nodes"]}
        self.ordinals = {
            node["node_id"]: ordinal for ordinal, node in enumerate(module["nodes"])
        }
        self.categories = categories
        self.function_records = function_records
        self.supported_call_node_ids = supported_call_node_ids
        self.supported_container_access_node_ids = supported_container_access_node_ids
        self.supported_record_access_node_ids = supported_record_access_node_ids
        self.rejected_expression_diagnostics = rejected_expression_diagnostics
        self.cancellation = cancellation
        self._approved_numeric_node_ids: set[str] = set()
        self._integer_expression_cache: dict[str, bool] = {}
        self.parents: dict[str, list[tuple[str, str]]] = {}
        for parent in module["nodes"]:
            self._check_cancellation()
            for field_name, value in parent.get("fields", {}).items():
                for child_id in python_ir_reference_ids(
                    parent["kind"], field_name, value, self.nodes
                ):
                    self.parents.setdefault(child_id, []).append(
                        (parent["node_id"], field_name)
                    )

    def analyze(self) -> BoundedNumericAnalysis:
        operations: list[NumericOperationFact] = []
        candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for node in self.module["nodes"]:
            self._check_cancellation()
            if node.get("kind") != "BinOp":
                continue
            operator = self.nodes.get(node.get("fields", {}).get("op"), {})
            if operator.get("kind") not in {"FloorDiv", "Mod"}:
                continue
            candidates.append((node, operator))
        candidates.sort(
            key=lambda item: (-self._depth(item[0]["node_id"]), self.ordinals[item[0]["node_id"]])
        )
        for node, operator in candidates:
            operation = self._operation(node, operator)
            operations.append(operation)
            self._approved_numeric_node_ids.add(node["node_id"])
        return BoundedNumericAnalysis(tuple(operations))

    def _operation(
        self,
        node: dict[str, Any],
        operator: dict[str, Any],
    ) -> NumericOperationFact:
        node_id = node["node_id"]
        left_id = node.get("fields", {}).get("left")
        right_id = node.get("fields", {}).get("right")
        function_node_id = self._approved_context(node_id)
        if (
            not isinstance(left_id, str)
            or left_id not in self.nodes
            or not isinstance(right_id, str)
            or right_id not in self.nodes
            or function_node_id is None
        ):
            self._reject(
                "PYC3701",
                "Integer floor arithmetic is supported only in a direct expression context of an understood top-level function",
                node,
            )

        rejection = self._first_rejected_expression(left_id)
        if rejection is not None:
            rejected_node_id, code, reason = rejection
            self._reject(code, reason, self.nodes[rejected_node_id])

        left_category = self.categories.get(left_id, ValueCategory.UNKNOWN)
        right_category = self.categories.get(right_id, ValueCategory.UNKNOWN)
        result_category = self.categories.get(node_id, ValueCategory.UNKNOWN)
        if (
            left_category is not ValueCategory.INTEGER
            or right_category is not ValueCategory.INTEGER
            or result_category is not ValueCategory.INTEGER
        ):
            self._reject(
                "PYC3701",
                "Integer // and % require exact integer-like operands and an integer-like result; bool and mixed categories are excluded",
                node,
            )
        if not self._approved_integer_expression(left_id):
            self._reject(
                "PYC3701",
                "The left operand of integer // or % must be an already supported scalar integer expression",
                self.nodes[left_id],
            )

        divisor = self._signed_literal(self.nodes[right_id])
        if divisor is None:
            self._reject(
                "PYC3702",
                "The divisor of integer // or % must be a directly recognized, lowerable signed int64 literal",
                self.nodes[right_id],
            )
        divisor_value, literal_ids, literal_shape = divisor
        if divisor_value in {0, -1}:
            reason = (
                "A zero divisor is excluded because Python would raise ZeroDivisionError"
                if divisor_value == 0
                else "A divisor of -1 is excluded by the frozen int64 helper precondition"
            )
            self._reject("PYC3702", reason, self.nodes[right_id])

        is_division = operator["kind"] == "FloorDiv"
        kind = (
            FloorArithmeticKind.FLOOR_DIVIDE
            if is_division
            else FloorArithmeticKind.FLOOR_MODULO
        )
        helper = FLOOR_DIV_REFERENCE if is_division else FLOOR_MOD_REFERENCE
        owner = self.function_records[function_node_id]
        module_id = owner.get("module_id")
        document_id = owner.get("document_id")
        logical_name = owner.get("logical_name")
        if not all(
            isinstance(item, str) and item
            for item in (module_id, document_id, logical_name)
        ):
            self._reject(
                "PYC3701",
                "Integer floor arithmetic lacks exact module, document, or logical-source ownership",
                node,
            )
        return NumericOperationFact(
            operation_id=_stable_id("numeric-op-", node_id, kind.value),
            binop_node_id=node_id,
            function_node_id=function_node_id,
            module_id=module_id,
            document_id=document_id,
            logical_name=logical_name,
            operator_node_id=operator["node_id"],
            operator_kind=kind,
            left_node_id=left_id,
            right_node_id=right_id,
            left_category=left_category.value,
            right_category=right_category.value,
            result_category=result_category.value,
            left_c_type="int64_t",
            right_c_type="int64_t",
            result_c_type="int64_t",
            divisor_value=divisor_value,
            divisor_literal_node_ids=literal_ids,
            literal_shape=literal_shape,
            divisor_in_admitted_domain=True,
            divisor_nonzero_proved=True,
            negative_one_divisor_excluded=True,
            minimum_signed_divisor_excluded=True,
            helper_requirement=helper.canonical,
            evaluation_order=(left_id, right_id),
            operands_evaluated_once=True,
            c_type="int64_t",
            failure_policy="caller-proved-no-runtime-failure-channel",
            support_state="SupportedWithHelper",
            parameter_ownership="scalar-values-by-value",
            result_ownership="scalar-value-by-value",
            allocation_model="none",
            cleanup_model="none",
            runtime_failure_channel="none",
            target_contract="c11-portable-fixed-v1",
        )

    def _approved_integer_expression(
        self,
        node_id: str,
        active: frozenset[str] = frozenset(),
    ) -> bool:
        self._check_cancellation()
        if node_id in self._integer_expression_cache:
            return self._integer_expression_cache[node_id]
        if node_id in active or self.categories.get(node_id) is not ValueCategory.INTEGER:
            return False
        node = self.nodes[node_id]
        kind = node["kind"]
        fields = node.get("fields", {})
        next_active = active | {node_id}
        accepted = False
        if kind == "Name":
            accepted = True
        elif kind == "Constant":
            value = fields.get("value")
            accepted = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= _MAX_DIRECT_MAGNITUDE
            )
        elif kind == "UnaryOp":
            operator = self.nodes.get(fields.get("op"), {})
            operand_id = fields.get("operand")
            accepted = (
                operator.get("kind") in {"UAdd", "USub"}
                and isinstance(operand_id, str)
                and operand_id in self.nodes
                and self._approved_integer_expression(operand_id, next_active)
            )
        elif kind == "BinOp":
            operator = self.nodes.get(fields.get("op"), {})
            left_id = fields.get("left")
            right_id = fields.get("right")
            if operator.get("kind") in {"FloorDiv", "Mod"}:
                accepted = node_id in self._approved_numeric_node_ids
            else:
                accepted = (
                    operator.get("kind") in {"Add", "Sub", "Mult"}
                    and isinstance(left_id, str)
                    and isinstance(right_id, str)
                    and left_id in self.nodes
                    and right_id in self.nodes
                    and self._approved_integer_expression(left_id, next_active)
                    and self._approved_integer_expression(right_id, next_active)
                )
        elif kind == "Call":
            accepted = node_id in self.supported_call_node_ids
        elif kind == "Subscript":
            accepted = node_id in self.supported_container_access_node_ids
        elif kind == "Attribute":
            accepted = node_id in self.supported_record_access_node_ids
        self._integer_expression_cache[node_id] = accepted
        return accepted

    def _first_rejected_expression(
        self,
        node_id: str,
        active: frozenset[str] = frozenset(),
    ) -> tuple[str, str, str] | None:
        """Preserve an established nested call/container rejection diagnostic."""
        self._check_cancellation()
        if node_id in active:
            return None
        diagnostic = self.rejected_expression_diagnostics.get(node_id)
        if diagnostic is not None:
            return node_id, diagnostic[0], diagnostic[1]
        node = self.nodes[node_id]
        children: list[str] = []
        for field_name, value in sorted(node.get("fields", {}).items()):
            children.extend(
                python_ir_reference_ids(node["kind"], field_name, value, self.nodes)
            )
        for child_id in sorted(
            set(children),
            key=lambda item: (self.ordinals.get(item, 2**63 - 1), item),
        ):
            rejection = self._first_rejected_expression(
                child_id,
                active | {node_id},
            )
            if rejection is not None:
                return rejection
        return None

    def _depth(self, node_id: str) -> int:
        depth = 0
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            candidates = self.parents.get(current, ())
            if not candidates:
                break
            current = min(
                candidates,
                key=lambda item: (self.ordinals.get(item[0], 2**63 - 1), item[1]),
            )[0]
            depth += 1
        return depth

    def _approved_context(self, node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            self._check_cancellation()
            seen.add(current)
            candidates = self.parents.get(current, ())
            if not candidates:
                return None
            parent_id, field_name = min(
                candidates,
                key=lambda item: (self.ordinals.get(item[0], 2**63 - 1), item[1]),
            )
            parent = self.nodes[parent_id]
            if parent["kind"] == "FunctionDef":
                return (
                    parent_id
                    if field_name == "body" and parent_id in self.function_records
                    else None
                )
            if parent["kind"] in _PROHIBITED_CONTEXTS or parent["kind"] == "ClassDef":
                return None
            current = parent_id
        return None

    def _signed_literal(
        self,
        node: dict[str, Any],
    ) -> tuple[int, tuple[str, ...], str] | None:
        """Recognize only source shapes the existing int64 literal lowerer closes.

        ``-2**63`` has a positive Constant child outside that lowerer's signed
        literal domain, so this mini-phase deliberately rejects it rather than
        smuggling an unrepresentable child through a helper call.
        """

        if node.get("kind") == "Constant":
            value = node.get("fields", {}).get("value")
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= _MAX_DIRECT_MAGNITUDE
            ):
                return value, (node["node_id"],), "constant"
            return None
        if node.get("kind") != "UnaryOp":
            return None
        operator = self.nodes.get(node.get("fields", {}).get("op"), {})
        operand = self.nodes.get(node.get("fields", {}).get("operand"), {})
        value = operand.get("fields", {}).get("value")
        if (
            operator.get("kind") not in {"UAdd", "USub"}
            or operand.get("kind") != "Constant"
            or not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= _MAX_DIRECT_MAGNITUDE
        ):
            return None
        signed = -value if operator["kind"] == "USub" else value
        shape = "unary-minus" if operator["kind"] == "USub" else "unary-plus"
        return signed, (node["node_id"], operator["node_id"], operand["node_id"]), shape

    def _reject(
        self,
        code: str,
        message: str,
        node: dict[str, Any],
    ) -> None:
        raise NumericAnalysisError(
            code,
            message,
            node["node_id"],
            node.get("provenance", {}).get("source_span"),
        )

    def _check_cancellation(self) -> None:
        if bool(getattr(self.cancellation, "is_canceled", False)):
            raise NumericAnalysisCanceled


__all__ = ["BoundedNumericAnalyzer"]
