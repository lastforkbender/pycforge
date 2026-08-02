"""C IR lowering adapter for the Phase 13 immutable static-record profile.

The adapter consumes only published record facts.  It does not rediscover
class semantics, allocate storage, introduce helpers, or own scalar expression
lowering.  Those services are supplied by the cumulative lowerer so record
lowering remains a small, independently testable representation boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from pycforge.converter.ir.c_ir import (
    CIdentifier,
    CIdentifierRef,
    CMemberAccessExpr,
    CMemberAccessMode,
    CQualifier,
    CRecordDefinition,
    CRecordField,
    CRecordInitializer,
    CStorage,
    CType,
    CVariableDeclaration,
)


def _sid(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


@dataclass(slots=True)
class RecordLoweringServices:
    """Services and proved fact indexes required by record lowering.

    Each fact mapping may use the corresponding semantic ID or source-node ID
    as its key.  :class:`RecordCIRLowerer` indexes values by their published
    identity fields, which lets it consume the canonical fact-table mappings
    directly without depending on a particular caller-side index choice.
    """

    nodes: dict[str, dict[str, Any]]
    definitions: dict[str, dict[str, Any]]
    fields: dict[str, dict[str, Any]]
    initializers: dict[str, dict[str, Any]]
    instances: dict[str, dict[str, Any]]
    bindings: dict[str, dict[str, Any]]
    accesses: dict[str, dict[str, Any]]
    source_bindings_by_id: dict[str, dict[str, Any]]
    generated_names: dict[str, str]
    expression: Callable[..., tuple[tuple[Any, ...], Any]]
    temporary: Callable[..., tuple[CVariableDeclaration, CIdentifierRef]]
    category_type: Callable[[str], CType]
    identifier: Callable[[dict[str, Any], dict[str, Any]], CIdentifier]
    provenance: Callable[..., Any]
    synthetic_provenance: Callable[..., Any]
    reject: Callable[..., Any]
    check_cancellation: Callable[[], None]


class RecordCIRLowerer:
    """Lower complete immutable-record proofs into structured C IR."""

    def __init__(self, services: RecordLoweringServices) -> None:
        self.services = services
        self.definition_by_record = self._index(services.definitions, "record_id")
        self.field_by_id = self._index(services.fields, "field_id")
        self.initializer_by_id = self._index(services.initializers, "initializer_id")
        self.instance_by_assignment = self._index(services.instances, "assignment_node_id")
        self.binding_by_id = self._index(services.bindings, "binding_id")
        self.access_by_node = self._index(services.accesses, "access_node_id")
        self.constructed_bindings: dict[str, CIdentifier] = {}

    @staticmethod
    def _index(
        values: dict[str, dict[str, Any]], identity_field: str
    ) -> dict[str, dict[str, Any]]:
        return {
            str(value[identity_field]): value
            for value in values.values()
            if isinstance(value, dict) and isinstance(value.get(identity_field), str)
        }

    def definitions(self) -> tuple[CRecordDefinition, ...]:
        """Return record declarations in canonical fact-table order."""

        self.services.check_cancellation()
        declarations: list[CRecordDefinition] = []
        for fact in self.services.definitions.values():
            self.services.check_cancellation()
            if not isinstance(fact, dict):
                self.services.reject(
                    "PYC3601", "Static-record definition fact is malformed"
                )
            declarations.append(self._definition(fact))
        return tuple(declarations)

    def construction(self, node: dict[str, Any]) -> tuple[Any, ...]:
        """Lower one proved constructor assignment with explicit LTR staging."""

        s = self.services
        s.check_cancellation()
        fact = self.instance_by_assignment.get(node.get("node_id"))
        if fact is None:
            s.reject(
                "PYC3605",
                "Static-record construction lacks a published instance fact",
                node,
            )
        if fact.get("assignment_node_id") != node.get("node_id"):
            s.reject("PYC3605", "Static-record assignment identity is inconsistent", node)

        definition = self.definition_by_record.get(fact.get("record_id"))
        if definition is None:
            s.reject("PYC3605", "Static-record construction type cannot be resolved", node)
        self._require_closed_definition(definition)

        initializer = self.initializer_by_id.get(definition.get("initializer_id"))
        if (
            initializer is None
            or initializer.get("record_id") != definition.get("record_id")
            or tuple(initializer.get("field_ids", ()))
            != tuple(definition.get("field_ids", ()))
            or initializer.get("receiver_model")
            != "direct-addressed-initialization-receiver"
            or initializer.get("evaluation_order")
            != "field-declaration-order-left-to-right-once"
            or initializer.get("initialization_completeness")
            != "all-fields-exactly-once"
        ):
            s.reject(
                "PYC3605",
                "Static-record construction lacks its exact initializer proof",
                node,
            )

        if (
            fact.get("class_node_id") != definition.get("class_node_id")
            or fact.get("mutable") is not False
            or fact.get("storage_model") != "automatic-inline-record"
            or fact.get("ownership_model") != "unique-lexical-owner"
            or fact.get("lifetime_model") != "enclosing-function-activation"
            or fact.get("aliasing_model") != "forbidden"
            or fact.get("cleanup_model") != "none"
            or fact.get("nullability_model") != "non-null-by-construction"
            or fact.get("allocation_model") != "none"
        ):
            s.reject(
                "PYC3606",
                "Static-record instance lacks the automatic no-allocation proof",
                node,
            )

        binding_fact = self.binding_by_id.get(fact.get("binding_id"))
        if (
            binding_fact is None
            or binding_fact.get("instance_id") != fact.get("instance_id")
            or binding_fact.get("record_id") != fact.get("record_id")
            or binding_fact.get("declaration_node_id") != fact.get("target_node_id")
            or binding_fact.get("single_assignment") is not True
            or binding_fact.get("noalias") is not True
            or binding_fact.get("escapes") is not False
        ):
            s.reject(
                "PYC3606",
                "Static-record construction lacks a unique, non-escaping owner proof",
                node,
            )

        target = s.nodes.get(fact.get("target_node_id"))
        source_binding = s.source_bindings_by_id.get(fact.get("binding_id"))
        construction = s.nodes.get(fact.get("construction_node_id"))
        if target is None or source_binding is None or construction is None:
            s.reject(
                "PYC3605",
                "Static-record construction source binding or node is absent",
                node,
            )
        if target.get("kind") != "Name" or construction.get("kind") != "Call":
            s.reject("PYC3605", "Static-record construction shape is malformed", node)

        field_ids = tuple(definition.get("field_ids", ()))
        argument_ids = tuple(fact.get("argument_node_ids", ()))
        if not field_ids or len(argument_ids) != len(field_ids):
            s.reject(
                "PYC3605", "Static-record constructor arity proof is inconsistent", construction
            )

        prelude: list[Any] = []
        staged_arguments: list[Any] = []
        for ordinal, (field_id, argument_id) in enumerate(
            zip(field_ids, argument_ids)
        ):
            s.check_cancellation()
            field = self.field_by_id.get(field_id)
            argument = s.nodes.get(argument_id)
            if (
                field is None
                or field.get("record_id") != definition.get("record_id")
                or field.get("ordinal") != ordinal
                or field.get("mutable") is not False
                or argument is None
            ):
                s.reject(
                    "PYC3605",
                    "Static-record constructor field or argument proof is inconsistent",
                    argument or construction,
                )
            expression_prelude, expression = s.expression(argument)
            s.check_cancellation()
            prelude.extend(expression_prelude)
            temporary, reference = s.temporary(
                "record_arg",
                construction,
                ordinal,
                s.category_type(str(field.get("category"))),
                expression,
                (argument_id, construction["node_id"], node["node_id"]),
            )
            prelude.append(temporary)
            staged_arguments.append(reference)

        s.check_cancellation()
        record_spelling = self._planned_name(
            str(definition.get("class_binding_id")),
            s.nodes.get(definition.get("class_node_id"), node),
            "record type",
        )
        initializer_expression = CRecordInitializer(
            _sid("c-record-initializer-", construction["node_id"]),
            CType(record_spelling),
            tuple(staged_arguments),
            s.provenance(construction),
        )
        identifier = s.identifier(source_binding, target)
        declaration = CVariableDeclaration(
            _sid("c-record-instance-", node["node_id"]),
            identifier,
            CType(record_spelling, (CQualifier.CONST,)),
            initializer_expression,
            CStorage.NONE,
            s.provenance(node),
        )
        s.check_cancellation()
        self.constructed_bindings[str(fact["binding_id"])] = identifier
        return tuple(prelude) + (declaration,)

    def access(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], CMemberAccessExpr]:
        """Lower one statically-bound immutable field read."""

        s = self.services
        s.check_cancellation()
        fact = self.access_by_node.get(node.get("node_id"))
        if (
            fact is None
            or fact.get("statically_bound") is not True
            or fact.get("access_mode") != "read"
        ):
            s.reject(
                "PYC3607",
                "Static-record field access lacks a complete read proof",
                node,
            )
        field = self.field_by_id.get(fact.get("field_id"))
        binding = self.binding_by_id.get(fact.get("binding_id"))
        if (
            field is None
            or binding is None
            or field.get("record_id") != fact.get("record_id")
            or binding.get("record_id") != fact.get("record_id")
            or binding.get("instance_id") != fact.get("instance_id")
            or fact.get("access_node_id")
            not in tuple(binding.get("allowed_field_access_node_ids", ()))
            or field.get("mutable") is not False
        ):
            s.reject(
                "PYC3607",
                "Static-record receiver or field binding proof is inconsistent",
                node,
            )

        receiver = s.nodes.get(node.get("fields", {}).get("value"))
        identifier = self.constructed_bindings.get(str(fact.get("binding_id")))
        if receiver is None or receiver.get("kind") != "Name" or identifier is None:
            s.reject(
                "PYC3607",
                "Static-record field access occurs without its unique local owner",
                node,
            )
        reference = CIdentifierRef(
            _sid(
                "c-record-owner-ref-",
                node["node_id"],
                identifier.binding_id,
            ),
            identifier.binding_id,
            s.provenance(receiver),
        )
        s.check_cancellation()
        return (), CMemberAccessExpr(
            _sid("c-record-member-", node["node_id"], str(fact["field_id"])),
            reference,
            str(fact["field_id"]),
            CMemberAccessMode.DIRECT,
            s.provenance(node),
        )

    def _definition(self, fact: dict[str, Any]) -> CRecordDefinition:
        s = self.services
        s.check_cancellation()
        self._require_closed_definition(fact)
        class_node = s.nodes.get(fact.get("class_node_id"))
        if class_node is None:
            s.reject("PYC3601", "Static-record class source node is absent")
        class_binding_id = str(fact.get("class_binding_id"))
        record_identifier = CIdentifier(
            class_binding_id,
            self._planned_name(class_binding_id, class_node, "record type"),
            s.provenance(class_node),
        )

        record_fields: list[CRecordField] = []
        for ordinal, field_id in enumerate(tuple(fact.get("field_ids", ()))):
            s.check_cancellation()
            field = self.field_by_id.get(field_id)
            field_node = s.nodes.get((field or {}).get("declaration_node_id"))
            if (
                field is None
                or field.get("record_id") != fact.get("record_id")
                or field.get("ordinal") != ordinal
                or field.get("mutable") is not False
                or field_node is None
            ):
                s.reject(
                    "PYC3602",
                    "Static-record field order or ownership proof is inconsistent",
                    field_node or class_node,
                )
            field_binding_id = str(field["field_id"])
            field_identifier = CIdentifier(
                field_binding_id,
                self._planned_name(field_binding_id, field_node, "record field"),
                s.provenance(field_node),
            )
            record_fields.append(
                CRecordField(
                    _sid("c-record-field-", field_binding_id),
                    field_identifier,
                    s.category_type(str(field.get("category"))),
                    s.provenance(field_node),
                )
            )
        return CRecordDefinition(
            _sid("c-record-definition-", str(fact["record_id"])),
            record_identifier,
            tuple(record_fields),
            s.provenance(class_node),
        )

    def _require_closed_definition(self, fact: dict[str, Any]) -> None:
        if (
            not isinstance(fact.get("record_id"), str)
            or not isinstance(fact.get("class_binding_id"), str)
            or not tuple(fact.get("field_ids", ()))
            or fact.get("mutable") is not False
            or fact.get("storage_model") != "automatic-inline-record"
            or fact.get("ownership_model") != "unique-lexical-owner"
            or fact.get("lifetime_model") != "enclosing-function-activation"
            or fact.get("aliasing_model") != "forbidden"
            or fact.get("cleanup_model") != "none"
            or fact.get("nullability_model") != "non-null-by-construction"
        ):
            node = self.services.nodes.get(fact.get("class_node_id"))
            self.services.reject(
                "PYC3601",
                "Static-record definition lacks the closed automatic ownership proof",
                node,
            )

    def _planned_name(
        self, binding_id: str, node: dict[str, Any] | None, subject: str
    ) -> str:
        spelling = self.services.generated_names.get(binding_id)
        if not spelling:
            self.services.reject(
                "PYC2942", f"Generated {subject} identifier plan is missing", node
            )
        return str(spelling)


__all__ = ["RecordCIRLowerer", "RecordLoweringServices"]
