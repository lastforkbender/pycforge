from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.contracts.configuration import (
    PHASE12_MODULE_POLICY,
    PHASE12_RENDERER,
    PHASE12_RULE_SET,
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
)
from pycforge.converter.ir.c_ir import (
    CBooleanLiteral,
    CFloatLiteral,
    CIdentifier,
    CIdentifierRef,
    CIntegerLiteral,
    CMemberAccessExpr,
    CMemberAccessMode,
    CProvenance,
    CQualifier,
    CRecordDefinition,
    CRecordInitializer,
    CStorage,
    CType,
    CVariableDeclaration,
)
from pycforge.converter.records import RecordCIRLowerer, RecordLoweringServices


class _Rejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Canceled(Exception):
    pass


def _node(node_id: str, kind: str, **fields: object) -> dict[str, object]:
    return {"node_id": node_id, "kind": kind, "fields": fields}


def _fixture():
    nodes = {
        item["node_id"]: item
        for item in (
            _node("class-sample", "ClassDef", name="Sample"),
            _node("field-count-declaration", "AnnAssign"),
            _node("field-ratio-declaration", "AnnAssign"),
            _node("field-enabled-declaration", "AnnAssign"),
            _node("assign-sample", "Assign"),
            _node("target-sample", "Name", id="sample"),
            _node("call-sample", "Call"),
            _node("arg-count", "Constant", value=7),
            _node("arg-ratio", "Constant", value=1.5),
            _node("arg-enabled", "Constant", value=True),
            _node("owner-sample", "Name", id="sample"),
            _node("access-ratio", "Attribute", value="owner-sample", attr="ratio"),
        )
    }
    definition = {
        "record_id": "record-sample",
        "class_node_id": "class-sample",
        "class_binding_id": "binding-class-sample",
        "field_ids": ["field-count", "field-ratio", "field-enabled"],
        "initializer_id": "initializer-sample",
        "storage_model": "automatic-inline-record",
        "ownership_model": "unique-lexical-owner",
        "lifetime_model": "enclosing-function-activation",
        "aliasing_model": "forbidden",
        "cleanup_model": "none",
        "nullability_model": "non-null-by-construction",
        "mutable": False,
    }
    fields = {
        # Deliberately not in declaration order: definition.field_ids owns it.
        "field-enabled": {
            "field_id": "field-enabled",
            "record_id": "record-sample",
            "declaration_node_id": "field-enabled-declaration",
            "source_name": "enabled",
            "ordinal": 2,
            "category": "boolean-like",
            "mutable": False,
        },
        "field-count": {
            "field_id": "field-count",
            "record_id": "record-sample",
            "declaration_node_id": "field-count-declaration",
            "source_name": "count",
            "ordinal": 0,
            "category": "integer-like",
            "mutable": False,
        },
        "field-ratio": {
            "field_id": "field-ratio",
            "record_id": "record-sample",
            "declaration_node_id": "field-ratio-declaration",
            "source_name": "ratio",
            "ordinal": 1,
            "category": "floating-like",
            "mutable": False,
        },
    }
    initializer = {
        "initializer_id": "initializer-sample",
        "record_id": "record-sample",
        "field_ids": ["field-count", "field-ratio", "field-enabled"],
        "receiver_model": "direct-addressed-initialization-receiver",
        "evaluation_order": "field-declaration-order-left-to-right-once",
        "initialization_completeness": "all-fields-exactly-once",
    }
    instance = {
        "instance_id": "instance-sample",
        "record_id": "record-sample",
        "class_node_id": "class-sample",
        "construction_node_id": "call-sample",
        "assignment_node_id": "assign-sample",
        "target_node_id": "target-sample",
        "binding_id": "binding-instance-sample",
        "argument_node_ids": ["arg-count", "arg-ratio", "arg-enabled"],
        "storage_model": "automatic-inline-record",
        "ownership_model": "unique-lexical-owner",
        "lifetime_model": "enclosing-function-activation",
        "aliasing_model": "forbidden",
        "cleanup_model": "none",
        "nullability_model": "non-null-by-construction",
        "allocation_model": "none",
        "mutable": False,
    }
    binding = {
        "binding_id": "binding-instance-sample",
        "instance_id": "instance-sample",
        "record_id": "record-sample",
        "declaration_node_id": "target-sample",
        "allowed_field_access_node_ids": ["access-ratio"],
        "single_assignment": True,
        "noalias": True,
        "escapes": False,
    }
    access = {
        "access_node_id": "access-ratio",
        "instance_id": "instance-sample",
        "binding_id": "binding-instance-sample",
        "record_id": "record-sample",
        "field_id": "field-ratio",
        "access_mode": "read",
        "statically_bound": True,
    }
    names = {
        "binding-class-sample": "pycf_record_sample",
        "field-count": "pycf_field_count",
        "field-ratio": "pycf_field_ratio",
        "field-enabled": "pycf_field_enabled",
        "binding-instance-sample": "pycf_sample",
    }
    return {
        "nodes": nodes,
        "definitions": {"record-sample": definition},
        "fields": fields,
        "initializers": {"initializer-sample": initializer},
        "instances": {"instance-sample": instance},
        "bindings": {"binding-instance-sample": binding},
        "accesses": {"access-ratio": access},
        "source_bindings_by_id": {
            "binding-instance-sample": {
                "binding_id": "binding-instance-sample",
                "declaration_node_id": "target-sample",
            }
        },
        "generated_names": names,
    }


