"""C IR lowering adapter for the approved fixed local-container profile.

The adapter owns only container representation mechanics. Scalar expression
evaluation, source binding, control-flow nesting, diagnostics, and provenance
remain services of the cumulative lowerer and are supplied explicitly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from pycforge.converter.ir.c_ir import (
    CAssignmentStatement,
    CBinaryExpr,
    CBinaryOp,
    CBlock,
    CForStatement,
    CIdentifier,
    CIdentifierRef,
    CInitializerList,
    CIntegerLiteral,
    CStorage,
    CSubscriptExpr,
    CType,
    CVariableDeclaration,
)


def _sid(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]


@dataclass(slots=True)
class ContainerLoweringServices:
    nodes: dict[str, dict[str, Any]]
    shapes: dict[str, dict[str, Any]]
    bindings: dict[str, dict[str, Any]]
    bindings_by_assignment: dict[str, dict[str, Any]]
    accesses: dict[str, dict[str, Any]]
    iterations: dict[str, dict[str, Any]]
    source_bindings_by_id: dict[str, dict[str, Any]]
    source_bindings_by_occurrence: dict[str, dict[str, Any]]
    generated_names: dict[str, str]
    generated_spellings: set[str]
    expression: Callable[..., tuple[tuple[Any, ...], Any]]
    temporary: Callable[..., tuple[CVariableDeclaration, CIdentifierRef]]
    category_type: Callable[[str], CType]
    identifier: Callable[[dict[str, Any], dict[str, Any]], CIdentifier]
    provenance: Callable[..., Any]
    synthetic_provenance: Callable[..., Any]
    block_statements: Callable[..., tuple[Any, ...]]
    temporary_spelling: Callable[[str, str], str]
    reject: Callable[..., Any]
    control_depth: Callable[[], int]


class ContainerCIRLowerer:
    """Lower proved container facts without owning scalar or control semantics."""

    def __init__(self, services: ContainerLoweringServices) -> None:
        self.services = services
        self.storage: dict[str, dict[str, Any]] = {}
        self.component_spellings: dict[tuple[str, str], str] = {}

    def declaration(self, node: dict[str, Any]) -> tuple[Any, ...]:
        s = self.services
        fact = s.bindings_by_assignment[node["node_id"]]
        if not fact.get("valid"):
            s.reject(fact.get("diagnostic_code") or "PYC3403", fact.get("reason") or "Invalid fixed container binding", node)
        shape = s.shapes.get(fact["literal_node_id"])
        if not shape or not shape.get("valid"):
            s.reject(
                (shape or {}).get("diagnostic_code") or "PYC3402",
                (shape or {}).get("reason") or "Fixed container shape fact is absent or invalid",
                s.nodes.get(fact["literal_node_id"], node),
            )
        target = s.nodes[fact["target_node_id"]]
        binding = s.source_bindings_by_id.get(fact["binding_id"])
        if not binding:
            s.reject("PYC3403", "Fixed container binding cannot be resolved", target)
        if s.control_depth():
            s.reject("PYC3403", "A fixed container must be bound directly in a function body", node)

        literal = s.nodes[fact["literal_node_id"]]
        prelude: list[Any] = []
        if fact["container_kind"] in {"list", "tuple"}:
            element_refs: list[Any] = []
            for ordinal, element_id in enumerate(shape["element_node_ids"]):
                expression_prelude, expression = s.expression(s.nodes[element_id])
                prelude.extend(expression_prelude)
                declaration, reference = s.temporary(
                    "container_item",
                    literal,
                    ordinal,
                    s.category_type(fact["element_category"]),
                    expression,
                    (element_id, literal["node_id"]),
                )
                prelude.append(declaration)
                element_refs.append(reference)
            identifier = s.identifier(binding, target)
            declaration = CVariableDeclaration(
                _sid("c-container-array-", node["node_id"]),
                identifier,
                self._array_type(
                    fact["element_category"],
                    fact["capacity"],
                    readonly=fact["container_kind"] == "tuple",
                ),
                CInitializerList(
                    _sid("c-container-init-", literal["node_id"]),
                    tuple(element_refs),
                    s.provenance(literal),
                ),
                CStorage.NONE,
                s.provenance(node),
            )
            self.storage[fact["binding_id"]] = {
                "iteration": identifier,
                "values": identifier,
                "kind": fact["container_kind"],
            }
            return tuple(prelude) + (declaration,)

        key_refs: list[Any] = []
        value_refs: list[Any] = []
        for ordinal, (key_id, value_id) in enumerate(zip(shape["key_node_ids"], shape["value_node_ids"])):
            key_prelude, key_expression = s.expression(s.nodes[key_id])
            prelude.extend(key_prelude)
            key_declaration, key_reference = s.temporary(
                "container_key",
                literal,
                ordinal,
                s.category_type(fact["key_category"]),
                key_expression,
                (key_id, literal["node_id"]),
            )
            prelude.append(key_declaration)
            key_refs.append(key_reference)

            value_prelude, value_expression = s.expression(s.nodes[value_id])
            prelude.extend(value_prelude)
            value_declaration, value_reference = s.temporary(
                "container_value",
                literal,
                ordinal,
                s.category_type(fact["value_category"]),
                value_expression,
                (value_id, literal["node_id"]),
            )
            prelude.append(value_declaration)
            value_refs.append(value_reference)

        key_identifier = self._component_identifier(fact, literal, "keys")
        value_identifier = self._component_identifier(fact, literal, "values")
        key_declaration = CVariableDeclaration(
            _sid("c-container-keys-", node["node_id"]),
            key_identifier,
            self._array_type(fact["key_category"], fact["capacity"], readonly=True),
            CInitializerList(_sid("c-container-keys-init-", literal["node_id"]), tuple(key_refs), s.provenance(literal)),
            CStorage.NONE,
            s.provenance(node),
        )
        value_declaration = CVariableDeclaration(
            _sid("c-container-values-", node["node_id"]),
            value_identifier,
            self._array_type(fact["value_category"], fact["capacity"], readonly=True),
            CInitializerList(_sid("c-container-values-init-", literal["node_id"]), tuple(value_refs), s.provenance(literal)),
            CStorage.NONE,
            s.provenance(node),
        )
        self.storage[fact["binding_id"]] = {
            "iteration": key_identifier,
            "values": value_identifier,
            "kind": "dict",
        }
        return tuple(prelude) + (key_declaration, value_declaration)

    def access(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        s = self.services
        fact = s.accesses.get(node["node_id"])
        if not fact or not fact.get("supported"):
            s.reject(
                (fact or {}).get("diagnostic_code") or "PYC3404",
                (fact or {}).get("reason") or "Container access lacks a static proof",
                node,
            )
        storage = self.storage.get(fact["binding_id"])
        if not storage:
            s.reject("PYC3403", "Container access occurs before its fixed local declaration", node)
        offset = fact.get("resolved_offset")
        if not isinstance(offset, int) or isinstance(offset, bool):
            s.reject("PYC3404", "Container access lacks a resolved integer offset", node)
        provenance = s.provenance(node)
        identifier = storage["values"]
        container = CIdentifierRef(
            _sid("c-container-ref-", node["node_id"], identifier.binding_id),
            identifier.binding_id,
            provenance,
        )
        index = CIntegerLiteral(
            _sid("c-container-offset-", node["node_id"]),
            offset,
            "LL",
            s.synthetic_provenance((node["node_id"],), node["node_id"]),
        )
        return (), CSubscriptExpr(_sid("c-subscript-", node["node_id"]), container, index, provenance)

    def iteration(self, node: dict[str, Any]) -> tuple[Any, ...]:
        s = self.services
        fact = s.iterations[node["node_id"]]
        if not fact.get("supported"):
            s.reject(fact.get("diagnostic_code") or "PYC3407", fact.get("reason") or "Unsupported container iteration", node)
        storage = self.storage.get(fact["binding_id"])
        if not storage:
            s.reject("PYC3403", "Container iteration occurs before its fixed local declaration", node)
        target = s.nodes[node["fields"]["target"]]
        target_binding = s.source_bindings_by_occurrence.get(target["node_id"])
        if not target_binding:
            s.reject("PYC3407", "Container loop target binding could not be resolved", target)

        index_binding_id = _sid("bind-container-index-", node["node_id"])
        index_provenance = s.synthetic_provenance((node["node_id"],), node["node_id"])
        index_identifier = CIdentifier(
            index_binding_id,
            s.temporary_spelling("index", index_binding_id),
            index_provenance,
        )
        zero = CIntegerLiteral(_sid("c-container-loop-zero-", node["node_id"]), 0, "LL", index_provenance)
        one = CIntegerLiteral(_sid("c-container-loop-one-", node["node_id"]), 1, "LL", index_provenance)
        capacity = CIntegerLiteral(_sid("c-container-loop-capacity-", node["node_id"]), fact["capacity"], "LL", index_provenance)
        initializer = CVariableDeclaration(
            _sid("c-container-loop-init-", node["node_id"]),
            index_identifier,
            CType("int64_t"),
            zero,
            CStorage.NONE,
            index_provenance,
        )
        condition_ref = CIdentifierRef(_sid("c-container-loop-condition-ref-", node["node_id"]), index_binding_id, index_provenance)
        condition = CBinaryExpr(_sid("c-container-loop-condition-", node["node_id"]), CBinaryOp.LESS, condition_ref, capacity, index_provenance)
        update_left = CIdentifierRef(_sid("c-container-loop-update-left-", node["node_id"]), index_binding_id, index_provenance)
        update_value = CBinaryExpr(_sid("c-container-loop-update-value-", node["node_id"]), CBinaryOp.ADD, update_left, one, index_provenance)
        update_target = CIdentifierRef(_sid("c-container-loop-update-target-", node["node_id"]), index_binding_id, index_provenance)
        update = CAssignmentStatement(_sid("c-container-loop-update-", node["node_id"]), update_target, update_value, index_provenance)

        data_identifier = storage["iteration"]
        data_ref = CIdentifierRef(_sid("c-container-loop-data-", node["node_id"]), data_identifier.binding_id, index_provenance)
        element_index = CIdentifierRef(_sid("c-container-loop-element-index-", node["node_id"]), index_binding_id, index_provenance)
        element = CSubscriptExpr(_sid("c-container-loop-element-", node["node_id"]), data_ref, element_index, index_provenance)
        target_declaration = CVariableDeclaration(
            _sid("c-container-loop-target-", node["node_id"]),
            s.identifier(target_binding, target),
            s.category_type(fact["target_category"]),
            element,
            CStorage.NONE,
            s.provenance(target, fallback_plan_node=node["node_id"]),
        )
        source_body = s.block_statements(node["fields"].get("body", []), loop=True)
        body = CBlock(
            _sid("c-container-loop-body-", node["node_id"]),
            (target_declaration,) + source_body,
            s.provenance(node),
        )
        return (CForStatement(_sid("c-container-loop-", node["node_id"]), initializer, condition, update, body, s.provenance(node)),)

    def _array_type(self, category: str, capacity: int, *, readonly: bool = False) -> CType:
        scalar = self.services.category_type(category)
        return CType(scalar.base, scalar.qualifiers, scalar.pointer_depth, (capacity,), readonly)

    def _component_identifier(self, fact: dict[str, Any], node: dict[str, Any], component: str) -> CIdentifier:
        s = self.services
        binding_id = _sid("bind-container-component-", fact["binding_id"], component)
        key = (fact["binding_id"], component)
        spelling = self.component_spellings.get(key)
        if spelling is None:
            base = f"{s.generated_names[fact['binding_id']]}_{component}"
            spelling = base
            suffix = 1
            while spelling in s.generated_spellings:
                suffix += 1
                spelling = f"{base}_{suffix}"
            s.generated_spellings.add(spelling)
            self.component_spellings[key] = spelling
        return CIdentifier(binding_id, spelling, s.synthetic_provenance((node["node_id"],), fact["assignment_node_id"]))


__all__ = ["ContainerCIRLowerer", "ContainerLoweringServices"]
