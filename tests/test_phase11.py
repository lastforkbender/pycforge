from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.contracts.configuration import (
    DEFAULT_CONTAINER_POLICY,
    PHASE9_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.ir.c_ir import (
    CBlock,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIdentifierRef,
    CInclude,
    CInitializerList,
    CIntegerLiteral,
    CProvenance,
    CReturnStatement,
    CStorage,
    CSubscriptExpr,
    CTranslationUnitBuilder,
    CType,
    CVariableDeclaration,
    CONTAINER_SCHEMA_VERSION,
    SCHEMA_VERSION,
    serialize_translation_unit,
    validate_translation_unit,
)
from pycforge.converter.c_output import CRenderer, validate_c_text
from pycforge.converter.support_templates import default_helper_registry


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


def convert(source: str, *, full: bool = False, **request_options: object):
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source, **request_options),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def kinds(value: object) -> list[str]:
    result: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("kind"), str):
            result.append(value["kind"])
        for item in value.values():
            result.extend(kinds(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(kinds(item))
    return result


class Phase11Tests(unittest.TestCase):
    def test_representation_gate_precedes_implementation(self):
        decision = (ROOT / "transition/phase_11/container_representation_decisions.md").read_text(encoding="utf-8")
        for item in (
            "Capacity is fixed",
            "Aliasing: rejected",
            "insertion order",
            "Negative indices",
            "No allocation",
            "PYC3407",
        ):
            self.assertIn(item.lower(), decision.lower())

    def test_list_tuple_and_dictionary_vertical_slices(self):
        sources = {
            "list": "def f() -> int:\n    values = [1, 2, 3]\n    return values[-1]\n",
            "tuple": "def f() -> str:\n    values = (\"a\", \"b\")\n    return values[0]\n",
            "dict": "def f() -> int:\n    values = {\"a\": 1, \"b\": 2}\n    return values[\"b\"]\n",
        }
        results = {key: convert(value) for key, value in sources.items()}
        self.assertTrue(all(item.status is ResultStatus.CONVERTED for item in results.values()))
        self.assertIn("int64_t values[3]", results["list"].generated_c)
        self.assertIn("return values[2LL];", results["list"].generated_c)
        self.assertIn("const char * const values[2]", results["tuple"].generated_c)
        self.assertIn("const char * const values_keys[2]", results["dict"].generated_c)
        self.assertIn("const int64_t values_values[2]", results["dict"].generated_c)
        self.assertIn("return values_values[1LL];", results["dict"].generated_c)
        for result in results.values():
            payload = result.stage_artifact.payload
            self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
            self.assertEqual(payload["schema_version"], GENERATED_C_SCHEMA)
            self.assertEqual(payload["c_ir_schema"], C_IR_SCHEMA)
            self.assertTrue(validate_c_text(result.generated_c).accepted)

    def test_dictionary_and_container_iteration_preserve_declared_order(self):
        source = (
            "def f() -> str:\n"
            "    values = {\"first\": 10, \"second\": 20}\n"
            "    answer = \"\"\n"
            "    for key in values:\n"
            "        answer = key\n"
            "    return answer\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        text = result.generated_c
        self.assertLess(text.index('= "first";'), text.index('= "second";'))
        self.assertIn("key = values_keys[pycf_index_", text)
        iteration = table(result.stage_artifact.payload, "container-iteration-facts")["records"][0]["value"]
        self.assertEqual(iteration["order_policy"], "source-insertion-order")
        self.assertEqual(iteration["capacity"], 2)
        self.assertTrue(iteration["supported"])

    def test_proved_indices_publish_normalized_offsets(self):
        source = (
            "def f() -> int:\n"
            "    values = [10, 20, 30]\n"
            "    first = values[0]\n"
            "    last = values[-1]\n"
            "    return first + last\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        records = table(result.stage_artifact.payload, "container-access-facts")["records"]
        facts = sorted((item["value"]["source_index"], item["value"]["resolved_offset"]) for item in records)
        self.assertEqual(facts, [(-1, 2), (0, 0)])
        self.assertIn("values[0LL]", result.generated_c)
        self.assertIn("values[2LL]", result.generated_c)

    def test_element_calls_are_staged_left_to_right_once(self):
        source = (
            "def identity(value: int) -> int:\n    return value\n\n"
            "def f() -> int:\n"
            "    values = [identity(10), identity(20)]\n"
            "    return values[0] + values[1]\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        text = result.generated_c
        ten = text.index(" = 10LL;")
        first_call = text.index(" = identity(", ten)
        twenty = text.index(" = 20LL;", first_call)
        second_call = text.index(" = identity(", twenty)
        array = text.index("values[2] = {", second_call)
        self.assertLess(ten, first_call)
        self.assertLess(first_call, twenty)
        self.assertLess(twenty, second_call)
        self.assertLess(second_call, array)
        self.assertEqual(text.count(" = identity("), 2)

    def test_bounded_loop_retains_break_and_continue_structure(self):
        source = (
            "def f() -> int:\n"
            "    values = (1, 2, 3)\n"
            "    total = 0\n"
            "    for value in values:\n"
            "        if value == 2:\n            continue\n"
            "        if value == 3:\n            break\n"
            "        total = total + value\n"
            "    return total\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIn("for (int64_t pycf_index_", result.generated_c)
        self.assertIn("value = values[pycf_index_", result.generated_c)
        self.assertIn("continue;", result.generated_c)
        self.assertIn("break;", result.generated_c)

    def test_shape_rejections_are_primary_and_stable(self):
        cases = {
            "def f() -> int:\n    values = []\n    return 1\n": "PYC3401",
            "def f() -> int:\n    values = [1, 2.0]\n    return 1\n": "PYC3402",
            "def f() -> int:\n    values = [[1], [2]]\n    return 1\n": "PYC3401",
            "def f() -> int:\n    values = [x for x in range(3)]\n    return 1\n": "PYC3406",
            "def f() -> int:\n    values = [" + ", ".join(str(item) for item in range(65)) + "]\n    return 1\n": "PYC3401",
        }
        for source, code in cases.items():
            with self.subTest(code=code):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertIsNone(result.generated_c)
                self.assertTrue(result.diagnostics[0].fact_references)

    def test_dynamic_missing_and_out_of_bounds_accesses_reject(self):
        cases = {
            "def f(index: int) -> int:\n    values = [1, 2]\n    return values[index]\n": "PYC3404",
            "def f() -> int:\n    values = [1, 2]\n    return values[2]\n": "PYC3405",
            "def f() -> int:\n    values = {\"a\": 1}\n    return values[\"b\"]\n": "PYC3405",
            "def f(key: str) -> int:\n    values = {\"a\": 1}\n    return values[key]\n": "PYC3404",
        }
        for source, code in cases.items():
            with self.subTest(code=code):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual(result.diagnostics[0].code, code)
                self.assertTrue(result.diagnostics[0].fact_references)
                self.assertFalse(result.stage_artifact.payload.get("helper_manifest"))

    def test_alias_escape_rebinding_and_mutation_reject(self):
        cases = {
            "def f() -> int:\n    values = [1, 2]\n    alias = values\n    return alias[0]\n": "PYC3403",
            "def f() -> int:\n    values = [1, 2]\n    values = [3, 4]\n    return values[0]\n": "PYC3403",
            "def f() -> int:\n    values = [1, 2]\n    values[0] = 3\n    return values[0]\n": "PYC3406",
            "def f() -> int:\n    values = [1, 2]\n    values.append(3)\n    return 1\n": "PYC3406",
            "def identity(value: int) -> int:\n    return value\n\ndef f() -> int:\n    values = [1, 2]\n    identity(values)\n    return 1\n": "PYC3403",
        }
        for source, code in cases.items():
            with self.subTest(code=code):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual(result.diagnostics[0].code, code)
                self.assertIsNone(result.generated_c)

    def test_unsupported_iteration_forms_reject(self):
        direct = convert("def f() -> int:\n    total = 0\n    for value in [1, 2]:\n        total = total + value\n    return total\n")
        loop_else = convert("def f() -> int:\n    values = [1, 2]\n    total = 0\n    for value in values:\n        total = total + value\n    else:\n        total = 3\n    return total\n")
        self.assertEqual(direct.diagnostics[0].code, "PYC3407")
        self.assertEqual(loop_else.diagnostics[0].code, "PYC3407")

    def test_container_facts_ruleplans_summary_and_trace_are_closed(self):
        source = "def f() -> int:\n    values = [1, 2]\n    return values[1]\n"
        result = convert(source, full=True)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        for table_id in (
            "container-shape-facts",
            "container-binding-facts",
            "container-access-facts",
            "container-iteration-facts",
        ):
            self.assertIn(table_id, {item["table_id"] for item in payload["fact_tables"]})
        rules = {item["rule_id"] for item in payload["rule_plans"]}
        self.assertIn("phase11.container.list_literal", rules)
        self.assertIn("phase11.container.assignment", rules)
        self.assertIn("phase11.container.index.proved", rules)
        self.assertEqual(result.conversion_summary["schema_version"], CONVERSION_SUMMARY_SCHEMA)
        self.assertEqual(result.conversion_summary["container_policy_version"], DEFAULT_CONTAINER_POLICY)
        self.assertEqual(result.conversion_summary["containers"][0]["allocation"], "none")
        self.assertEqual(result.decision_trace["schema_version"], DECISION_TRACE_SCHEMA)
        self.assertEqual(result.decision_trace["container_policy_version"], DEFAULT_CONTAINER_POLICY)
        self.assertTrue(result.decision_trace["source_output_mappings"])

    def test_c_ir_011_arrays_initializer_lists_and_subscripts_are_structural(self):
        provenance = CProvenance("synthetic")
        function = CIdentifier("fn", "f", provenance)
        array = CIdentifier("array", "values", provenance)
        prototype = CFunctionPrototype("prototype", function, CType("int64_t"), (), CStorage.NONE, provenance)
        initializer = CInitializerList(
            "initializer",
            (CIntegerLiteral("one", 1, "LL", provenance), CIntegerLiteral("two", 2, "LL", provenance)),
            provenance,
        )
        declaration = CVariableDeclaration("declaration", array, CType("int64_t", array_extents=(2,)), initializer, CStorage.NONE, provenance)
        access = CSubscriptExpr("access", CIdentifierRef("array-ref", "array", provenance), CIntegerLiteral("index", 1, "LL", provenance), provenance)
        definition = CFunctionDefinition("definition", function, CType("int64_t"), (), CBlock("body", (declaration, CReturnStatement("return", access, provenance)), provenance), CStorage.NONE, provenance)
        builder = CTranslationUnitBuilder("c11-portable-fixed-v1", schema_version=CONTAINER_SCHEMA_VERSION, provenance=provenance)
        builder.add_include(CInclude("include", "stdint.h", True, provenance))
        builder.add_declaration(prototype)
        builder.add_declaration(definition)
        unit = builder.build()
        self.assertTrue(validate_translation_unit(unit).accepted)
        rendered = CRenderer().render(unit).text
        self.assertIn("int64_t values[2] = {1LL, 2LL};", rendered)
        self.assertIn("return values[1LL];", rendered)
        self.assertTrue(validate_c_text(rendered).accepted)
        serialized = serialize_translation_unit(unit)
        self.assertIn("CInitializerList", kinds(serialized))
        self.assertIn("CSubscriptExpr", kinds(serialized))

        old_builder = CTranslationUnitBuilder("c11-portable-fixed-v1", schema_version=SCHEMA_VERSION, provenance=provenance)
        old_builder.add_include(CInclude("old-include", "stdint.h", True, provenance))
        old_builder.add_declaration(prototype)
        old_builder.add_declaration(definition)
        old_validation = validate_translation_unit(old_builder.build())
        self.assertFalse(old_validation.accepted)
        self.assertIn("array types require C IR schema 0.11", old_validation.errors)

    def test_phase10_helper_contract_and_scalar_output_remain_stable(self):
        registry = default_helper_registry()
        self.assertEqual(registry.fingerprint, "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98")
        self.assertEqual(
            [item["asset_fingerprint"] for item in registry.manifest],
            [
                "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
                "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
            ],
        )
        source = "def f(value: int) -> int:\n    return value + 1\n"
        current = convert(source)
        phase10_surface = convert(source, rule_set_version=PHASE9_RULE_SET, renderer_version="c-renderer-v0.9")
        self.assertEqual(current.generated_c, phase10_surface.generated_c)
        self.assertEqual(phase10_surface.stage_artifact.payload["c_ir_schema"], "c-ir/0.9")
        self.assertEqual(phase10_surface.stage_artifact.payload["schema_version"], "generated-c/0.10")
        self.assertNotIn("array_extents", json.dumps(phase10_surface.stage_artifact.payload["c_ir"], sort_keys=True))

    def test_container_policy_is_request_identity_and_unknown_policy_rejects(self):
        source = "def f() -> int:\n    values = [1]\n    return values[0]\n"
        accepted = convert(source)
        rejected = convert(source, container_policy_version="unknown-container-policy")
        self.assertEqual(accepted.status, ResultStatus.CONVERTED)
        self.assertEqual(accepted.stage_artifact.payload["container_policy_version"], DEFAULT_CONTAINER_POLICY)
        self.assertEqual(rejected.status, ResultStatus.REJECTED)
        self.assertEqual(rejected.diagnostics[0].code, "PYC1015")

    def test_phase11_output_is_deterministic_in_a_fresh_process(self):
        source = "def f() -> int:\n    values = {1: 10, 2: 20}\n    return values[2]\n"
        script = (
            "import json\n"
            "from pycforge import ConversionRequest,PythonToCConverter\n"
            f"r=PythonToCConverter().convert(ConversionRequest.from_source({source!r}))\n"
            "print(json.dumps({'status':r.status.value,'c':r.generated_c,'fp':r.output_fingerprint.value,'artifact':r.stage_artifact.artifact_fingerprint.value},sort_keys=True))\n"
        )
        first = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=ENV, text=True, capture_output=True, check=True).stdout
        second = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=ENV, text=True, capture_output=True, check=True).stdout
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
