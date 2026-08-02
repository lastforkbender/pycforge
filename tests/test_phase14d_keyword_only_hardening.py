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
from pycforge.converter.contracts.versions import (
    CONVERSION_PLAN_SCHEMA,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
)
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.keyword_only_calls import (
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_TABLE_ID,
    KeywordOnlyCallAnalysisError,
    KeywordOnlyCallAnalyzer,
    KeywordOnlyCallCIRLowerer,
    KeywordOnlyCallLoweringServices,
    KeywordOnlyCallValidationCanceled,
    validate_keyword_only_call_binding_facts,
)


ROOT = Path(__file__).resolve().parents[1]
ENV = {
    **os.environ,
    "PYTHONPATH": str(ROOT),
    "PYTHONDONTWRITEBYTECODE": "1",
}

KEYWORD_ONLY_SOURCE = (
    "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool, ratio: float) -> int:\n"
    "    return choose(ratio=ratio, left=value, flag=flag)\n"
)


def convert(
    source: str = KEYWORD_ONLY_SOURCE,
    *,
    full: bool = False,
    cancellation=None,
):
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source),
        observation=ObservationOptions("Full" if full else "None", False),
        cancellation=cancellation,
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def feature_plan(payload: dict) -> dict:
    return next(
        item
        for item in payload["rule_plans"]
        if item["rule_id"] == KEYWORD_ONLY_CALL_RULE_ID
    )


