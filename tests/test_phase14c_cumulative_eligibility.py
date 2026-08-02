from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.conditional_regions.model import (
    ConditionalRegionValidationCanceled,
)
from pycforge.converter.keyword_calls.model import KeywordCallValidationCanceled


_CUMULATIVE_REASON = (
    "Keyword-call target is outside the eligible direct source-function profile"
)


def convert(source: str):
    return PythonToCConverter().convert(ConversionRequest.from_source(source))


def table(payload: dict, table_id: str) -> dict:
    return next(
        item for item in payload["fact_tables"] if item["table_id"] == table_id
    )


class Phase14CCumulativeEligibilityTests(unittest.TestCase):
    def assert_cumulative_rejection(
        self,
        source: str,
        diagnostic_code: str,
        *,
        fact_count: int = 1,
    ) -> None:
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], [diagnostic_code])
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")

        payload = deepcopy(dict(result.stage_artifact.payload))
        self.assertEqual(validate_analysis_payload(payload), (True, ""))
        facts = [
            item["value"]
            for item in table(payload, "keyword-call-binding-facts")["records"]
        ]
        self.assertEqual(len(facts), fact_count)
        call_targets = {
            item["value"]["call_node_id"]: item["value"]
            for item in table(payload, "call-target-facts")["records"]
        }
        decisions = {
            item["node_id"]: item for item in payload["support_decisions"]
        }
        for fact in facts:
            with self.subTest(call_node_id=fact["call_node_id"]):
                self.assertFalse(fact["supported"])
                self.assertTrue(fact["parameter_coverage_exact"])
                self.assertEqual(fact["diagnostic_code"], "PYC2911")
                self.assertEqual(fact["reason"], _CUMULATIVE_REASON)
                self.assertEqual(
                    fact["rejection_node_id"],
                    fact["target_function_node_id"],
                )
                self.assertEqual(
                    fact["runtime_binding_failure"],
                    "compile-time-rejected",
                )
                target = call_targets[fact["call_node_id"]]
                self.assertFalse(target["supported"])
                self.assertEqual(target["resolution"], "ineligible-source-function")
                self.assertEqual(target["diagnostic_code"], "PYC2911")
                self.assertEqual(target["reason"], _CUMULATIVE_REASON)
                self.assertEqual(decisions[fact["call_node_id"]]["state"], "Unsupported")
                self.assertIsNone(
                    decisions[fact["call_node_id"]]["rule_plan_id"]
                )
        self.assertEqual(
            [
                item
                for item in payload["rule_plans"]
                if item["rule_id"] == "phase14.keyword_call.exact_binding"
            ],
            [],
        )

    def test_positive_binding_is_gated_by_every_final_function_boundary(self) -> None:
        cases = (
            (
                "return-mismatch",
                "def bad(value: int) -> int:\n"
                "    return True\n\n"
                "def run(value: int) -> int:\n"
                "    return bad(value=value)\n",
                "PYC2930",
                1,
            ),
            (
                "fallthrough",
                "def bad(value: int, flag: bool) -> int:\n"
                "    if flag:\n"
                "        return value\n\n"
                "def run(value: int, flag: bool) -> int:\n"
                "    return bad(flag=flag, value=value)\n",
                "PYC2931",
                1,
            ),
            (
                "local-lifetime",
                "def bad(flag: bool) -> int:\n"
                "    if flag:\n"
                "        value = 1\n"
                "    else:\n"
                "        value = 2\n"
                "    return value\n\n"
                "def run(flag: bool) -> int:\n"
                "    return bad(flag=flag)\n",
                "PYC2870",
                1,
            ),
            (
                "unsupported-nested-call",
                "def bad(value: int) -> int:\n"
                "    return missing(value)\n\n"
                "def run(value: int) -> int:\n"
                "    return bad(value=value)\n",
                "PYC2901",
                1,
            ),
            (
                "recursion",
                "def bad(value: int) -> int:\n"
                "    if value == 0:\n"
                "        return value\n"
                "    return bad(value=value)\n\n"
                "def run(value: int) -> int:\n"
                "    return bad(value=value)\n",
                "PYC2920",
                2,
            ),
        )
        for label, source, code, count in cases:
            with self.subTest(label=label):
                self.assert_cumulative_rejection(source, code, fact_count=count)

    def test_target_eligibility_propagates_through_supported_direct_calls(self) -> None:
        self.assert_cumulative_rejection(
            "def broken(value: int) -> int:\n"
            "    return True\n\n"
            "def middle(value: int) -> int:\n"
            "    return broken(value)\n\n"
            "def run(value: int) -> int:\n"
            "    return middle(value=value)\n",
            "PYC2930",
        )

    def test_long_invalid_target_chain_is_closed_without_rescan_waves(self) -> None:
        function_count = 180
        definitions = [
            f"def step_{function_count - 1}(value: int) -> int:\n"
            "    return True\n"
        ]
        definitions.extend(
            f"def step_{ordinal}(value: int) -> int:\n"
            f"    return step_{ordinal + 1}(value)\n"
            for ordinal in range(function_count - 2, -1, -1)
        )
        definitions.append(
            "def run(value: int) -> int:\n"
            "    return step_0(value=value)\n"
        )
        self.assert_cumulative_rejection("\n".join(definitions), "PYC2930")

    def test_exact_cascade_deferral_does_not_hide_declaration_pyc2911(self) -> None:
        result = convert(
            "def sink(value: int, flag: bool = True) -> int:\n"
            "    return value\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return sink(flag=flag, value=value)\n"
        )
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC2911"])
        self.assertNotEqual(result.diagnostics[0].message, _CUMULATIVE_REASON)
        self.assertIsNone(result.generated_c)
        self.assertEqual(
            table(
                result.stage_artifact.payload,
                "keyword-call-binding-facts",
            )["records"],
            [],
        )

    def test_validation_cancellation_names_the_component_that_canceled(self) -> None:
        from pycforge.converter.analysis import stage as analysis_stage

        cases = (
            (
                ConditionalRegionValidationCanceled,
                "Conversion canceled during conditional-region validation",
            ),
            (
                KeywordCallValidationCanceled,
                "Conversion canceled during keyword-call validation",
            ),
        )
        source = "def run(value: int) -> int:\n    return value\n"
        for exception, message in cases:
            with self.subTest(exception=exception.__name__):
                with patch.object(
                    analysis_stage,
                    "validate_analysis_payload",
                    side_effect=exception,
                ):
                    result = convert(source)
                self.assertEqual(result.status, ResultStatus.CANCELED)
                self.assertEqual([item.code for item in result.diagnostics], ["PYC1901"])
                self.assertEqual(result.diagnostics[0].message, message)
                self.assertIsNone(result.generated_c)
                self.assertNotIn("analysis.plan", result.stage_order)

    def test_general_analysis_validation_rejects_malformed_collections(self) -> None:
        converted = convert(
            "def sink(value: int) -> int:\n"
            "    return value\n\n"
            "def run(value: int) -> int:\n"
            "    return sink(value=value)\n"
        )
        self.assertEqual(converted.status, ResultStatus.CONVERTED)
        baseline = json.loads(json.dumps(dict(converted.stage_artifact.payload)))

        def first_record(payload: dict) -> dict:
            return next(
                record
                for fact_table in payload["fact_tables"]
                for record in fact_table["records"]
            )

        mutations = (
            ("fact tables null", lambda payload: payload.__setitem__("fact_tables", None)),
            ("fact-table item", lambda payload: payload["fact_tables"].__setitem__(0, None)),
            ("records null", lambda payload: payload["fact_tables"][0].__setitem__("records", None)),
            ("record item", lambda payload: payload["fact_tables"][0]["records"].__setitem__(0, None)),
            ("record key", lambda payload: first_record(payload).__setitem__("key", None)),
            ("plans null", lambda payload: payload.__setitem__("rule_plans", None)),
            ("plan item", lambda payload: payload["rule_plans"].__setitem__(0, None)),
            ("plan ID", lambda payload: payload["rule_plans"][0].__setitem__("plan_id", None)),
            ("decisions null", lambda payload: payload.__setitem__("support_decisions", None)),
            ("decision item", lambda payload: payload["support_decisions"].__setitem__(0, None)),
            ("decision key", lambda payload: payload["support_decisions"][0].__setitem__("decision_key", None)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = deepcopy(baseline)
                mutate(payload)
                valid, reason = validate_analysis_payload(payload)
                self.assertFalse(valid)
                self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