def _lowerer(fixture=None, check_cancellation=None):
    fixture = fixture or _fixture()
    events: list[str] = []
    provenance = CProvenance("source", "document-app")

    def expression(node):
        events.append(f"expression:{node['node_id']}")
        value = node["fields"]["value"]
        if isinstance(value, bool):
            result = CBooleanLiteral(f"c-{node['node_id']}", value, provenance)
        elif isinstance(value, int):
            result = CIntegerLiteral(f"c-{node['node_id']}", value, "LL", provenance)
        else:
            result = CFloatLiteral(f"c-{node['node_id']}", value, provenance)
        return (), result

    def temporary(purpose, owner, ordinal, type_ref, initializer, origin_ids):
        events.append(f"temporary:{ordinal}")
        binding_id = f"binding-temp-{ordinal}"
        identifier = CIdentifier(binding_id, f"pycf_record_arg_{ordinal}", provenance)
        declaration = CVariableDeclaration(
            f"temporary-{ordinal}",
            identifier,
            type_ref,
            initializer,
            CStorage.NONE,
            provenance,
        )
        return declaration, CIdentifierRef(
            f"temporary-reference-{ordinal}", binding_id, provenance
        )

    def category_type(category):
        return {
            "integer-like": CType("int64_t"),
            "floating-like": CType("double"),
            "boolean-like": CType("bool"),
        }[category]

    def identifier(binding, node):
        return CIdentifier(
            binding["binding_id"],
            fixture["generated_names"][binding["binding_id"]],
            provenance,
        )

    def reject(code, message, node=None):
        raise _Rejected(code, message)

    services = RecordLoweringServices(
        **fixture,
        expression=expression,
        temporary=temporary,
        category_type=category_type,
        identifier=identifier,
        provenance=lambda node, **kwargs: provenance,
        synthetic_provenance=lambda *args, **kwargs: provenance,
        reject=reject,
        check_cancellation=check_cancellation or (lambda: None),
    )
    return RecordCIRLowerer(services), events


class Phase13RecordLoweringTests(unittest.TestCase):
    def test_cancellation_interrupts_definition_construction_and_access_loops(self):
        def canceled():
            raise _Canceled

        lowerer, _ = _lowerer(check_cancellation=canceled)
        with self.assertRaises(_Canceled):
            lowerer.definitions()

        polls = 0

        def cancel_during_arguments():
            nonlocal polls
            polls += 1
            if polls == 5:
                raise _Canceled

        lowerer, events = _lowerer(check_cancellation=cancel_during_arguments)
        with self.assertRaises(_Canceled):
            lowerer.construction(lowerer.services.nodes["assign-sample"])
        self.assertEqual(lowerer.constructed_bindings, {})
        self.assertGreater(len(events), 0)

        lowerer, _ = _lowerer()
        lowerer.construction(lowerer.services.nodes["assign-sample"])
        lowerer.services.check_cancellation = canceled
        with self.assertRaises(_Canceled):
            lowerer.access(lowerer.services.nodes["access-ratio"])

    def test_definitions_use_planned_bindings_and_explicit_field_order(self):
        lowerer, _ = _lowerer()
        definitions = lowerer.definitions()
        self.assertEqual(len(definitions), 1)
        record = definitions[0]
        self.assertIsInstance(record, CRecordDefinition)
        self.assertEqual(record.identifier.binding_id, "binding-class-sample")
        self.assertEqual(record.identifier.spelling, "pycf_record_sample")
        self.assertEqual(
            [field.identifier.binding_id for field in record.fields],
            ["field-count", "field-ratio", "field-enabled"],
        )
        self.assertEqual(
            [field.identifier.spelling for field in record.fields],
            ["pycf_field_count", "pycf_field_ratio", "pycf_field_enabled"],
        )
        self.assertEqual(
            [field.type_ref for field in record.fields],
            [CType("int64_t"), CType("double"), CType("bool")],
        )

    def test_construction_stages_every_argument_left_to_right_then_declares_const(self):
        lowerer, events = _lowerer()
        statements = lowerer.construction(lowerer.services.nodes["assign-sample"])
        self.assertEqual(
            events,
            [
                "expression:arg-count",
                "temporary:0",
                "expression:arg-ratio",
                "temporary:1",
                "expression:arg-enabled",
                "temporary:2",
            ],
        )
        self.assertEqual(len(statements), 4)
        self.assertTrue(
            all(isinstance(item, CVariableDeclaration) for item in statements)
        )
        declaration = statements[-1]
        self.assertEqual(declaration.identifier.binding_id, "binding-instance-sample")
        self.assertEqual(
            declaration.type_ref,
            CType("pycf_record_sample", (CQualifier.CONST,)),
        )
        self.assertIsInstance(declaration.initializer, CRecordInitializer)
        self.assertEqual(
            declaration.initializer.record_type, CType("pycf_record_sample")
        )
        self.assertEqual(
            [item.binding_id for item in declaration.initializer.elements],
            ["binding-temp-0", "binding-temp-1", "binding-temp-2"],
        )

    def test_access_is_direct_and_uses_exact_owner_and_field_bindings(self):
        lowerer, _ = _lowerer()
        lowerer.construction(lowerer.services.nodes["assign-sample"])
        prelude, expression = lowerer.access(
            lowerer.services.nodes["access-ratio"]
        )
        self.assertEqual(prelude, ())
        self.assertIsInstance(expression, CMemberAccessExpr)
        self.assertEqual(expression.mode, CMemberAccessMode.DIRECT)
        self.assertEqual(expression.receiver.binding_id, "binding-instance-sample")
        self.assertEqual(expression.field_binding_id, "field-ratio")

    def test_access_before_construction_and_heap_fact_fail_closed(self):
        lowerer, _ = _lowerer()
        with self.assertRaises(_Rejected) as caught:
            lowerer.access(lowerer.services.nodes["access-ratio"])
        self.assertEqual(caught.exception.code, "PYC3607")

        fixture = deepcopy(_fixture())
        fixture["instances"]["instance-sample"]["allocation_model"] = "heap"
        lowerer, _ = _lowerer(fixture)
        with self.assertRaises(_Rejected) as caught:
            lowerer.construction(lowerer.services.nodes["assign-sample"])
        self.assertEqual(caught.exception.code, "PYC3606")


