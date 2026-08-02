"""Structured C IR lowering for proved conditional temporary regions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from pycforge.converter.ir.c_ir import (
    CAssignmentStatement,
    CBinaryExpr,
    CBinaryOp,
    CBlock,
    CBooleanLiteral,
    CFloatLiteral,
    CIdentifierRef,
    CIfStatement,
    CIntegerLiteral,
    CProvenance,
    CType,
    CUnaryExpr,
    CUnaryOp,
)

from .model import (
    CONDITIONAL_REGION_LOWERING_SHAPE,
    ConditionalGuardPolarity,
    ConditionalRegionKind,
)


def _sid(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return prefix + digest


_COMPARISON_OPERATORS = {
    "Eq": CBinaryOp.EQUAL,
    "NotEq": CBinaryOp.NOT_EQUAL,
    "Lt": CBinaryOp.LESS,
    "LtE": CBinaryOp.LESS_EQUAL,
    "Gt": CBinaryOp.GREATER,
    "GtE": CBinaryOp.GREATER_EQUAL,
}


@dataclass(slots=True)
class ConditionalRegionLoweringServices:
    nodes: dict[str, dict[str, Any]]
    categories: dict[str, str]
    regions: dict[str, dict[str, Any]]
    expression: Callable[[dict[str, Any]], tuple[tuple[Any, ...], Any]]
    temporary: Callable[..., tuple[Any, CIdentifierRef]]
    category_type: Callable[[str], CType]
    provenance: Callable[..., CProvenance]
    synthetic_provenance: Callable[..., CProvenance]
    reject: Callable[..., Any]
    check_cancellation: Callable[[], None]


class ConditionalRegionCIRLowerer:
    """Lower legacy-direct or independently proved guarded expression forms."""

    def __init__(self, services: ConditionalRegionLoweringServices) -> None:
        self.services = services

    def boolean(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        fact = self.services.regions.get(node["node_id"])
        if fact is None:
            return self._legacy_boolean(node)
        self._require_fact(node, fact, ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT)
        return self._guarded_boolean(node, fact)

    def comparison(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        fact = self.services.regions.get(node["node_id"])
        if fact is None:
            return self._legacy_comparison(node)
        self._require_fact(node, fact, ConditionalRegionKind.CHAINED_COMPARISON)
        return self._guarded_comparison(node, fact)

    def _legacy_boolean(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        values = node["fields"].get("values", [])
        operator_kind = s.nodes[node["fields"]["op"]]["kind"]
        operator = (
            CBinaryOp.LOGICAL_AND
            if operator_kind == "And"
            else CBinaryOp.LOGICAL_OR
            if operator_kind == "Or"
            else None
        )
        if (
            operator is None
            or len(values) < 2
            or any(s.categories.get(item) != "boolean-like" for item in values)
        ):
            s.reject(
                "PYC2826",
                "Only Boolean-represented and/or expressions are supported",
                node,
            )
        lowered = [s.expression(s.nodes[item]) for item in values]
        if any(prelude for prelude, _ in lowered):
            s.reject(
                "PYC2950",
                "Calls inside short-circuit Boolean expressions require a conditional-temporary proof",
                node,
            )
        result = lowered[0][1]
        provenance = s.provenance(node)
        for child_id, (_, child) in zip(values[1:], lowered[1:]):
            result = CBinaryExpr(
                _sid("c-boolop-", node["node_id"], child_id),
                operator,
                result,
                child,
                provenance,
            )
        return (), result

    def _guarded_boolean(
        self,
        node: dict[str, Any],
        fact: dict[str, Any],
    ) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        values = tuple(fact["operand_node_ids"])
        operator_kind = fact["operator_kinds"][0]
        polarity = (
            ConditionalGuardPolarity.WHEN_RESULT_TRUE.value
            if operator_kind == "And"
            else ConditionalGuardPolarity.WHEN_RESULT_FALSE.value
        )
        s.check_cancellation()
        first_prelude, first_expression = s.expression(s.nodes[values[0]])
        result_declaration, result_template = s.temporary(
            "bool_region_result",
            node,
            0,
            CType("bool"),
            first_expression,
            (values[0], node["node_id"]),
        )
        prelude: list[Any] = [*first_prelude, result_declaration]
        result_binding = result_template.binding_id
        placements = tuple(fact["placements"])
        for ordinal, operand_id in enumerate(values[1:], 1):
            s.check_cancellation()
            placement = placements[ordinal]
            if (
                placement.get("evaluation_mode") != "guarded"
                or placement.get("guard_polarity") != polarity
                or placement.get("guard_after_operand_ordinal") != ordinal - 1
            ):
                s.reject("PYC2950", "Boolean conditional placement fact is inconsistent", node)
            operand_prelude, operand_expression = s.expression(s.nodes[operand_id])
            target = self._reference(
                result_binding,
                "c-bool-region-target-",
                node,
                ordinal,
                (operand_id, node["node_id"]),
            )
            assignment = CAssignmentStatement(
                _sid("c-bool-region-assign-", node["node_id"], str(ordinal)),
                target,
                operand_expression,
                s.synthetic_provenance((operand_id, node["node_id"]), node["node_id"]),
            )
            condition_reference = self._reference(
                result_binding,
                "c-bool-region-guard-ref-",
                node,
                ordinal,
                (node["node_id"], operand_id),
            )
            condition = (
                condition_reference
                if polarity == ConditionalGuardPolarity.WHEN_RESULT_TRUE.value
                else CUnaryExpr(
                    _sid("c-bool-region-not-", node["node_id"], str(ordinal)),
                    CUnaryOp.LOGICAL_NOT,
                    condition_reference,
                    s.synthetic_provenance(
                        (node["node_id"], operand_id), node["node_id"]
                    ),
                )
            )
            block = CBlock(
                _sid("c-bool-region-block-", node["node_id"], str(ordinal)),
                tuple(operand_prelude) + (assignment,),
                s.synthetic_provenance((operand_id, node["node_id"]), node["node_id"]),
            )
            prelude.append(
                CIfStatement(
                    _sid("c-bool-region-if-", node["node_id"], str(ordinal)),
                    condition,
                    block,
                    None,
                    s.synthetic_provenance(
                        (node["node_id"], operand_id), node["node_id"]
                    ),
                )
            )
        s.check_cancellation()
        return tuple(prelude), self._reference(
            result_binding,
            "c-bool-region-result-ref-",
            node,
            len(values),
            (node["node_id"],),
        )

    def _legacy_comparison(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        fields = node["fields"]
        operand_ids = [fields["left"]] + list(fields.get("comparators", []))
        operator_ids = list(fields.get("ops", []))
        if not operator_ids or len(operand_ids) != len(operator_ids) + 1:
            s.reject("PYC2829", "Malformed comparison", node)
        prelude: list[Any] = []
        operands: list[Any] = []
        chained = len(operator_ids) > 1
        for ordinal, operand_id in enumerate(operand_ids):
            expression_prelude, expression = s.expression(s.nodes[operand_id])
            if chained and ordinal >= 2 and (
                expression_prelude
                or s.nodes[operand_id]["kind"] not in {"Name", "Constant"}
            ):
                s.reject(
                    "PYC2951",
                    "A conditionally evaluated chained-comparison operand must have a conditional-temporary proof",
                    s.nodes[operand_id],
                )
            prelude.extend(expression_prelude)
            category = s.categories.get(operand_id, "unknown")
            if category not in {"integer-like", "floating-like", "boolean-like"}:
                s.reject(
                    "PYC2860",
                    f"Comparison operand has unsupported representation: {category}",
                    s.nodes[operand_id],
                )
            if chained:
                declaration, reference = s.temporary(
                    "cmp",
                    node,
                    ordinal,
                    s.category_type(category),
                    expression,
                    (operand_id, node["node_id"]),
                )
                prelude.append(declaration)
                operands.append(reference)
            else:
                operands.append(expression)
        pieces: list[Any] = []
        for ordinal, operator_id in enumerate(operator_ids):
            operator_kind = s.nodes[operator_id]["kind"]
            if operator_kind not in _COMPARISON_OPERATORS:
                s.reject(
                    "PYC2828", f"Unsupported comparison operator: {operator_kind}", node
                )
            left, right = operands[ordinal], operands[ordinal + 1]
            if chained:
                left = CIdentifierRef(
                    _sid("c-cmp-ref-l-", node["node_id"], str(ordinal)),
                    left.binding_id,
                    s.synthetic_provenance(
                        (operand_ids[ordinal], node["node_id"]), node["node_id"]
                    ),
                )
                right = CIdentifierRef(
                    _sid("c-cmp-ref-r-", node["node_id"], str(ordinal)),
                    right.binding_id,
                    s.synthetic_provenance(
                        (operand_ids[ordinal + 1], node["node_id"]), node["node_id"]
                    ),
                )
            pieces.append(
                CBinaryExpr(
                    _sid("c-cmp-", node["node_id"], str(ordinal)),
                    _COMPARISON_OPERATORS[operator_kind],
                    left,
                    right,
                    s.provenance(node),
                )
            )
        result = pieces[0]
        for ordinal, piece in enumerate(pieces[1:], 1):
            result = CBinaryExpr(
                _sid("c-chain-", node["node_id"], str(ordinal)),
                CBinaryOp.LOGICAL_AND,
                result,
                piece,
                s.provenance(node),
            )
        return tuple(prelude), result

    def _guarded_comparison(
        self,
        node: dict[str, Any],
        fact: dict[str, Any],
    ) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        operand_ids = tuple(fact["operand_node_ids"])
        operator_ids = tuple(fact["operator_node_ids"])
        operator_kinds = tuple(fact["operator_kinds"])
        prelude: list[Any] = []
        operand_bindings: list[str] = []

        for ordinal, operand_id in enumerate(operand_ids[:2]):
            s.check_cancellation()
            expression_prelude, expression = s.expression(s.nodes[operand_id])
            prelude.extend(expression_prelude)
            category = s.categories.get(operand_id, "unknown")
            declaration, reference = s.temporary(
                "cmp",
                node,
                ordinal,
                s.category_type(category),
                expression,
                (operand_id, node["node_id"]),
            )
            prelude.append(declaration)
            operand_bindings.append(reference.binding_id)

        for ordinal, operand_id in enumerate(operand_ids[2:], 2):
            s.check_cancellation()
            category = s.categories.get(operand_id, "unknown")
            declaration, reference = s.temporary(
                "cmp",
                node,
                ordinal,
                s.category_type(category),
                self._zero(node, operand_id, ordinal, category),
                (operand_id, node["node_id"]),
            )
            prelude.append(declaration)
            operand_bindings.append(reference.binding_id)

        first_comparison = self._comparison_expression(
            node,
            0,
            operator_kinds[0],
            operand_ids,
            operand_bindings,
        )
        result_declaration, result_template = s.temporary(
            "comparison_region_result",
            node,
            0,
            CType("bool"),
            first_comparison,
            (operand_ids[0], operand_ids[1], node["node_id"]),
        )
        prelude.append(result_declaration)
        result_binding = result_template.binding_id
        placements = tuple(fact["placements"])

        for ordinal, operand_id in enumerate(operand_ids[2:], 2):
            s.check_cancellation()
            placement = placements[ordinal]
            if (
                placement.get("evaluation_mode") != "guarded"
                or placement.get("guard_polarity")
                != ConditionalGuardPolarity.WHEN_RESULT_TRUE.value
                or placement.get("guard_after_operand_ordinal") != ordinal - 1
            ):
                s.reject(
                    "PYC2951", "Chained-comparison placement fact is inconsistent", node
                )
            expression_prelude, expression = s.expression(s.nodes[operand_id])
            operand_assignment = CAssignmentStatement(
                _sid("c-chain-region-value-assign-", node["node_id"], str(ordinal)),
                self._reference(
                    operand_bindings[ordinal],
                    "c-chain-region-value-target-",
                    node,
                    ordinal,
                    (operand_id, node["node_id"]),
                ),
                expression,
                s.synthetic_provenance((operand_id, node["node_id"]), node["node_id"]),
            )
            comparison = self._comparison_expression(
                node,
                ordinal - 1,
                operator_kinds[ordinal - 1],
                operand_ids,
                operand_bindings,
            )
            result_assignment = CAssignmentStatement(
                _sid("c-chain-region-result-assign-", node["node_id"], str(ordinal)),
                self._reference(
                    result_binding,
                    "c-chain-region-result-target-",
                    node,
                    ordinal,
                    (node["node_id"], operand_id),
                ),
                comparison,
                s.synthetic_provenance((operand_id, node["node_id"]), node["node_id"]),
            )
            block = CBlock(
                _sid("c-chain-region-block-", node["node_id"], str(ordinal)),
                tuple(expression_prelude) + (operand_assignment, result_assignment),
                s.synthetic_provenance((operand_id, node["node_id"]), node["node_id"]),
            )
            prelude.append(
                CIfStatement(
                    _sid("c-chain-region-if-", node["node_id"], str(ordinal)),
                    self._reference(
                        result_binding,
                        "c-chain-region-guard-ref-",
                        node,
                        ordinal,
                        (node["node_id"], operand_id),
                    ),
                    block,
                    None,
                    s.synthetic_provenance(
                        (node["node_id"], operand_id), node["node_id"]
                    ),
                )
            )
        s.check_cancellation()
        return tuple(prelude), self._reference(
            result_binding,
            "c-chain-region-final-ref-",
            node,
            len(operand_ids),
            (node["node_id"],),
        )

    def _comparison_expression(
        self,
        node: dict[str, Any],
        comparison_ordinal: int,
        operator_kind: str,
        operand_ids: tuple[str, ...],
        operand_bindings: list[str],
    ) -> CBinaryExpr:
        s = self.services
        if operator_kind not in _COMPARISON_OPERATORS:
            s.reject("PYC2828", f"Unsupported comparison operator: {operator_kind}", node)
        left_ordinal = comparison_ordinal
        right_ordinal = comparison_ordinal + 1
        left = self._reference(
            operand_bindings[left_ordinal],
            "c-chain-region-left-ref-",
            node,
            comparison_ordinal,
            (operand_ids[left_ordinal], node["node_id"]),
        )
        right = self._reference(
            operand_bindings[right_ordinal],
            "c-chain-region-right-ref-",
            node,
            comparison_ordinal,
            (operand_ids[right_ordinal], node["node_id"]),
        )
        return CBinaryExpr(
            _sid("c-chain-region-compare-", node["node_id"], str(comparison_ordinal)),
            _COMPARISON_OPERATORS[operator_kind],
            left,
            right,
            s.provenance(node),
        )

    def _zero(
        self,
        owner: dict[str, Any],
        operand_id: str,
        ordinal: int,
        category: str,
    ) -> Any:
        provenance = self.services.synthetic_provenance(
            (operand_id, owner["node_id"]), owner["node_id"]
        )
        if category == "integer-like":
            return CIntegerLiteral(
                _sid("c-chain-region-zero-int-", owner["node_id"], str(ordinal)),
                0,
                "LL",
                provenance,
            )
        if category == "floating-like":
            return CFloatLiteral(
                _sid("c-chain-region-zero-float-", owner["node_id"], str(ordinal)),
                0.0,
                provenance,
            )
        if category == "boolean-like":
            return CBooleanLiteral(
                _sid("c-chain-region-zero-bool-", owner["node_id"], str(ordinal)),
                False,
                provenance,
            )
        self.services.reject(
            "PYC2860",
            f"Comparison operand has unsupported representation: {category}",
            self.services.nodes[operand_id],
        )

    def _reference(
        self,
        binding_id: str,
        prefix: str,
        owner: dict[str, Any],
        ordinal: int,
        origin_ids: tuple[str, ...],
    ) -> CIdentifierRef:
        return CIdentifierRef(
            _sid(prefix, owner["node_id"], str(ordinal), *origin_ids),
            binding_id,
            self.services.synthetic_provenance(origin_ids, owner["node_id"]),
        )

    def _require_fact(
        self,
        node: dict[str, Any],
        fact: dict[str, Any],
        expected_kind: ConditionalRegionKind,
    ) -> None:
        fields = node.get("fields", {})
        expected_operands = (
            tuple(fields.get("values", ()))
            if expected_kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT
            else (fields.get("left"), *tuple(fields.get("comparators", ())))
        )
        expected_operators = (
            (fields.get("op"),)
            if expected_kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT
            else tuple(fields.get("ops", ()))
        )
        code = (
            "PYC2950"
            if expected_kind is ConditionalRegionKind.BOOLEAN_SHORT_CIRCUIT
            else "PYC2951"
        )
        if (
            fact.get("region_node_id") != node.get("node_id")
            or fact.get("region_kind") != expected_kind.value
            or tuple(fact.get("operand_node_ids", ())) != expected_operands
            or tuple(fact.get("operator_node_ids", ())) != expected_operators
            or fact.get("lowering_shape") != CONDITIONAL_REGION_LOWERING_SHAPE
            or fact.get("result_category") != "boolean-like"
            or fact.get("result_c_type") != "bool"
            or fact.get("operands_evaluated_once") is not True
        ):
            self.services.reject(code, "Conditional-region fact is incomplete or inconsistent", node)


def bind_conditional_region_lowerer(owner: Any) -> ConditionalRegionCIRLowerer:
    """Bind the feature lowerer while keeping the cumulative lowerer small."""

    return ConditionalRegionCIRLowerer(
        ConditionalRegionLoweringServices(
            nodes=owner.nodes,
            categories=owner.categories,
            regions=owner._optional_values(
                "conditional-region-facts", "region_node_id"
            ),
            expression=owner._expression,
            temporary=owner._temporary,
            category_type=owner._category_type,
            provenance=owner._prov,
            synthetic_provenance=owner._synthetic_prov,
            reject=owner._reject,
            check_cancellation=owner._check_cancel,
        )
    )


__all__ = [
    "ConditionalRegionCIRLowerer",
    "ConditionalRegionLoweringServices",
    "bind_conditional_region_lowerer",
]
