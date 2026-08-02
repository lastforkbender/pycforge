from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.contracts.configuration import (
    PHASE14C_RENDERER,
    PHASE14C_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    CONVERSION_PLAN_SCHEMA,
    KEYWORD_CALL_FACT_SCHEMA,
)
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.keyword_calls import (
    KeywordCallAnalysisError,
    KeywordCallAnalyzer,
    KeywordCallCIRLowerer,
    KeywordCallLoweringServices,
    KeywordCallValidationCanceled,
    validate_keyword_call_binding_facts,
)


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}

KEYWORD_SOURCE = (
    "def choose(left: int, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool, ratio: float) -> int:\n"
    "    return choose(ratio=ratio, left=value, flag=flag)\n"
)


def convert(
    source: str = KEYWORD_SOURCE,
    *,
    full: bool = False,
    historical: bool = False,
    cancellation=None,
):
    options: dict[str, object] = {}
    if historical:
        options.update(
            rule_set_version=PHASE14C_RULE_SET,
            renderer_version=PHASE14C_RENDERER,
        )
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source, **options),
        observation=ObservationOptions("Full" if full else "None", False),
        cancellation=cancellation,
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def feature_plan(payload: dict) -> dict:
    return next(
        item
        for item in payload["rule_plans"]
        if item["rule_id"] == "phase14.keyword_call.exact_binding"
    )