class Phase13RecordLoweringIntegrationTests(unittest.TestCase):
    RECORD_SOURCE = (
        "class Point:\n"
        "    x: int\n"
        "    y: int\n"
        "    def __init__(self, x: int, y: int) -> None:\n"
        "        self.x = x\n"
        "        self.y = y\n"
        "\n"
        "def run() -> int:\n"
        "    point = Point(10, 20)\n"
        "    return point.x + point.y\n"
    )

    def test_cumulative_lowerer_publishes_the_structured_record_slice(self):
        first = PythonToCConverter().convert(
            ConversionRequest.from_source(self.RECORD_SOURCE)
        )
        second = PythonToCConverter().convert(
            ConversionRequest.from_source(self.RECORD_SOURCE)
        )
        self.assertEqual(first.status, ResultStatus.CONVERTED)
        self.assertEqual(first.generated_c, second.generated_c)
        self.assertEqual(first.output_fingerprint, second.output_fingerprint)
        self.assertEqual(first.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(first.stage_artifact.payload["c_ir_schema"], "c-ir/0.14.3")

        c_ir = first.stage_artifact.payload["c_ir"]
        declarations = c_ir["declarations"]
        self.assertEqual(declarations[0]["kind"], "CRecordDefinition")
        record = declarations[0]
        self.assertEqual(
            [field["type_ref"]["base"] for field in record["fields"]],
            ["int64_t", "int64_t"],
        )
        function = next(
            item for item in declarations if item["kind"] == "CFunctionDefinition"
        )
        statements = function["body"]["statements"]
        self.assertEqual(
            [item["kind"] for item in statements],
            [
                "CVariableDeclaration",
                "CVariableDeclaration",
                "CVariableDeclaration",
                "CReturnStatement",
            ],
        )
        instance = statements[2]
        self.assertEqual(instance["type_ref"]["qualifiers"], ["const"])
        self.assertEqual(instance["initializer"]["kind"], "CRecordInitializer")
        returned = statements[3]["expression"]
        self.assertEqual(returned["left"]["kind"], "CMemberAccessExpr")
        self.assertEqual(returned["left"]["mode"], "direct")
        self.assertEqual(returned["right"]["kind"], "CMemberAccessExpr")
        self.assertEqual(first.stage_artifact.payload["helper_manifest"], [])

    def test_class_free_phase13_c_bytes_match_the_sealed_phase12_surface(self):
        source = "def run(value: int) -> int:\n    return value + 1\n"
        current_request = ConversionRequest.from_source(
            source,
            rule_set_version=PHASE13_RULE_SET,
            renderer_version=PHASE13_RENDERER,
        )
        predecessor_request = replace(
            current_request,
            rule_set_version=PHASE12_RULE_SET,
            renderer_version=PHASE12_RENDERER,
            module_policy_version=PHASE12_MODULE_POLICY,
        )
        current = PythonToCConverter().convert(current_request)
        predecessor = PythonToCConverter().convert(predecessor_request)
        self.assertEqual(current.status, ResultStatus.CONVERTED)
        self.assertEqual(predecessor.status, ResultStatus.CONVERTED)
        self.assertEqual(current.generated_c, predecessor.generated_c)
        self.assertEqual(current.output_fingerprint, predecessor.output_fingerprint)
        self.assertEqual(current.stage_artifact.payload["c_ir_schema"], "c-ir/0.13")
        self.assertEqual(
            predecessor.stage_artifact.payload["c_ir_schema"], "c-ir/0.12"
        )


if __name__ == "__main__":
    unittest.main()
