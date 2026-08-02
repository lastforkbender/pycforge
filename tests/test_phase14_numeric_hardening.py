from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.contracts.configuration import (
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    CONVERSION_PLAN_SCHEMA,
    PHASE13_C_IR_SCHEMA,
    PHASE13_CONVERSION_SUMMARY_SCHEMA,
    PHASE13_DECISION_TRACE_SCHEMA,
    PHASE13_GENERATED_C_SCHEMA,
)
from pycforge.converter.core.artifact_io import (
    ArtifactCompatibilityError,
    artifact_from_dict,
    artifact_to_dict,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.lowering import LoweringCanceled
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
)


SOURCE = (
    "def run(value: int) -> int:\n"
    "    return (value // -3) + (value % 5)\n"
)


def convert(source: str = SOURCE, *, full: bool = False):
    observation = ObservationOptions("Full", False) if full else None
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source),
        observation=observation,
    )


def table(payload: dict, table_id: str) -> dict:
    return next(
        item for item in payload["fact_tables"] if item["table_id"] == table_id
    )


def walk(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from walk(child)


class Phase14NumericHardeningTests(unittest.TestCase):
    def converted(self, source: str = SOURCE, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.stage_artifact)
        return result

    def analysis_payload(self) -> dict:
        result = self.converted()
        assert result.stage_artifact is not None
        # Exercise the same JSON surface used by persisted artifacts.  The
        # generated-C payload cumulatively contains the conversion plan.
        payload = json.loads(json.dumps(dict(result.stage_artifact.payload)))
        payload["schema_version"] = CONVERSION_PLAN_SCHEMA
        self.assertEqual(validate_analysis_payload(payload), (True, ""))
        return payload

    def test_numeric_left_preserves_established_nested_call_rejections(self):
        cases = (
            (
                "def recursive(value: int) -> int:\n"
                "    return recursive(value) // 2\n",
                "PYC2920",
            ),
            (
                "def target(value: int) -> int:\n"
                "    return value\n\n"
                "def run(value: int) -> int:\n"
                "    return target(value, value) % 2\n",
                "PYC2904",
            ),
        )
        for source, code in cases:
            with self.subTest(code=code):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertIsNone(result.generated_c)
                self.assertIsNone(result.output_fingerprint)

    def test_serialized_artifact_round_trips_and_detects_numeric_fact_tampering(self):
        result = self.converted()
        assert result.stage_artifact is not None
        envelope = json.loads(json.dumps(artifact_to_dict(result.stage_artifact)))
        loaded = artifact_from_dict(
            deepcopy(envelope),
            accepted={("generated_c", "0.14.3")},
        )
        self.assertEqual(
            loaded.artifact_fingerprint,
            result.stage_artifact.artifact_fingerprint,
        )
        self.assertEqual(
            loaded.payload["helper_requirements"],
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )

        numeric = table(envelope["payload"], "numeric-operation-facts")
        numeric["records"][0]["value"]["divisor_value"] = 17
        with self.assertRaisesRegex(ArtifactCompatibilityError, "PYC3105"):
            artifact_from_dict(
                envelope,
                accepted={("generated_c", "0.14.3")},
            )

    def test_independent_numeric_reproof_rejects_adversarial_serialized_evidence(self):
        baseline = self.analysis_payload()

        def numeric_records(payload: dict) -> list[dict]:
            return table(payload, "numeric-operation-facts")["records"]

        def fact(payload: dict, operator_kind: str) -> dict:
            return next(
                record["value"]
                for record in numeric_records(payload)
                if record["value"]["operator_kind"] == operator_kind
            )

        def corrupt_divisor(payload: dict) -> None:
            fact(payload, "floor-divide")["divisor_value"] = -4

        def swap_fact_helper(payload: dict) -> None:
            fact(payload, "floor-divide")[
                "helper_requirement"
            ] = FLOOR_MOD_REFERENCE.canonical

        def reverse_evaluation(payload: dict) -> None:
            fact(payload, "floor-divide")["evaluation_order"].reverse()

        def duplicate_operand_evaluation(payload: dict) -> None:
            fact(payload, "floor-divide")["operands_evaluated_once"] = False

        def forge_category(payload: dict) -> None:
            fact(payload, "floor-divide")["left_category"] = "boolean-like"

        def forge_operation_identity(payload: dict) -> None:
            fact(payload, "floor-divide")["operation_id"] = "numeric-op-forged"

        def remove_provenance(payload: dict) -> None:
            record = next(
                record
                for record in numeric_records(payload)
                if record["value"]["operator_kind"] == "floor-divide"
            )
            literal_ids = set(record["value"]["divisor_literal_node_ids"])
            record["provenance"]["source_node_ids"] = [
                node_id
                for node_id in record["provenance"]["source_node_ids"]
                if node_id not in literal_ids
            ]

        def omit_operation(payload: dict) -> None:
            numeric_records(payload).pop()

        def make_serialized_divisor_unsafe(payload: dict) -> None:
            operation = fact(payload, "floor-modulo")
            right = next(
                node
                for node in payload["python_ir"]["nodes"]
                if node["node_id"] == operation["right_node_id"]
            )
            right["fields"]["value"] = 0

        def swap_plan_helpers(payload: dict) -> None:
            for plan in payload["rule_plans"]:
                if plan["rule_id"] != "phase14.numeric.floor_arithmetic":
                    continue
                plan["helper_requirements"] = [
                    FLOOR_MOD_REFERENCE.canonical
                    if plan["helper_requirements"] == [FLOOR_DIV_REFERENCE.canonical]
                    else FLOOR_DIV_REFERENCE.canonical
                ]

        def erase_plan_proof(payload: dict) -> None:
            plan = next(
                item
                for item in payload["rule_plans"]
                if item["rule_id"] == "phase14.numeric.floor_arithmetic"
            )
            operation = next(
                item
                for item in plan["facts_used"]
                if item.startswith("numeric-operation:")
            )
            plan["facts_used"] = [operation, "value-category:integer-like"]
            plan["semantic_obligations"] = []
            plan["resolved_obligations"] = []
            plan["explanation_tokens"] = []

        def let_non_numeric_plan_claim_helper(payload: dict) -> None:
            plan = next(
                item
                for item in payload["rule_plans"]
                if item["rule_id"] != "phase14.numeric.floor_arithmetic"
            )
            plan["helper_requirements"] = [FLOOR_DIV_REFERENCE.canonical]

        mutations = (
            ("divisor value", corrupt_divisor, "disagrees with independent proof"),
            ("helper identity", swap_fact_helper, "disagrees with independent proof"),
            ("evaluation order", reverse_evaluation, "disagrees with independent proof"),
            (
                "evaluate once",
                duplicate_operand_evaluation,
                "disagrees with independent proof",
            ),
            ("category", forge_category, "disagrees with independent proof"),
            ("operation identity", forge_operation_identity, "disagrees with independent proof"),
            ("provenance", remove_provenance, "provenance is incomplete"),
            ("coverage", omit_operation, "do not exactly cover"),
            ("serialized literal", make_serialized_divisor_unsafe, "divisor proof is unsafe"),
            ("plan helper", swap_plan_helpers, "does not close its helper proof"),
            ("plan proof", erase_plan_proof, "does not close its helper proof"),
            (
                "helper ownership",
                let_non_numeric_plan_claim_helper,
                "non-numeric RulePlan claims",
            ),
        )
        for label, mutate, reason_fragment in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_analysis_payload(payload)
                self.assertFalse(valid)
                self.assertIn(reason_fragment, reason)

    def test_numeric_analysis_cancellation_discards_an_already_computed_fact(self):
        from pycforge.converter.analysis import stage as analysis_stage

        real_analyzer = analysis_stage.BoundedNumericAnalyzer

        class CancelAfterOneFact(real_analyzer):
            calls = 0

            def _operation(self, node, operator):
                result = super()._operation(node, operator)
                type(self).calls += 1
                if type(self).calls == 1:
                    self.cancellation.cancel()
                return result

        with patch.object(
            analysis_stage,
            "BoundedNumericAnalyzer",
            CancelAfterOneFact,
        ):
            result = convert()

        self.assertEqual(CancelAfterOneFact.calls, 1)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertIsNone(result.generated_c)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertFalse(any(item.code.startswith("PYC37") for item in result.diagnostics))
        self.assertIsNotNone(result.stage_artifact)
        assert result.stage_artifact is not None
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("fact_tables", result.stage_artifact.payload)

    def test_numeric_lowering_cancellation_publishes_no_partial_c_or_helper_manifest(self):
        def cancel_operation(_self, _node):
            raise LoweringCanceled

        with patch(
            "pycforge.converter.numeric_semantics.lowering.NumericCIRLowerer.operation",
            cancel_operation,
        ):
            result = convert()

        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertIsNone(result.generated_c)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNotNone(result.stage_artifact)
        assert result.stage_artifact is not None
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(
            result.stage_artifact.payload["helper_requirements"],
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )
        self.assertNotIn("c_ir", result.stage_artifact.payload)
        self.assertNotIn("generated_c", result.stage_artifact.payload)
        self.assertNotIn("helper_manifest", result.stage_artifact.payload)

    def test_repeated_operations_use_exact_helpers_and_deduplicate_helper_c_ir(self):
        source = (
            "def run(value: int) -> int:\n"
            "    return ((value // 2) // 3) + ((value % 4) % -5)\n"
        )
        result = self.converted(source)
        assert result.stage_artifact is not None
        payload = result.stage_artifact.payload
        self.assertEqual(
            payload["helper_requirements"],
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )
        self.assertEqual(
            [item["reference"] for item in payload["helper_manifest"]],
            [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical],
        )

        c_nodes = list(walk(payload["c_ir"]))
        helper_bindings = {
            FLOOR_DIV_REFERENCE.canonical:
                f"helper-binding:{FLOOR_DIV_REFERENCE.canonical}:function",
            FLOOR_MOD_REFERENCE.canonical:
                f"helper-binding:{FLOOR_MOD_REFERENCE.canonical}:function",
        }
        prototypes = [
            node for node in c_nodes if node.get("kind") == "CFunctionPrototype"
        ]
        definitions = [
            node for node in c_nodes if node.get("kind") == "CFunctionDefinition"
        ]
        for binding_id in helper_bindings.values():
            self.assertEqual(
                sum(
                    item.get("identifier", {}).get("binding_id") == binding_id
                    for item in prototypes
                ),
                1,
            )
            self.assertEqual(
                sum(
                    item.get("identifier", {}).get("binding_id") == binding_id
                    for item in definitions
                ),
                1,
            )

        calls = [
            node
            for node in c_nodes
            if node.get("kind") == "CCallExpr"
            and node.get("callee", {}).get("binding_id") in helper_bindings.values()
        ]
        self.assertEqual(len(calls), 4)
        self.assertEqual(
            [item["callee"]["binding_id"] for item in calls].count(
                helper_bindings[FLOOR_DIV_REFERENCE.canonical]
            ),
            2,
        )
        self.assertEqual(
            [item["callee"]["binding_id"] for item in calls].count(
                helper_bindings[FLOOR_MOD_REFERENCE.canonical]
            ),
            2,
        )
        self.assertTrue(
            all(
                len(item["arguments"]) == 2
                and all(argument["kind"] == "CIdentifierRef" for argument in item["arguments"])
                for item in calls
            )
        )
        result_declarations = [
            node
            for node in c_nodes
            if node.get("kind") == "CVariableDeclaration"
            and node.get("initializer", {}).get("node_id")
            in {call["node_id"] for call in calls}
        ]
        self.assertEqual(len(result_declarations), 4)
        self.assertTrue(
            all(item["type_ref"]["base"] == "int64_t" for item in result_declarations)
        )

    def test_full_numeric_artifacts_are_deterministic(self):
        first = self.converted(full=True)
        second = self.converted(full=True)
        assert first.stage_artifact is not None
        assert second.stage_artifact is not None
        self.assertEqual(first.generated_c, second.generated_c)
        self.assertEqual(first.output_fingerprint, second.output_fingerprint)
        self.assertEqual(
            first.stage_artifact.artifact_fingerprint,
            second.stage_artifact.artifact_fingerprint,
        )
        self.assertEqual(first.stage_artifact.payload, second.stage_artifact.payload)
        self.assertEqual(first.conversion_summary, second.conversion_summary)
        self.assertEqual(first.decision_trace, second.decision_trace)

    def test_explicit_phase13_request_remains_historical_and_output_compatible(self):
        source = (
            "class Box:\n"
            "    value: int\n"
            "    def __init__(self, value: int) -> None:\n"
            "        self.value = value\n"
            "\n"
            "def run() -> int:\n"
            "    box = Box(7)\n"
            "    return box.value\n"
        )
        active = self.converted(source, full=True)
        historical = PythonToCConverter().convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE13_RULE_SET,
                renderer_version=PHASE13_RENDERER,
            ),
            observation=ObservationOptions("Full", False),
        )
        self.assertEqual(historical.status, ResultStatus.CONVERTED, historical.diagnostics)
        self.assertEqual(historical.diagnostics, ())
        self.assertEqual(active.generated_c, historical.generated_c)
        self.assertIsNotNone(historical.stage_artifact)
        assert historical.stage_artifact is not None
        payload = historical.stage_artifact.payload
        self.assertEqual(historical.stage_artifact.schema_version, "0.13")
        self.assertEqual(payload["schema_version"], PHASE13_GENERATED_C_SCHEMA)
        self.assertEqual(payload["c_ir_schema"], PHASE13_C_IR_SCHEMA)
        self.assertEqual(
            historical.conversion_summary["schema_version"],
            PHASE13_CONVERSION_SUMMARY_SCHEMA,
        )
        self.assertEqual(
            historical.decision_trace["schema_version"],
            PHASE13_DECISION_TRACE_SCHEMA,
        )
        for observer in (payload, historical.conversion_summary, historical.decision_trace):
            self.assertNotIn("numeric_policy_version", observer)
        self.assertNotIn(
            "numeric-operation-facts",
            {item["table_id"] for item in payload["fact_tables"]},
        )
        self.assertEqual(payload["helper_requirements"], [])
        self.assertEqual(payload["helper_manifest"], [])


if __name__ == "__main__":
    unittest.main()
