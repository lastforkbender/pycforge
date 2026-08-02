from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.conditional_regions import (
    ConditionalRegionValidationCanceled,
    validate_conditional_region_facts,
)
from pycforge.converter.contracts.configuration import (
    PHASE14A_RENDERER,
    PHASE14A_RULE_SET,
    PHASE14B_RENDERER,
    PHASE14B_RULE_SET,
)
from pycforge.converter.contracts.versions import CONVERSION_PLAN_SCHEMA
from pycforge.converter.core.artifact_io import (
    artifact_from_dict,
    artifact_to_dict,
)
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.lowering import LoweringCanceled
from pycforge.converter.support_templates import FLOOR_DIV_REFERENCE


BOOLEAN_SOURCE = (
    "def flag(value: bool) -> bool:\n"
    "    return value\n\n"
    "def run(a: bool, b: bool, c: bool) -> bool:\n"
    "    return flag(a) and flag(b) and flag(c)\n"
)


def convert(
    source: str = BOOLEAN_SOURCE,
    *,
    full: bool = False,
    rule_set_version: str | None = None,
    renderer_version: str | None = None,
):
    request_options = {}
    if rule_set_version is not None:
        request_options["rule_set_version"] = rule_set_version
    if renderer_version is not None:
        request_options["renderer_version"] = renderer_version
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source, **request_options),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def conditional_plan(payload: dict) -> dict:
    return next(
        item
        for item in payload["rule_plans"]
        if item["rule_id"].startswith("phase14.conditional.")
    )