class Phase14DKeywordOnlyHardeningTests(unittest.TestCase):
    def converted(self, source: str = KEYWORD_ONLY_SOURCE, *, full: bool = False):
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
                "no-keyword-missing-required",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value)\n",
                "PYC2904",
            ),
            (
                "missing-keyword-only",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value=value)\n",
                "PYC2904",
            ),
            (
                "keyword-only-passed-positionally",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value, flag)\n",
                "PYC2904",
            ),
            (
                "unknown-name",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, missing=flag)\n",
                "PYC2912",
            ),
            (
                "positional-only-name",
                "def sink(value: int, /, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "positional-keyword-collision",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value, value=value, flag=flag)\n",
                "PYC2912",
            ),
            (
                "duplicate-keyword-only",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag, flag=flag)\n",
                "PYC2912",
            ),
            (
                "category-mismatch",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=value)\n",
                "PYC2905",
            ),
            (
                "star-positional",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(*value, flag=flag)\n",
                "PYC2910",
            ),
            (
                "star-keyword",
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, **flag)\n",
                "PYC2910",
            ),
            (
                "keyword-only-default",
                "def sink(value: int, *, flag: bool = True) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag)\n",
                "PYC2911",
            ),
            (
                "positional-default",
                "def sink(value: int = 1, *, flag: bool) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=flag)\n",
                "PYC2911",
            ),
            (
                "variadic-target",
                "def sink(value: int, *rest: int, flag: bool) -> int:\n"
                "    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value, flag=flag)\n",
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
                "def run(value: int, *, flag: bool) -> int:\n"
                "    return run(value=value, flag=flag)\n",
                "PYC2920",
            ),
        )
        for label, source, code in cases:
            with self.subTest(label=label):
                result = convert(source)
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                self.assertIsNone(result.generated_c)
                self.assertIsNone(result.output_fingerprint)
                self.assertNotIn("c_ir", result.stage_artifact.payload)
                self.assertNotIn("helper_manifest", result.stage_artifact.payload)

    def test_binding_rejections_publish_complete_negative_facts(self) -> None:
        cases = (
            (
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int) -> int:\n    return sink(value)\n",
                "PYC2904",
            ),
            (
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, unknown=flag)\n",
                "PYC2912",
            ),
            (
                "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return sink(value=value, flag=value)\n",
                "PYC2905",
            ),
        )
        for source, code in cases:
            with self.subTest(code=code):
                result = convert(source)
                records = table(
                    result.stage_artifact.payload,
                    KEYWORD_ONLY_CALL_TABLE_ID,
                )["records"]
                self.assertEqual(len(records), 1)
                fact = records[0]["value"]
                self.assertFalse(fact["supported"])
                self.assertEqual(fact["diagnostic_code"], code)
                self.assertTrue(fact["reason"])
                self.assertTrue(fact["rejection_node_id"])
                self.assertEqual(records[0]["key"], fact["call_node_id"])
                self.assertEqual(
                    fact["runtime_binding_failure"],
                    "compile-time-rejected",
                )

    def test_independent_reconstruction_rejects_order_kind_and_plan_tampering(self) -> None:
        baseline = self.analysis_payload()

        def record(payload: dict) -> dict:
            return table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"][0]

        def omit_coverage(payload: dict) -> None:
            table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"].clear()

        def erase_provenance(payload: dict) -> None:
            record(payload)["provenance"]["source_node_ids"] = []

        def reverse_source_order(payload: dict) -> None:
            record(payload)["value"]["source_argument_node_ids"].reverse()

        def reverse_evaluation_order(payload: dict) -> None:
            record(payload)["value"]["evaluation_order"].reverse()

        def forge_keyword_name(payload: dict) -> None:
            record(payload)["value"]["keyword_names"][0] = "left"

        def forge_parameter_kind(payload: dict) -> None:
            record(payload)["value"]["parameter_kinds"][-1] = "positional-or-keyword"

        def erase_required_keyword_only(payload: dict) -> None:
            record(payload)["value"]["required_keyword_only_parameter_names"] = []

        def forge_source_mapping(payload: dict) -> None:
            record(payload)["value"]["source_to_parameter_ordinals"] = [0, 1, 2]

        def forge_formal_mapping(payload: dict) -> None:
            record(payload)["value"]["parameter_to_source_ordinals"] = [0, 1, 2]

        def reverse_formal_arguments(payload: dict) -> None:
            record(payload)["value"]["parameter_argument_node_ids"].reverse()

        def forge_argument_binding(payload: dict) -> None:
            record(payload)["value"]["argument_bindings"][0]["parameter_ordinal"] = 0

        def remove_plan_fact(payload: dict) -> None:
            facts = feature_plan(payload)["facts_used"]
            facts.remove(
                next(
                    item
                    for item in facts
                    if item.startswith("keyword-only-call-binding:")
                )
            )

        def forge_plan_obligations(payload: dict) -> None:
            plan = feature_plan(payload)
            changed = list(plan["semantic_obligations"])
            changed[
                changed.index("required-keyword-only-coverage-exact")
            ] = "forged-obligation"
            plan["semantic_obligations"] = changed
            plan["resolved_obligations"] = list(changed)

        def forge_rule_version(payload: dict) -> None:
            feature_plan(payload)["rule_version"] = "0.14.2"

        mutations = (
            ("coverage", omit_coverage),
            ("provenance", erase_provenance),
            ("source order", reverse_source_order),
            ("evaluation order", reverse_evaluation_order),
            ("keyword spelling", forge_keyword_name),
            ("parameter kind", forge_parameter_kind),
            ("required keyword-only set", erase_required_keyword_only),
            ("source mapping", forge_source_mapping),
            ("formal mapping", forge_formal_mapping),
            ("formal arguments", reverse_formal_arguments),
            ("argument binding", forge_argument_binding),
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

    def test_coordinated_category_tampering_cannot_override_python_ir(self) -> None:
        payload = self.analysis_payload()
        fact = table(
            payload,
            KEYWORD_ONLY_CALL_TABLE_ID,
        )["records"][0]["value"]
        parameter_ordinal = fact["parameter_categories"].index("boolean-like")
        keyword_only_ordinal = fact[
            "required_keyword_only_parameter_categories"
        ].index("boolean-like")
        source_ordinal = fact["source_argument_categories"].index("boolean-like")

        fact["parameter_categories"][parameter_ordinal] = "integer-like"
        fact["required_keyword_only_parameter_categories"][
            keyword_only_ordinal
        ] = "integer-like"
        fact["source_argument_categories"][source_ordinal] = "integer-like"
        fact["argument_bindings"][source_ordinal]["category"] = "integer-like"
        fact["argument_bindings"][source_ordinal][
            "expected_category"
        ] = "integer-like"

        actual_id = fact["source_argument_node_ids"][source_ordinal]
        next(
            item
            for item in table(payload, "value-category-facts")["records"]
            if item["key"] == actual_id
        )["value"] = "integer-like"
        target_signature = next(
            item["value"]
            for item in table(payload, "function-signature-facts")["records"]
            if item["value"]["binding_id"] == fact["target_binding_id"]
        )
        target_signature["parameters"][parameter_ordinal][
            "category"
        ] = "integer-like"
        target = next(
            item["value"]
            for item in table(payload, "call-target-facts")["records"]
            if item["value"]["call_node_id"] == fact["call_node_id"]
        )
        target["argument_categories"][source_ordinal] = "integer-like"
        target["parameter_categories"][parameter_ordinal] = "integer-like"
        plan = feature_plan(payload)
        plan["facts_used"] = [
            "argument-category:integer-like"
            if item == "argument-category:boolean-like"
            else item
            for item in plan["facts_used"]
        ]

        valid, reason = validate_analysis_payload(payload)
        self.assertFalse(valid)
        self.assertIn("Python IR annotations", reason)

    def test_call_target_support_flip_disagrees_with_reconstructed_rejection(self) -> None:
        result = convert(
            "def sink(value: int, *, flag: bool) -> int:\n"
            "    return value\n\n"
            "def run(value: int) -> int:\n"
            "    return sink(value)\n"
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        payload = json.loads(json.dumps(dict(result.stage_artifact.payload)))
        self.assertEqual(validate_analysis_payload(payload), (True, ""))
        table(payload, "call-target-facts")["records"][0]["value"][
            "supported"
        ] = True

        valid, reason = validate_analysis_payload(payload)
        self.assertFalse(valid)
        self.assertIn("call-target evidence", reason)

    def test_malformed_tables_dependencies_and_plans_fail_closed(self) -> None:
        baseline = self.analysis_payload()

        def null_tables(payload: dict) -> None:
            payload["fact_tables"] = None

        def malformed_table_item(payload: dict) -> None:
            payload["fact_tables"].append(None)

        def duplicate_dependency_table(payload: dict) -> None:
            payload["fact_tables"].append(deepcopy(table(payload, "binding-facts")))

        def null_dependencies(payload: dict) -> None:
            table(payload, KEYWORD_ONLY_CALL_TABLE_ID)[
                "invalidation_dependencies"
            ] = None

        def null_records(payload: dict) -> None:
            table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"] = None

        def null_parameter_kinds(payload: dict) -> None:
            table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"][0]["value"][
                "parameter_kinds"
            ] = None

        def null_rule_plans(payload: dict) -> None:
            payload["rule_plans"] = None

        def malformed_rule_plan_item(payload: dict) -> None:
            payload["rule_plans"].append(None)

        def duplicate_feature_plan(payload: dict) -> None:
            payload["rule_plans"].append(deepcopy(feature_plan(payload)))

        def null_plan_facts(payload: dict) -> None:
            feature_plan(payload)["facts_used"] = None

        def malformed_permutation(payload: dict) -> None:
            table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"][0]["value"][
                "source_to_parameter_ordinals"
            ] = [{}, 0, 1]

        mutations = (
            ("null tables", null_tables),
            ("malformed table item", malformed_table_item),
            ("duplicate dependency table", duplicate_dependency_table),
            ("null dependencies", null_dependencies),
            ("null records", null_records),
            ("null parameter kinds", null_parameter_kinds),
            ("null RulePlans", null_rule_plans),
            ("malformed RulePlan item", malformed_rule_plan_item),
            ("duplicate feature plan", duplicate_feature_plan),
            ("null plan facts", null_plan_facts),
            ("malformed permutation", malformed_permutation),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_keyword_only_call_binding_facts(payload)
                self.assertFalse(valid)
                self.assertTrue(reason)

        valid, reason = validate_keyword_only_call_binding_facts(
            deepcopy(baseline),
            tables=7,  # type: ignore[arg-type]
        )
        self.assertFalse(valid)
        self.assertTrue(reason)

    def test_analyzer_malformed_inputs_raise_only_bounded_binding_error(self) -> None:
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
                with self.assertRaises(KeywordOnlyCallAnalysisError) as caught:
                    KeywordOnlyCallAnalyzer(
                        module,  # type: ignore[arg-type]
                        bindings=bindings,  # type: ignore[arg-type]
                        signatures=signatures,  # type: ignore[arg-type]
                        categories=categories,  # type: ignore[arg-type]
                        cancellation=None,
                    )
                self.assertEqual(caught.exception.code, "PYC2912")

    def test_lowerer_rejects_malformed_facts_signatures_and_permutations(self) -> None:
        baseline = self.analysis_payload()
        fact = deepcopy(
            table(baseline, KEYWORD_ONLY_CALL_TABLE_ID)["records"][0]["value"]
        )
        call_id = fact["call_node_id"]
        nodes = {
            item["node_id"]: item for item in baseline["python_ir"]["nodes"]
        }
        node = deepcopy(nodes[call_id])
        signature = deepcopy(
            next(
                item["value"]
                for item in table(
                    baseline,
                    "function-signature-facts",
                )["records"]
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
            lowerer = KeywordOnlyCallCIRLowerer(
                KeywordOnlyCallLoweringServices(
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
            self.assertIn(caught.exception.code, {"PYC2910", "PYC2912"})

        cases: list[tuple[str, object, object, object]] = []
        cases.append(("null fact", None, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["argument_bindings"] = None
        cases.append(("null bindings", malformed, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["parameter_kinds"][-1] = "positional-or-keyword"
        cases.append(("wrong kind", malformed, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["source_to_parameter_ordinals"] = [{}, 0, 1]
        cases.append(("wrong permutation", malformed, deepcopy(node), deepcopy(signature)))
        malformed = deepcopy(fact)
        malformed["argument_bindings"][0] = None
        cases.append(("null binding", malformed, deepcopy(node), deepcopy(signature)))
        malformed_signature = deepcopy(signature)
        malformed_signature["parameters"] = None
        cases.append(
            (
                "null parameters",
                deepcopy(fact),
                deepcopy(node),
                malformed_signature,
            )
        )
        malformed_node = deepcopy(node)
        malformed_node["fields"] = None
        cases.append(
            (
                "null call fields",
                deepcopy(fact),
                malformed_node,
                deepcopy(signature),
            )
        )
        for label, candidate_fact, candidate_node, candidate_signature in cases:
            with self.subTest(label=label):
                invoke(candidate_fact, candidate_node, candidate_signature)

    def test_algorithms_keep_linear_merge_and_index_shapes(self) -> None:
        analysis_source = (
            ROOT / "pycforge/converter/keyword_only_calls/analysis.py"
        ).read_text(encoding="utf-8")
        validation_source = (
            ROOT / "pycforge/converter/keyword_only_calls/validation.py"
        ).read_text(encoding="utf-8")
        lowering_source = (
            ROOT / "pycforge/converter/keyword_only_calls/lowering.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _merge_source_entries(", analysis_source)
        self.assertIn("def _merge(", validation_source)
        self.assertNotIn("source_entries.sort(", analysis_source)
        self.assertNotIn("entries.sort(", validation_source)
        self.assertIn("feature_plans", validation_source)
        self.assertNotIn("matches = [item for item in plans", validation_source)
        self.assertNotIn("sorted(source_to_parameter)", lowering_source)
        self.assertNotIn("sorted(parameter_to_source)", lowering_source)

    def test_validator_propagates_cancellation(self) -> None:
        payload = self.analysis_payload()
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(KeywordOnlyCallValidationCanceled):
            validate_keyword_only_call_binding_facts(
                payload,
                expected_fact_schema=KEYWORD_ONLY_CALL_FACT_SCHEMA,
                cancellation=token,
            )

    def test_signature_analysis_cancels_inside_wide_parameter_scan(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        class ArmableCancellation(CancellationToken):
            def __init__(self, limit: int) -> None:
                super().__init__()
                self.armed = False
                self.limit = limit
                self.checks = 0

            @property
            def is_canceled(self) -> bool:
                if not self.armed:
                    return False
                self.checks += 1
                return self.checks > self.limit

        parameters = ", ".join(
            ["value: int", *(f"flag_{ordinal}: bool" for ordinal in range(80))]
        )
        source = f"def wide({parameters}) -> int:\n    return value\n"
        token = ArmableCancellation(12)
        real_signatures = analysis_stage.FunctionFactsAnalyzer.signatures

        def armed_signatures(analyzer):
            token.armed = True
            return real_signatures(analyzer)

        with patch.object(
            analysis_stage.FunctionFactsAnalyzer,
            "signatures",
            armed_signatures,
        ):
            result = convert(source, cancellation=token)

        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual(token.checks, token.limit + 1)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("analysis.plan", result.stage_order)
        self.assertNotIn("fact_tables", result.stage_artifact.payload)
        self.assertIsNone(result.generated_c)

    def test_declaration_validation_cancels_inside_wide_parameter_scan(self) -> None:
        from pycforge.converter.keyword_only_calls import validation

        class ArmableCancellation:
            def __init__(self, limit: int) -> None:
                self.armed = False
                self.limit = limit
                self.checks = 0

            @property
            def is_canceled(self) -> bool:
                if not self.armed:
                    return False
                self.checks += 1
                return self.checks > self.limit

        keyword_only = ", ".join(
            f"flag_{ordinal}: bool" for ordinal in range(80)
        )
        source = (
            f"def wide(value: int, *, {keyword_only}) -> int:\n"
            "    return value\n"
        )
        payload = json.loads(
            json.dumps(dict(self.converted(source).stage_artifact.payload))
        )
        token = ArmableCancellation(12)
        real_declaration_validation = validation._validate_declaration_plans

        def armed_validation(*args, **kwargs):
            token.armed = True
            return real_declaration_validation(*args, **kwargs)

        with patch.object(
            validation,
            "_validate_declaration_plans",
            armed_validation,
        ):
            with self.assertRaises(KeywordOnlyCallValidationCanceled):
                validate_keyword_only_call_binding_facts(
                    payload,
                    cancellation=token,
                )

        self.assertEqual(token.checks, token.limit + 1)

    def test_lowering_cancels_during_wide_prototype_parameter_assembly(self) -> None:
        from pycforge.converter import lowering

        parameters = ", ".join(
            ["value: int", *(f"flag_{ordinal}: bool" for ordinal in range(80))]
        )
        source = f"def wide({parameters}) -> int:\n    return value\n"
        token = CancellationToken()
        real_parameter = lowering._Lowerer._parameter
        calls = 0

        def cancel_on_seventh_parameter(lowerer, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 7:
                token.cancel()
            return real_parameter(lowerer, *args, **kwargs)

        with patch.object(
            lowering._Lowerer,
            "_parameter",
            cancel_on_seventh_parameter,
        ):
            result = convert(source, cancellation=token)

        self.assertEqual(calls, 7)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)

    def test_analysis_cancellation_discards_feature_facts_and_partial_plan(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        real_analyzer = analysis_stage.KeywordOnlyCallAnalyzer

        class CancelAfterAnalysis(real_analyzer):
            calls = 0

            def analyze(self):
                product = super().analyze()
                type(self).calls += 1
                self.cancellation.cancel()
                return product

        with patch.object(
            analysis_stage,
            "KeywordOnlyCallAnalyzer",
            CancelAfterAnalysis,
        ):
            result = convert()

        self.assertEqual(CancelAfterAnalysis.calls, 1)
        self.assertEqual(result.status, ResultStatus.CANCELED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("analysis.plan", result.stage_order)
        self.assertNotIn("fact_tables", result.stage_artifact.payload)

    def test_wide_binding_stress_has_complete_unique_linear_coverage(self) -> None:
        call_count = 180
        body = ["    result = seed"]
        body.extend(
            "    result = choose(ratio=ratio, flag=flag, left=result)"
            for _ in range(call_count)
        )
        body.append("    return result")
        source = (
            "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return left\n\n"
            "def run(seed: int, flag: bool, ratio: float) -> int:\n"
            + "\n".join(body)
            + "\n"
        )
        result = self.converted(source)
        records = table(
            result.stage_artifact.payload,
            KEYWORD_ONLY_CALL_TABLE_ID,
        )["records"]
        self.assertEqual(len(records), call_count)
        self.assertEqual(
            [item["key"] for item in records],
            sorted(item["key"] for item in records),
        )
        self.assertEqual(
            len({item["value"]["binding_id"] for item in records}),
            call_count,
        )
        self.assertTrue(all(item["value"]["supported"] for item in records))
        self.assertTrue(
            all(
                item["value"]["source_to_parameter_ordinals"] == [2, 1, 0]
                for item in records
            )
        )

    def test_observer_failures_are_semantically_inert(self) -> None:
        request = ConversionRequest.from_source(KEYWORD_ONLY_SOURCE)
        converter = PythonToCConverter()
        baseline = converter.convert(request)
        noisy = converter.convert(
            request,
            observation=ObservationOptions("Full", True),
            inject_trace_failure=True,
            inject_telemetry_failure=True,
        )

        self.assertEqual(baseline.status, ResultStatus.CONVERTED)
        self.assertEqual(baseline.semantic_dict(), noisy.semantic_dict())
        self.assertTrue(noisy.decision_trace["observer_failed"])
        self.assertTrue(noisy.telemetry["observer_failed"])

    def test_full_artifacts_are_fresh_process_deterministic(self) -> None:
        script = (
            "from pycforge import ConversionRequest,PythonToCConverter\n"
            "from pycforge.converter.core.request import ObservationOptions\n"
            "from pycforge.converter.core.serialization import result_to_json\n"
            f"source={KEYWORD_ONLY_SOURCE!r}\n"
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