class Phase14CKeywordHardeningTests(unittest.TestCase):
    def converted(self, source: str = KEYWORD_SOURCE, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.stage_artifact)
        self.assertIsNotNone(result.generated_c)
        return result

    def analysis_payload(self) -> dict:
        payload = json.loads(json.dumps(dict(self.converted().stage_artifact.payload)))
        payload["schema_version"] = CONVERSION_PLAN_SCHEMA
        self.assertEqual(validate_analysis_payload(payload), (True, ""))
        return payload

    def test_closed_rejection_matrix_keeps_specific_primary_diagnostics(self) -> None:
        record = (
            "class Sample:\n"
            "    count: int\n"
            "    def __init__(self, count: int) -> None:\n"
            "        self.count = count\n\n"
            "def run(value: int) -> int:\n"
            "    sample = Sample(count=value)\n"
            "    return value\n"
        )
        cases = (
            (
                "star-positional",
                "def sink(value: int) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(*value)\n",
                "PYC2910",
            ),
            (
                "star-keyword",
                "def sink(value: int) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(**value)\n",
                "PYC2910",
            ),
            (
                "positional-only-name",
                "def sink(value: int, /, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "unknown-name",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(missing=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "positional-keyword-collision",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value, value=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "duplicate-keyword",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag, value=value)\n",
                "PYC2912",
            ),
            (
                "missing-parameter",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value=value)\n",
                "PYC2904",
            ),
            (
                "excess-positional",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value, flag, value)\n",
                "PYC2904",
            ),
            (
                "mapped-category",
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(flag=value, value=flag)\n",
                "PYC2905",
            ),
            (
                "default-target",
                "def sink(value: int, flag: bool = True) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(flag=flag, value=value)\n",
                "PYC2911",
            ),
            (
                "keyword-only-target",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(flag=flag, value=value)\n",
                "PYC2911",
            ),
            (
                "variadic-target",
                "def sink(value: int, *rest: int) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value=value)\n",
                "PYC2911",
            ),
            (
                "range-keyword",
                "def run() -> int:\n"
                "    total = 0\n"
                "    for item in range(stop=3):\n"
                "        total = total + item\n"
                "    return total\n",
                "PYC2842",
            ),
            ("record-constructor-keyword", record, "PYC3605"),
            (
                "dynamic-target",
                "def run(value: int) -> int:\n    return missing(value=value)\n",
                "PYC2901",
            ),
            (
                "recursive-target",
                "def run(value: int) -> int:\n    return run(value=value)\n",
                "PYC2920",
            ),
        )
        for label, source, code in cases:
            with self.subTest(label=label):
                result = convert(
                    source,
                    historical=label == "keyword-only-target",
                )
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertIsNone(result.generated_c)
                self.assertIsNone(result.output_fingerprint)
                self.assertNotIn("c_ir", result.stage_artifact.payload)
                self.assertNotIn("helper_manifest", result.stage_artifact.payload)

    def test_static_binding_rejections_publish_complete_negative_facts(self) -> None:
        cases = (
            (
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(unknown=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value=value)\n",
                "PYC2904",
            ),
            (
                "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=flag, flag=value)\n",
                "PYC2905",
            ),
        )
        for source, code in cases:
            with self.subTest(code=code):
                result = convert(source)
                facts = table(
                    result.stage_artifact.payload,
                    "keyword-call-binding-facts",
                )["records"]
                self.assertEqual(len(facts), 1)
                fact = facts[0]["value"]
                self.assertFalse(fact["supported"])
                self.assertEqual(fact["diagnostic_code"], code)
                self.assertTrue(fact["reason"])
                self.assertTrue(fact["rejection_node_id"])
                self.assertEqual(facts[0]["key"], fact["call_node_id"])

    def test_independent_reconstruction_rejects_fact_coverage_order_and_plan_mutations(self) -> None:
        baseline = self.analysis_payload()

        def record(payload: dict) -> dict:
            return table(payload, "keyword-call-binding-facts")["records"][0]

        def omit_coverage(payload: dict) -> None:
            table(payload, "keyword-call-binding-facts")["records"].clear()

        def erase_provenance(payload: dict) -> None:
            record(payload)["provenance"]["source_node_ids"] = []

        def reverse_source_order(payload: dict) -> None:
            record(payload)["value"]["source_argument_node_ids"].reverse()

        def reverse_evaluation_order(payload: dict) -> None:
            record(payload)["value"]["evaluation_order"].reverse()

        def forge_keyword_name(payload: dict) -> None:
            record(payload)["value"]["keyword_names"][0] = "left"

        def forge_source_mapping(payload: dict) -> None:
            record(payload)["value"]["source_to_parameter_ordinals"] = [0, 1, 2]

        def forge_formal_mapping(payload: dict) -> None:
            record(payload)["value"]["parameter_to_source_ordinals"] = [0, 1, 2]

        def reverse_formal_arguments(payload: dict) -> None:
            record(payload)["value"]["parameter_argument_node_ids"].reverse()

        def forge_argument_binding(payload: dict) -> None:
            record(payload)["value"]["argument_bindings"][0]["parameter_ordinal"] = 0

        def forge_ast_keyword(payload: dict) -> None:
            keyword_id = record(payload)["value"]["keyword_node_ids"][0]
            next(
                item
                for item in payload["python_ir"]["nodes"]
                if item["node_id"] == keyword_id
            )["fields"]["arg"] = "left"

        def remove_plan_fact(payload: dict) -> None:
            facts = feature_plan(payload)["facts_used"]
            facts.remove(
                next(item for item in facts if item.startswith("keyword-call-binding:"))
            )

        def forge_plan_obligations(payload: dict) -> None:
            plan = feature_plan(payload)
            changed = list(plan["semantic_obligations"])
            changed[changed.index("parameter-coverage-exact")] = "forged-obligation"
            plan["semantic_obligations"] = changed
            plan["resolved_obligations"] = list(changed)

        def forge_rule_version(payload: dict) -> None:
            feature_plan(payload)["rule_version"] = "0.14.1"

        mutations = (
            ("coverage", omit_coverage),
            ("provenance", erase_provenance),
            ("source order", reverse_source_order),
            ("evaluation order", reverse_evaluation_order),
            ("keyword spelling", forge_keyword_name),
            ("source mapping", forge_source_mapping),
            ("formal mapping", forge_formal_mapping),
            ("formal arguments", reverse_formal_arguments),
            ("argument binding", forge_argument_binding),
            ("Python IR keyword", forge_ast_keyword),
            ("plan fact", remove_plan_fact),
            ("plan obligations", forge_plan_obligations),
            ("rule version", forge_rule_version),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_analysis_payload(payload)
                self.assertFalse(valid)
                self.assertTrue(reason)

    def test_malformed_tables_dependencies_and_plans_fail_closed(self) -> None:
        baseline = self.analysis_payload()

        def null_tables(payload: dict) -> None:
            payload["fact_tables"] = None

        def malformed_table_item(payload: dict) -> None:
            payload["fact_tables"].append(None)

        def duplicate_dependency_table(payload: dict) -> None:
            payload["fact_tables"].append(deepcopy(table(payload, "binding-facts")))

        def null_dependencies(payload: dict) -> None:
            table(payload, "keyword-call-binding-facts")[
                "invalidation_dependencies"
            ] = None

        def null_keyword_records(payload: dict) -> None:
            table(payload, "keyword-call-binding-facts")["records"] = None

        def null_binding_occurrences(payload: dict) -> None:
            table(payload, "binding-facts")["records"][0]["value"][
                "occurrence_node_ids"
            ] = None

        def null_signature_parameters(payload: dict) -> None:
            table(payload, "function-signature-facts")["records"][0]["value"][
                "parameters"
            ] = None

        def null_call_target_value(payload: dict) -> None:
            table(payload, "call-target-facts")["records"][0]["value"] = None

        def null_rule_plans(payload: dict) -> None:
            payload["rule_plans"] = None

        def malformed_rule_plan_item(payload: dict) -> None:
            payload["rule_plans"].append(None)

        def duplicate_keyword_plan(payload: dict) -> None:
            payload["rule_plans"].append(deepcopy(feature_plan(payload)))

        def null_plan_facts(payload: dict) -> None:
            feature_plan(payload)["facts_used"] = None

        def malformed_source_permutation(payload: dict) -> None:
            table(payload, "keyword-call-binding-facts")["records"][0]["value"][
                "source_to_parameter_ordinals"
            ] = [{}, 0, 1]

        mutations = (
            ("null tables", null_tables),
            ("malformed table item", malformed_table_item),
            ("duplicate dependency table", duplicate_dependency_table),
            ("null dependencies", null_dependencies),
            ("null keyword records", null_keyword_records),
            ("null binding occurrences", null_binding_occurrences),
            ("null signature parameters", null_signature_parameters),
            ("null call target value", null_call_target_value),
            ("null RulePlans", null_rule_plans),
            ("malformed RulePlan item", malformed_rule_plan_item),
            ("duplicate keyword plan", duplicate_keyword_plan),
            ("null plan facts", null_plan_facts),
            ("malformed permutation", malformed_source_permutation),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_keyword_call_binding_facts(payload)
                self.assertFalse(valid)
                self.assertTrue(reason)

        valid, reason = validate_keyword_call_binding_facts(
            deepcopy(baseline),
            tables=7,  # type: ignore[arg-type]
        )
        self.assertFalse(valid)
        self.assertTrue(reason)

    def test_analyzer_malformed_inputs_raise_only_pyc2912(self) -> None:
        cases = (
            (None, (), (), {}),
            ({"root_node_id": "root", "nodes": None}, (), (), {}),
            ({"root_node_id": "root", "nodes": [None]}, (), (), {}),
            ({"root_node_id": "root", "nodes": []}, None, (), {}),
            ({"root_node_id": "root", "nodes": []}, (), None, {}),
            ({"root_node_id": "root", "nodes": []}, (), (), None),
        )
        for module, bindings, signatures, categories in cases:
            with self.subTest(module=module, bindings=bindings):
                with self.assertRaises(KeywordCallAnalysisError) as caught:
                    KeywordCallAnalyzer(
                        module,  # type: ignore[arg-type]
                        bindings=bindings,  # type: ignore[arg-type]
                        signatures=signatures,  # type: ignore[arg-type]
                        categories=categories,  # type: ignore[arg-type]
                        cancellation=None,
                    )
                self.assertEqual(caught.exception.code, "PYC2912")

    def test_lowerer_malformed_facts_signatures_and_permutations_reject_pyc2912(self) -> None:
        baseline = self.analysis_payload()
        fact = deepcopy(
            table(baseline, "keyword-call-binding-facts")["records"][0]["value"]
        )
        call_id = fact["call_node_id"]
        nodes = {item["node_id"]: item for item in baseline["python_ir"]["nodes"]}
        node = deepcopy(nodes[call_id])
        signature = deepcopy(
            next(
                item["value"]
                for item in table(baseline, "function-signature-facts")["records"]
                if item["value"]["binding_id"] == fact["target_binding_id"]
            )
        )

        class LoweringRejected(Exception):
            def __init__(self, code: str) -> None:
                super().__init__(code)
                self.code = code

        def reject(code, _message, _node):
            raise LoweringRejected(code)

        def invoke(candidate_fact, candidate_node, candidate_signature) -> None:
            lowerer = KeywordCallCIRLowerer(
                KeywordCallLoweringServices(
                    nodes=nodes,
                    facts={call_id: candidate_fact},
                    expression=lambda _node: ((), object()),
                    temporary=lambda *_args: (object(), object()),
                    type_from_name=lambda _name: object(),  # type: ignore[arg-type]
                    reject=reject,
                    check_cancellation=lambda: None,
                )
            )
            with self.assertRaises(LoweringRejected) as caught:
                lowerer.arguments(candidate_node, candidate_signature)
            self.assertEqual(caught.exception.code, "PYC2912")

        cases: list[tuple[str, object, object, object]] = []
        cases.append(("null fact", None, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["argument_bindings"] = None
        cases.append(("null bindings", malformed, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["source_to_parameter_ordinals"] = [{}, 0, 1]
        cases.append(("wrong permutation", malformed, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["argument_bindings"][0] = None
        cases.append(("null binding", malformed, deepcopy(node), deepcopy(signature)))
        malformed_signature = deepcopy(signature)
        malformed_signature["parameters"] = None
        cases.append(("null parameters", deepcopy(fact), deepcopy(node), malformed_signature))
        malformed_node = deepcopy(node)
        malformed_node["fields"] = None
        cases.append(("null call fields", deepcopy(fact), malformed_node, deepcopy(signature)))
        for label, candidate_fact, candidate_node, candidate_signature in cases:
            with self.subTest(label=label):
                invoke(candidate_fact, candidate_node, candidate_signature)

    def test_cumulative_target_ineligibility_is_reconstructed_as_pyc2911(self) -> None:
        payload = self.analysis_payload()
        record = table(payload, "keyword-call-binding-facts")["records"][0]
        fact = record["value"]
        call_id = fact["call_node_id"]
        target_id = fact["target_function_node_id"]
        reason = "Keyword-call target is outside the eligible direct source-function profile"
        fact.update(
            runtime_binding_failure="compile-time-rejected",
            supported=False,
            diagnostic_code="PYC2911",
            reason=reason,
            rejection_node_id=target_id,
        )
        target = next(
            item["value"]
            for item in table(payload, "call-target-facts")["records"]
            if item["value"]["call_node_id"] == call_id
        )
        target.update(
            resolution="ineligible-source-function",
            supported=False,
            diagnostic_code="PYC2911",
            reason=reason,
        )
        payload["rule_plans"] = [
            item
            for item in payload["rule_plans"]
            if item.get("source_node_id") != call_id
        ]

        valid_without_override, _ = validate_keyword_call_binding_facts(payload)
        self.assertFalse(valid_without_override)
        self.assertEqual(
            validate_keyword_call_binding_facts(
                payload,
                cumulatively_ineligible_target_function_node_ids=frozenset(
                    {target_id}
                ),
            ),
            (True, ""),
        )

    def test_keyword_algorithms_keep_linear_merge_and_index_shapes(self) -> None:
        analysis_source = (
            ROOT / "pycforge/converter/keyword_calls/analysis.py"
        ).read_text(encoding="utf-8")
        validation_source = (
            ROOT / "pycforge/converter/keyword_calls/validation.py"
        ).read_text(encoding="utf-8")
        lowering_source = (
            ROOT / "pycforge/converter/keyword_calls/lowering.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _merge_source_entries(", analysis_source)
        self.assertIn("def _merge_source_entries(", validation_source)
        self.assertNotIn("source_entries.sort(", analysis_source)
        self.assertNotIn("entries.sort(", validation_source)
        self.assertIn("plans_by_source", validation_source)
        self.assertNotIn("matches = [item for item in plans", validation_source)
        self.assertNotIn("sorted(source_to_parameter)", lowering_source)
        self.assertNotIn("sorted(parameter_to_source)", lowering_source)

    def test_interleaved_starred_negative_fact_preserves_true_source_order(self) -> None:
        source = (
            "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return sink(flag=flag, *value)\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC2910"])
        payload = result.stage_artifact.payload
        fact = table(payload, "keyword-call-binding-facts")["records"][0]["value"]
        by_id = {item["node_id"]: item for item in payload["python_ir"]["nodes"]}
        self.assertEqual(
            [by_id[item]["kind"] for item in fact["source_argument_node_ids"]],
            ["Name", "Starred"],
        )
        self.assertEqual(fact["evaluation_order"], fact["source_argument_node_ids"])

    def test_keyword_validator_propagates_cancellation(self) -> None:
        payload = self.analysis_payload()
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(KeywordCallValidationCanceled):
            validate_keyword_call_binding_facts(
                payload,
                expected_fact_schema=KEYWORD_CALL_FACT_SCHEMA,
                cancellation=token,
            )

    def test_analysis_cancellation_discards_keyword_facts_and_partial_plan(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        real_analyzer = analysis_stage.KeywordCallAnalyzer

        class CancelAfterAnalysis(real_analyzer):
            calls = 0

            def analyze(self):
                product = super().analyze()
                type(self).calls += 1
                self.cancellation.cancel()
                return product

        with patch.object(analysis_stage, "KeywordCallAnalyzer", CancelAfterAnalysis):
            result = convert()

        self.assertEqual(CancelAfterAnalysis.calls, 1)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("analysis.plan", result.stage_order)
        self.assertNotIn("fact_tables", result.stage_artifact.payload)

    def test_wide_keyword_binding_stress_has_complete_unique_linear_coverage(self) -> None:
        call_count = 180
        body = ["    result = seed"]
        body.extend(
            "    result = choose(ratio=ratio, flag=flag, left=result)"
            for _ in range(call_count)
        )
        body.append("    return result")
        source = (
            "def choose(left: int, flag: bool, ratio: float) -> int:\n"
            "    return left\n\n"
            "def run(seed: int, flag: bool, ratio: float) -> int:\n"
            + "\n".join(body)
            + "\n"
        )
        result = self.converted(source)
        records = table(
            result.stage_artifact.payload,
            "keyword-call-binding-facts",
        )["records"]
        self.assertEqual(len(records), call_count)
        self.assertEqual(
            [item["key"] for item in records],
            sorted(item["key"] for item in records),
        )
        self.assertEqual(len({item["value"]["binding_id"] for item in records}), call_count)
        self.assertTrue(all(item["value"]["supported"] for item in records))
        self.assertTrue(
            all(
                item["value"]["source_to_parameter_ordinals"] == [2, 1, 0]
                for item in records
            )
        )

    def test_full_artifacts_are_fresh_process_deterministic(self) -> None:
        script = (
            "from pycforge import ConversionRequest,PythonToCConverter\n"
            "from pycforge.converter.core.request import ObservationOptions\n"
            "from pycforge.converter.core.serialization import result_to_json\n"
            f"source={KEYWORD_SOURCE!r}\n"
            "result=PythonToCConverter().convert(ConversionRequest.from_source(source),"
            "observation=ObservationOptions('Full',False))\n"
            "print(result_to_json(result),end='')\n"
        )
        outputs = [
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=ENV,
                text=True,
            )
            for _ in range(2)
        ]
        self.assertEqual(outputs[0], outputs[1])
        result = self.converted(full=True)
        repeated = self.converted(full=True)
        self.assertEqual(result.generated_c, repeated.generated_c)
        self.assertEqual(result.output_fingerprint, repeated.output_fingerprint)
        self.assertEqual(result.stage_artifact.payload, repeated.stage_artifact.payload)
        self.assertEqual(result.conversion_summary, repeated.conversion_summary)
        self.assertEqual(result.decision_trace, repeated.decision_trace)


if __name__ == "__main__":
    unittest.main()
