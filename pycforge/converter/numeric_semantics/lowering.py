"""Helper-call lowering for independently validated numeric facts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from pycforge.converter.ir.c_ir import (
    CCallExpr,
    CIdentifierRef,
    CIntegerLiteral,
    CProvenance,
    CType,
    CUnaryExpr,
    CUnaryOp,
)


def _sid(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return prefix + digest


@dataclass(frozen=True, slots=True)
class NumericLoweringServices:
    nodes: dict[str, dict[str, Any]]
    operations: dict[str, dict[str, Any]]
    expression: Callable[[dict[str, Any]], tuple[tuple[Any, ...], Any]]
    temporary: Callable[[str, dict[str, Any], int, CType, Any, tuple[str, ...]], tuple[Any, Any]]
    provenance: Callable[[dict[str, Any]], CProvenance]
    synthetic_provenance: Callable[[tuple[str, ...], str | None], CProvenance]
    reject: Callable[[str, str, dict[str, Any] | None], None]
    check_cancellation: Callable[[], None]


class NumericCIRLowerer:
    def __init__(self, services: NumericLoweringServices) -> None:
        self.services = services

    def operation(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        s.check_cancellation()
        fact = s.operations.get(node["node_id"])
        if not fact:
            s.reject(
                "PYC3701",
                "Integer floor arithmetic lacks an independently validated numeric fact",
                node,
            )
        left_node = s.nodes.get(fact["left_node_id"])
        right_node = s.nodes.get(fact["right_node_id"])
        if left_node is None or right_node is None:
            s.reject("PYC3701", "Numeric fact references an absent operand", node)

        prelude: list[Any] = []
        left_prelude, left_expression = s.expression(left_node)
        prelude.extend(left_prelude)
        left_declaration, left_reference = s.temporary(
            "numeric_left",
            node,
            0,
            CType("int64_t"),
            left_expression,
            (fact["left_node_id"], node["node_id"]),
        )
        prelude.append(left_declaration)

        right_expression = self._literal_from_validated_fact(fact, right_node)
        right_declaration, right_reference = s.temporary(
            "numeric_right",
            node,
            0,
            CType("int64_t"),
            right_expression,
            (fact["right_node_id"], node["node_id"]),
        )
        prelude.append(right_declaration)

        helper = fact["helper_requirement"]
        callee = CIdentifierRef(
            _sid("c-numeric-helper-ref-", node["node_id"], helper),
            f"helper-binding:{helper}:function",
            s.synthetic_provenance((node["node_id"],), node["node_id"]),
        )
        call = CCallExpr(
            _sid("c-numeric-helper-call-", node["node_id"], helper),
            callee,
            (left_reference, right_reference),
            s.provenance(node),
        )
        result_declaration, result_reference = s.temporary(
            "numeric_result",
            node,
            0,
            CType("int64_t"),
            call,
            (node["node_id"],),
        )
        prelude.append(result_declaration)
        s.check_cancellation()
        return tuple(prelude), result_reference

    def _literal_from_validated_fact(
        self,
        fact: dict[str, Any],
        node: dict[str, Any],
    ) -> Any:
        value = fact.get("divisor_value")
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value in {0, -1}
            or not -(2**63 - 1) <= value <= 2**63 - 1
        ):
            self.services.reject("PYC3702", "Numeric divisor proof is invalid", node)
        magnitude = abs(value)
        literal = CIntegerLiteral(
            _sid("c-numeric-divisor-literal-", node["node_id"], str(value)),
            magnitude,
            "LL",
            self.services.provenance(node),
        )
        if value < 0:
            return CUnaryExpr(
                _sid("c-numeric-divisor-negate-", node["node_id"], str(value)),
                CUnaryOp.NEGATE,
                literal,
                self.services.provenance(node),
            )
        return literal


def bind_numeric_lowerer(owner: Any) -> NumericCIRLowerer:
    """Bind the feature lowerer without expanding the cumulative hotspot."""

    return NumericCIRLowerer(
        NumericLoweringServices(
            nodes=owner.nodes,
            operations=owner._optional_values(
                "numeric-operation-facts", "binop_node_id"
            ),
            expression=owner._expression,
            temporary=owner._temporary,
            provenance=owner._prov,
            synthetic_provenance=owner._synthetic_prov,
            reject=owner._reject,
            check_cancellation=owner._check_cancel,
        )
    )


__all__ = ["NumericCIRLowerer", "NumericLoweringServices", "bind_numeric_lowerer"]
