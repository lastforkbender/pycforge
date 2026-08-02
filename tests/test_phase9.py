from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.resource_policy import ResourcePolicy
from pycforge.converter.contracts.configuration import (
    PHASE14B_RENDERER,
    PHASE14B_RULE_SET,
    PHASE14C_RENDERER,
    PHASE14C_RULE_SET,
)
from pycforge.converter.ir.c_ir import (
    CBlock,
    CCallExpr,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIdentifierRef,
    CParameter,
    CProvenance,
    CReturnStatement,
    CStorage,
    CTranslationUnitBuilder,
    CType,
    SCHEMA_VERSION,
    validate_translation_unit,
)
from pycforge.ide.controller import WorkspaceController
from pycforge.laboratory.audits import audit_rules, audit_transition


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
BASE = (
    "def add(a: int, b: int) -> int:\n"
    "    return a + b\n\n"
    "def twice(x: int) -> int:\n"
    "    return add(x, x)\n"
)


def convert(source: str = BASE, **kwargs: object):
    return PythonToCConverter().convert(ConversionRequest.from_source(source), **kwargs)


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def kinds(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("kind"), str):
            found.append(value["kind"])
        for item in value.values():
            found.extend(kinds(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(kinds(item))
    return found


class Phase9Tests(unittest.TestCase):
    def test_multiple_functions_prototypes_calls_and_current_artifact_schemas(self):
        result = convert()
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(payload["schema_version"], "generated-c/0.14.3")
        self.assertEqual(payload["c_ir_schema"], "c-ir/0.14.3")
        self.assertEqual(kinds(payload["c_ir"]).count("CFunctionPrototype"), 2)
        self.assertEqual(kinds(payload["c_ir"]).count("CFunctionDefinition"), 2)
        self.assertEqual(kinds(payload["c_ir"]).count("CCallExpr"), 1)

    def test_arguments_are_staged_left_to_right_once(self):
        source = (
            "def identity(value: int) -> int:\n    return value\n\n"
            "def combine(left: int, right: int) -> int:\n    return left + right\n\n"
            "def f() -> int:\n    return combine(identity(10), identity(20))\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        text = result.generated_c
        ten = text.index(" = 10LL;")
        first_call = text.index(" = identity(", ten)
        twenty = text.index(" = 20LL;", first_call)
        second_call = text.index(" = identity(", twenty)
        outer_call = text.index(" = combine(", second_call)
        self.assertLess(ten, first_call)
        self.assertLess(first_call, twenty)
        self.assertLess(twenty, second_call)
        self.assertLess(second_call, outer_call)
        self.assertEqual(kinds(result.stage_artifact.payload["c_ir"]).count("CCallExpr"), 3)

    def test_forward_call_is_legal_because_prototypes_precede_definitions(self):
        source = (
            "def first(x: int) -> int:\n    return later(x)\n\n"
            "def later(x: int) -> int:\n    return x + 1\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        text = result.generated_c
        self.assertLess(text.index("int64_t later("), text.index("int64_t first(", text.index("{\n") - 30))
        self.assertIn("later(", text)

    def test_local_declarations_before_and_after_calls(self):
        source = (
            "def identity(x: int) -> int:\n    return x\n\n"
            "def f(x: int) -> int:\n"
            "    before = x + 1\n"
            "    after = identity(before)\n"
            "    before = after + 1\n"
            "    return before\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIn("int64_t before =", result.generated_c)
        self.assertIn("int64_t after =", result.generated_c)
        self.assertIn("before = after + 1LL;", result.generated_c)

    def test_understood_call_can_be_an_expression_statement(self):
        source = (
            "def identity(x: int) -> int:\n    return x\n\n"
            "def f(x: int) -> int:\n    identity(x)\n    return x\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertRegex(result.generated_c, r"\n    identity\(pycf_arg_[a-f0-9]+\);\n")

    def test_calls_inside_if_while_and_range_bound(self):
        source = (
            "def positive(x: int) -> bool:\n    return x > 0\n\n"
            "def decrement(x: int) -> int:\n    return x - 1\n\n"
            "def f(x: int) -> int:\n"
            "    for i in range(decrement(x)):\n        continue\n"
            "    while positive(x):\n        x = decrement(x)\n"
            "    if positive(x):\n        return decrement(x)\n"
            "    return x\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIn("for (", result.generated_c)
        self.assertIn("while (true)", result.generated_c)
        self.assertIn("if (", result.generated_c)
        self.assertGreaterEqual(result.generated_c.count("decrement("), 4)

    def test_all_reachable_explicit_return_paths_are_supported(self):
        source = "def choose(flag: bool, left: int, right: int) -> int:\n    if flag:\n        return left\n    else:\n        return right\n"
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        return_fact = table(result.stage_artifact.payload, "return-path-facts")["records"][0]["value"]
        self.assertFalse(return_fact["fallthrough_possible"])
        self.assertTrue(return_fact["compatible"])

    def test_signature_call_return_local_and_graph_fact_tables_are_complete(self):
        result = convert()
        tables = {item["table_id"]: item for item in result.stage_artifact.payload["fact_tables"]}
        required = {
            "function-signature-facts",
            "call-target-facts",
            "return-path-facts",
            "local-declaration-facts",
            "call-graph-facts",
        }
        self.assertTrue(required.issubset(tables))
        for name in required:
            self.assertEqual(tables[name]["completeness"], "complete")
            keys = [record["key"] for record in tables[name]["records"]]
            self.assertEqual(keys, sorted(keys))

    def test_call_ruleplan_exposes_annotations_order_and_ownership(self):
        result = convert()
        plan = next(item for item in result.stage_artifact.payload["rule_plans"] if item["rule_id"] == "phase9.call.understood_target")
        self.assertTrue(any(item.startswith("annotation-evidence:") for item in plan["facts_used"]))
        self.assertIn("arguments-evaluated-left-to-right-once", plan["semantic_obligations"])
        self.assertIn("parameter-ownership-boundary-explicit", plan["semantic_obligations"])
        self.assertFalse(plan["unresolved_obligations"])
        summary = result.conversion_summary
        self.assertEqual(summary["schema_version"], "pycforge.conversion-summary/0.14.3")
        self.assertTrue(all(item["return_annotation"] == "int" for item in summary["functions"]))
        self.assertTrue(summary["calls"][0]["annotation_evidence"])
        self.assertTrue(summary["calls"][0]["arguments_evaluated_once"])

    def test_trace_contains_the_same_phase9_call_ruleplan(self):
        result = convert(observation=ObservationOptions("Full", True))
        traced = [item["plan"] for item in result.decision_trace["events"] if item.get("kind") == "rule_plan"]
        self.assertTrue(any(item["rule_id"] == "phase9.call.understood_target" for item in traced))
        self.assertEqual(result.decision_trace["schema_version"], "pycforge.decision-trace/0.14.3")
        self.assertEqual(result.telemetry["schema_version"], "pycforge.telemetry/0.9")
        self.assertRegex(result.decision_trace["trace_fingerprint"], r"^[0-9a-f]{64}$")
        trace_body = dict(result.decision_trace)
        trace_value = trace_body.pop("trace_fingerprint")
        self.assertEqual(trace_value, fingerprint("decision-trace", trace_body).value)
        self.assertEqual(result.decision_trace["rule_decisions"], traced)
        summary = convert(observation=ObservationOptions("Summary", False)).decision_trace
        decisions = convert(observation=ObservationOptions("Decisions", False)).decision_trace
        self.assertFalse(any(item.get("kind") == "rule_plan" for item in summary["events"]))
        self.assertTrue(any(item.get("kind") == "rule_plan" for item in decisions["events"]))

    def test_mappings_cover_prototypes_parameters_arguments_calls_and_temporaries(self):
        result = convert()
        mappings = result.stage_artifact.payload["source_output_mappings"]
        prefixes = {item["c_node_id"].split("-")[1] for item in mappings}
        self.assertTrue({"prototype", "proto", "param", "arg", "call", "ret"}.issubset(prefixes))
        self.assertTrue(any(item["origin_kind"] == "synthetic" and item["c_node_id"].startswith("c-arg-temp-") for item in mappings))
        self.assertTrue(any(item["c_node_id"].startswith("c-call-") and item["rule_plan_id"] for item in mappings))

    def test_unknown_and_rebound_targets_reject_at_the_call(self):
        cases = (
            "def f(x: int) -> int:\n    return missing(x)\n",
            "def target(x: int) -> int:\n    return x\n\ndef f(x: int) -> int:\n    target = 1\n    return target(x)\n",
        )
        for source in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, "PYC2901")
            self.assertIsNotNone(result.diagnostics[0].source_span)

    def test_direct_keyword_arguments_convert_while_unpacking_stays_rejected(self):
        prefix = "def target(x: int) -> int:\n    return x\n\n"
        source = prefix + "def f(x: int) -> int:\n    return target(x=x)\n"
        active = convert(source)
        self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)

        for call in ("target(*x)", "target(**x)"):
            result = convert(prefix + f"def f(x: int) -> int:\n    return {call}\n")
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, "PYC2910")

        historical = PythonToCConverter().convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE14B_RULE_SET,
                renderer_version=PHASE14B_RENDERER,
            )
        )
        self.assertEqual(historical.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in historical.diagnostics], ["PYC2910"])
        self.assertIsNone(historical.generated_c)

    def test_defaults_and_variadics_reject_while_required_keyword_only_is_successor_supported(self):
        sources = (
            "def f(x: int = 1) -> int:\n    return x\n",
            "def f(*x: int) -> int:\n    return 1\n",
            "def f(**x: int) -> int:\n    return 1\n",
            "def f(x: int, x: int) -> int:\n    return x\n",
            "def f(x: int = missing()) -> int:\n    return x\n",
        )
        for source in sources:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, "PYC2911")

        required_keyword_only = "def f(*, x: int) -> int:\n    return x\n"
        active = convert(required_keyword_only)
        self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)

        historical = PythonToCConverter().convert(
            ConversionRequest.from_source(
                required_keyword_only,
                rule_set_version=PHASE14C_RULE_SET,
                renderer_version=PHASE14C_RENDERER,
            )
        )
        self.assertEqual(historical.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in historical.diagnostics], ["PYC2911"])

    def test_unsupported_annotation_arity_and_argument_representation_reject(self):
        cases = (
            ("def f(x: object) -> int:\n    return 1\n", "PYC2932"),
            ("def target(x: int) -> int:\n    return x\n\ndef f() -> int:\n    return target()\n", "PYC2904"),
            ("def target(x: int) -> int:\n    return x\n\ndef f(x: bool) -> int:\n    return target(x)\n", "PYC2905"),
        )
        for source, code in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, code)

    def test_return_mismatch_and_fallthrough_reject_distinctly(self):
        cases = (
            ("def f() -> int:\n    return True\n", "PYC2930"),
            ("def f(flag: bool) -> int:\n    if flag:\n        return 1\n", "PYC2931"),
            ("def f() -> int:\n    pass\n", "PYC2931"),
        )
        for source, code in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, code)

    def test_use_before_binding_rejects_as_local_error_not_return_error(self):
        result = convert("def f(x: int) -> int:\n    y = y + x\n    return y\n")
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(result.diagnostics[0].code, "PYC2940")

    def test_nested_functions_and_closures_reject(self):
        source = "def f(x: int) -> int:\n    def nested(y: int) -> int:\n        return x + y\n    return nested(x)\n"
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual(result.diagnostics[0].code, "PYC2915")

    def test_decorated_lambda_and_indirect_targets_reject(self):
        cases = (
            ("@decorator\ndef f(x: int) -> int:\n    return x\n", "PYC2914"),
            ("@decorator()\ndef f(x: int) -> int:\n    return x\n", "PYC2914"),
            ("def f(x: int) -> int:\n    target = lambda y: y\n    return target(x)\n", "PYC2901"),
            ("def f(target: int, x: int) -> int:\n    return target(x)\n", "PYC2901"),
        )
        for source, code in cases:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, code)

    def test_direct_and_mutual_recursion_reject(self):
        sources = (
            "def f(x: int) -> int:\n    return f(x)\n",
            "def f(x: int) -> int:\n    return g(x)\n\ndef g(x: int) -> int:\n    return f(x)\n",
        )
        for source in sources:
            result = convert(source)
            self.assertEqual(result.status, ResultStatus.REJECTED)
            self.assertEqual(result.diagnostics[0].code, "PYC2920")
        count = 150
        large_cycle = "\n".join(
            f"def f{index}(x: int) -> int:\n    return f{(index + 1) % count}(x)\n"
            for index in range(count)
        )
        bounded = convert(large_cycle)
        self.assertEqual(bounded.status, ResultStatus.REJECTED)
        self.assertEqual(bounded.diagnostics[0].code, "PYC2920")

    def test_c_identifier_collisions_are_escaped_deterministically(self):
        source = (
            "def switch(int64_t: int) -> int:\n    bool = int64_t\n    return bool\n\n"
            "def f(x: int) -> int:\n    return switch(x)\n"
        )
        first = convert(source)
        second = convert(source)
        self.assertEqual(first.status, ResultStatus.CONVERTED)
        self.assertEqual(first.generated_c, second.generated_c)
        self.assertIn("py_switch", first.generated_c)
        self.assertIn("py_int64_t", first.generated_c)
        self.assertIn("py_bool", first.generated_c)

    def test_positional_only_parameters_are_supported(self):
        source = (
            "def target(left: int, /, right: int) -> int:\n    return left + right\n\n"
            "def f(a: int, b: int) -> int:\n    return target(a, b)\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        signature = table(result.stage_artifact.payload, "function-signature-facts")["records"]
        self.assertTrue(any(len(item["value"]["parameters"]) == 2 for item in signature))

    def test_string_boundary_records_borrowing_and_const_pointer_types(self):
        source = (
            "def identity(value: str) -> str:\n    return value\n\n"
            "def f() -> str:\n    return identity(\"value\")\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        signatures = [record["value"] for record in table(result.stage_artifact.payload, "function-signature-facts")["records"]]
        identity = next(item for item in signatures if item["source_name"] == "identity")
        self.assertEqual(identity["parameters"][0]["passing"], "borrowed-pointer")
        self.assertEqual(identity["parameters"][0]["ownership"], "borrowed")
        self.assertEqual(identity["return_c_type"], "const char *")
        self.assertIn("const char * identity", result.generated_c)

    def test_generated_c_has_independent_text_conformance(self):
        result = convert()
        conformance = validate_c_text(result.generated_c)
        self.assertTrue(conformance.accepted, conformance.message)
        self.assertGreater(conformance.token_count, 0)

    def test_c_ir_validator_rejects_call_arity_mismatch(self):
        provenance = CProvenance("synthetic")
        target_id = CIdentifier("bind-target", "target", provenance)
        parameter_id = CIdentifier("bind-value", "value", provenance)
        prototype_parameter = CParameter("proto-param", parameter_id, CType("int64_t"), provenance)
        definition_parameter = CParameter("def-param", parameter_id, CType("int64_t"), provenance)
        prototype = CFunctionPrototype("target-proto", target_id, CType("int64_t"), (prototype_parameter,), CStorage.NONE, provenance)
        target_body = CBlock("target-body", (CReturnStatement("target-return", CIdentifierRef("target-ref", "bind-value", provenance), provenance),), provenance)
        target = CFunctionDefinition("target-def", target_id, CType("int64_t"), (definition_parameter,), target_body, CStorage.NONE, provenance)
        caller_id = CIdentifier("bind-caller", "caller", provenance)
        caller_prototype = CFunctionPrototype("caller-proto", caller_id, CType("int64_t"), (), CStorage.NONE, provenance)
        bad_call = CCallExpr("bad-call", CIdentifierRef("callee-ref", "bind-target", provenance), (), provenance)
        caller_body = CBlock("caller-body", (CReturnStatement("caller-return", bad_call, provenance),), provenance)
        caller = CFunctionDefinition("caller-def", caller_id, CType("int64_t"), (), caller_body, CStorage.NONE, provenance)
        builder = CTranslationUnitBuilder("c11-portable-fixed-v1", schema_version=SCHEMA_VERSION, provenance=provenance)
        for declaration in (prototype, caller_prototype, target, caller):
            builder.add_declaration(declaration)
        validation = validate_translation_unit(builder.build())
        self.assertFalse(validation.accepted)
        self.assertTrue(any("argument count" in item for item in validation.errors))

    def test_api_cli_and_workspace_publish_equivalent_c(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "main.py"
            source_path.write_text(BASE, encoding="utf-8")
            direct = convert()
            cli = subprocess.run(
                [sys.executable, "-m", "pycforge", "--format", "json", "convert", str(source_path)],
                cwd=ROOT,
                env=ENV,
                text=True,
                capture_output=True,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertEqual(json.loads(cli.stdout)["generated_c"], direct.generated_c)
            controller = WorkspaceController()
            self.addCleanup(controller.close)
            controller.set_source(BASE)
            workspace = controller.convert()
            self.assertEqual(workspace.generated_c, direct.generated_c)
            self.assertEqual(workspace.output_fingerprint, direct.output_fingerprint)

    def test_observers_cannot_change_phase9_artifacts(self):
        plain = convert()
        noisy = convert(
            observation=ObservationOptions("Full", True),
            inject_trace_failure=True,
            inject_telemetry_failure=True,
        )
        self.assertEqual(plain.semantic_dict(), noisy.semantic_dict())
        self.assertEqual(plain.stage_artifact.artifact_fingerprint, noisy.stage_artifact.artifact_fingerprint)
        self.assertTrue(noisy.decision_trace["observer_failed"])
        self.assertTrue(noisy.telemetry["observer_failed"])
        bounded = PythonToCConverter().convert(
            ConversionRequest.from_source(BASE, resource_policy=ResourcePolicy(max_trace_events=1)),
            observation=ObservationOptions("Summary", False),
        )
        self.assertEqual(bounded.status, ResultStatus.CONVERTED)
        self.assertTrue(bounded.decision_trace["truncated"])
        self.assertIn("PYC8001", {item["code"] for item in bounded.decision_trace["diagnostics"]})
        self.assertNotIn("PYC8001", {item.code for item in bounded.diagnostics})

    def test_cancellation_and_resource_rejection_publish_no_c(self):
        token = CancellationToken()
        token.cancel()
        canceled = convert(cancellation=token)
        self.assertEqual(canceled.status, ResultStatus.CANCELED)
        self.assertIsNone(canceled.generated_c)
        constrained = PythonToCConverter().convert(
            ConversionRequest.from_source(BASE, resource_policy=ResourcePolicy(max_ast_nodes=1))
        )
        self.assertEqual(constrained.status, ResultStatus.REJECTED)
        self.assertIsNone(constrained.generated_c)
        self.assertEqual(constrained.diagnostics[0].code, "PYC3510")

    def test_fresh_process_phase9_output_is_deterministic(self):
        code = (
            "from pycforge import *;"
            f"r=PythonToCConverter().convert(ConversionRequest.from_source({BASE!r}));"
            "print(r.output_fingerprint.value);print(r.stage_artifact.artifact_fingerprint.value)"
        )
        first = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=ENV, text=True)
        second = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=ENV, text=True)
        self.assertEqual(first, second)

    def test_phase9_rule_registry_is_frozen_and_conflict_free(self):
        report = audit_rules(ROOT)
        self.assertTrue(report["passed"], report)
        identities = {(item["rule_id"], item["rule_version"]) for item in report["manifest"]}
        self.assertIn(("phase9.call.understood_target", "0.9"), identities)
        self.assertEqual(report["rule_count"], len(identities))
        transition = audit_transition(ROOT, "phase_9")
        self.assertTrue(transition["passed"], transition)


if __name__ == "__main__":
    unittest.main()