def walk(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from walk(child)


class Phase14BConditionalHardeningTests(unittest.TestCase):
    def converted(self, source: str = BOOLEAN_SOURCE, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.stage_artifact)
        self.assertIsNotNone(result.generated_c)
        return result

    def analysis_payload(self) -> dict:
        result = self.converted()
        payload = json.loads(json.dumps(dict(result.stage_artifact.payload)))
        payload["schema_version"] = CONVERSION_PLAN_SCHEMA
        self.assertEqual(validate_analysis_payload(payload), (True, ""))
        return payload

    def test_more_specific_root_causes_keep_precedence_over_placement_diagnostics(self) -> None:
        cases = (
            (
                "unknown-target",
                "def run(a: bool, b: bool) -> bool:\n"
                "    return a and missing(b)\n",
                "PYC2901",
            ),
            (
                "arity",
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    return a and flag(b, b)\n",
                "PYC2904",
            ),
            (
                "recursion",
                "def run(a: bool) -> bool:\n"
                "    return a and run(a)\n",
                "PYC2920",
            ),
            (
                "return-category",
                "def flag(v: bool) -> bool:\n    return 1\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    return a and flag(b)\n",
                "PYC2930",
            ),
            (
                "dynamic-index",
                "def run(a: int, b: int, index: int) -> bool:\n"
                "    values = [1, 2]\n"
                "    return a < b < values[index]\n",
                "PYC3404",
            ),
            (
                "unsafe-divisor",
                "def run(a: int, b: int, c: int) -> bool:\n"
                "    return a < b < (c // 0)\n",
                "PYC3702",
            ),
        )
        for name, source, code in cases:
            with self.subTest(name=name):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertNotIn(code, {"PYC2950", "PYC2951"})
                self.assertIsNone(result.generated_c)
                self.assertIsNone(result.output_fingerprint)

    def test_active_keyword_call_composes_with_regions_and_phase14b_stays_frozen(self) -> None:
        source = (
            "def flag(v: bool) -> bool:\n    return v\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return a and flag(v=b)\n"
        )
        active = convert(source)
        self.assertEqual(active.status, ResultStatus.CONVERTED, active.diagnostics)

        historical = convert(
            source,
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        )
        self.assertEqual(historical.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in historical.diagnostics], ["PYC2910"])
        self.assertIsNone(historical.generated_c)
        self.assertIsNone(historical.output_fingerprint)

    def test_independent_reconstruction_rejects_conditional_fact_and_plan_mutations(self) -> None:
        baseline = self.analysis_payload()

        def record(payload: dict) -> dict:
            return table(payload, "conditional-region-facts")["records"][0]

        def mutate_guard(payload: dict) -> None:
            record(payload)["value"]["placements"][1]["guard_polarity"] = "when-result-false"

        def mutate_operand_order(payload: dict) -> None:
            record(payload)["value"]["operand_node_ids"].reverse()

        def mutate_prefix(payload: dict) -> None:
            record(payload)["value"]["unconditional_prefix_count"] = 2

        def omit_region(payload: dict) -> None:
            table(payload, "conditional-region-facts")["records"].clear()

        def erase_provenance(payload: dict) -> None:
            record(payload)["provenance"]["source_node_ids"] = []

        def mutate_operator_fact(payload: dict) -> None:
            record(payload)["value"]["operator_kinds"] = ["Or"]

        def mutate_ast_operator(payload: dict) -> None:
            operator_id = record(payload)["value"]["operator_node_ids"][0]
            next(
                item
                for item in payload["python_ir"]["nodes"]
                if item["node_id"] == operator_id
            )["kind"] = "Or"

        def remove_plan_fact(payload: dict) -> None:
            conditional_plan(payload)["facts_used"].pop()

        def mutate_plan_obligations(payload: dict) -> None:
            plan = conditional_plan(payload)
            changed = [*plan["semantic_obligations"][:-1], "forged-obligation"]
            plan["semantic_obligations"] = changed
            plan["resolved_obligations"] = list(changed)

        def claim_region_helper(payload: dict) -> None:
            helper = FLOOR_DIV_REFERENCE.canonical
            conditional_plan(payload)["helper_requirements"] = [helper]
            payload["helper_requirements"] = [helper]

        mutations = (
            ("guard polarity", mutate_guard),
            ("operand order", mutate_operand_order),
            ("unconditional prefix", mutate_prefix),
            ("coverage", omit_region),
            ("provenance", erase_provenance),
            ("operator fact", mutate_operator_fact),
            ("serialized operator", mutate_ast_operator),
            ("plan facts", remove_plan_fact),
            ("plan obligations", mutate_plan_obligations),
            ("region helper ownership", claim_region_helper),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_analysis_payload(payload)
                self.assertFalse(valid)
                self.assertTrue(reason)

    def test_conditional_analysis_cancellation_discards_computed_region(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        real_analyzer = analysis_stage.ConditionalRegionAnalyzer

        class CancelAfterRegion(real_analyzer):
            calls = 0

            def _region(self, node, kind):
                result = super()._region(node, kind)
                type(self).calls += 1
                self.cancellation.cancel()
                return result

        with patch.object(
            analysis_stage,
            "ConditionalRegionAnalyzer",
            CancelAfterRegion,
        ):
            result = convert()

        self.assertEqual(CancelAfterRegion.calls, 1)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertEqual(result.stage_artifact.schema_version, "0.4")
        self.assertNotIn("analysis.plan", result.stage_order)
        self.assertNotIn("fact_tables", result.stage_artifact.payload)

    def test_independent_validator_propagates_cancellation_as_cancellation(self) -> None:
        payload = self.analysis_payload()
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(ConditionalRegionValidationCanceled):
            validate_conditional_region_facts(
                payload,
                expected_fact_schema="fact-table/0.14.1",
                cancellation=token,
            )

    def test_stage_validation_cancellation_retires_unpublished_conversion_plan(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        token = CancellationToken()
        calls = 0

        def cancel_during_stage_validation(payload, cancellation=None):
            nonlocal calls
            calls += 1
            self.assertIs(cancellation, token)
            if calls == 1:
                return True, ""
            token.cancel()
            raise ConditionalRegionValidationCanceled

        with patch.object(
            analysis_stage,
            "validate_analysis_payload",
            cancel_during_stage_validation,
        ):
            result = PythonToCConverter().convert(
                ConversionRequest.from_source(BOOLEAN_SOURCE),
                cancellation=token,
            )

        self.assertEqual(calls, 2)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("fact_tables", result.stage_artifact.payload)

    def test_conditional_lowering_cancellation_publishes_no_partial_successor(self) -> None:
        def cancel_region(_self, _node, _fact):
            raise LoweringCanceled

        with patch(
            "pycforge.converter.conditional_regions.lowering.ConditionalRegionCIRLowerer._guarded_boolean",
            cancel_region,
        ):
            result = convert()

        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertIn(
            "conditional-region-facts",
            {item["table_id"] for item in result.stage_artifact.payload["fact_tables"]},
        )
        self.assertNotIn("c_ir", result.stage_artifact.payload)
        self.assertNotIn("generated_c", result.stage_artifact.payload)
        self.assertNotIn("helper_manifest", result.stage_artifact.payload)
        self.assertNotIn("source_output_mappings", result.stage_artifact.payload)

    def test_full_artifacts_observers_and_mappings_are_deterministic(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def value(item: int) -> int:\n"
            "    return item\n\n"
            "def bool_run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return a and (b or flag(c))\n\n"
            "def chain_run(a: int, b: int, c: int) -> bool:\n"
            "    return a < b < (value(c) // 2)\n"
        )
        first = self.converted(source, full=True)
        second = self.converted(source, full=True)
        self.assertEqual(first.generated_c, second.generated_c)
        self.assertEqual(first.output_fingerprint, second.output_fingerprint)
        self.assertEqual(
            first.stage_artifact.artifact_fingerprint,
            second.stage_artifact.artifact_fingerprint,
        )
        self.assertEqual(first.stage_artifact.payload, second.stage_artifact.payload)
        self.assertEqual(first.conversion_summary, second.conversion_summary)
        self.assertEqual(first.decision_trace, second.decision_trace)
        self.assertEqual(
            first.stage_artifact.payload["source_output_mappings"],
            second.stage_artifact.payload["source_output_mappings"],
        )

    def test_no_region_active_output_is_byte_identical_to_authenticated_phase14a(self) -> None:
        source = "def run() -> int:\n    return 1\n"
        active = self.converted(source, full=True)
        historical = convert(
            source,
            full=True,
            rule_set_version=PHASE14A_RULE_SET,
            renderer_version=PHASE14A_RENDERER,
        )
        self.assertEqual(historical.status, ResultStatus.CONVERTED, historical.diagnostics)
        self.assertEqual(active.generated_c, historical.generated_c)
        self.assertEqual(active.output_fingerprint, historical.output_fingerprint)
        self.assertEqual(
            hashlib.sha256((historical.generated_c or "").encode("utf-8")).hexdigest(),
            "0ba73812646f4113b99bbe72661d7a7eef129901439422cc2d47bbc6ddaa64c5",
        )
        self.assertEqual(
            historical.output_fingerprint.value,
            "27f2abb910f41170714de587158e2eacc66ef81d8535b28a754f5f960e9b6f0d",
        )
        self.assertEqual(
            historical.request_fingerprint.value,
            "f3bdc058becb0854692235850037797872afc00a18a132c88b7bb2950a2d4360",
        )
        payload = historical.stage_artifact.payload
        self.assertEqual(historical.stage_artifact.schema_version, "0.14")
        self.assertEqual(payload["schema_version"], "generated-c/0.14")
        self.assertEqual(payload["c_ir_schema"], "c-ir/0.14")
        self.assertEqual(
            historical.conversion_summary["schema_version"],
            "pycforge.conversion-summary/0.14",
        )
        self.assertEqual(
            historical.decision_trace["schema_version"],
            "pycforge.decision-trace/0.14",
        )
        self.assertNotIn(
            "conditional-region-facts",
            {item["table_id"] for item in payload["fact_tables"]},
        )
        self.assertNotIn("conditional_regions", historical.conversion_summary)
        self.assertNotIn("conditional_regions", historical.decision_trace)

    def test_active_artifact_round_trips_under_the_exact_new_envelope(self) -> None:
        result = self.converted()
        envelope = json.loads(json.dumps(artifact_to_dict(result.stage_artifact)))
        loaded = artifact_from_dict(
            envelope,
            accepted={("generated_c", "0.14.3")},
        )
        self.assertEqual(loaded.artifact_fingerprint, result.stage_artifact.artifact_fingerprint)
        self.assertEqual(loaded.payload["schema_version"], "generated-c/0.14.3")
        self.assertEqual(loaded.payload["c_ir_schema"], "c-ir/0.14.3")

    def test_wide_boolean_region_has_no_arbitrary_64_operand_cap_or_nested_guards(self) -> None:
        operand_count = 70
        parameters = ", ".join(f"v{index}: bool" for index in range(operand_count))
        expression = " and ".join(f"flag(v{index})" for index in range(operand_count))
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            f"def run({parameters}) -> bool:\n"
            f"    return {expression}\n"
        )
        result = self.converted(source)
        run = next(
            item
            for item in result.stage_artifact.payload["c_ir"]["declarations"]
            if item.get("kind") == "CFunctionDefinition"
            and item.get("identifier", {}).get("spelling") == "run"
        )
        direct_guards = [
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        ]
        self.assertEqual(len(direct_guards), operand_count - 1)
        self.assertTrue(
            all(
                not any(
                    child.get("node_id", "").startswith("c-bool-region-if-")
                    for statement in guard["then_block"]["statements"]
                    for child in ([statement] if isinstance(statement, dict) else [])
                )
                for guard in direct_guards
            )
        )

    def test_deep_nested_call_prerequisite_closure_remains_bounded_and_guarded(self) -> None:
        depth = 110
        expression = "b"
        for _ in range(depth):
            expression = f"identity({expression})"
        source = (
            "def identity(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            f"    return a and {expression}\n"
        )
        result = self.converted(source)
        payload = result.stage_artifact.payload
        region = table(payload, "conditional-region-facts")["records"][0]["value"]
        self.assertEqual(len(region["placements"][1]["prerequisite_node_ids"]), depth)
        run = next(
            item
            for item in payload["c_ir"]["declarations"]
            if item.get("kind") == "CFunctionDefinition"
            and item.get("identifier", {}).get("spelling") == "run"
        )
        guard = next(
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        )
        guarded_calls = [
            item for item in walk(guard["then_block"]) if item.get("kind") == "CCallExpr"
        ]
        all_run_calls = [
            item for item in walk(run) if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(len(guarded_calls), depth)
        self.assertEqual(guarded_calls, all_run_calls)


if __name__ == "__main__":
    unittest.main()
