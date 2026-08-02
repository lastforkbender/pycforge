from __future__ import annotations

import unittest

from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.keyword_only_calls import KEYWORD_ONLY_CALL_TABLE_ID


def convert(source: str, *, full: bool = False):
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def convert_bundle(primary: str, companion: str, *, full: bool = False):
    return PythonToCConverter().convert(
        ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", primary, "app"),
                (SourceDocumentInput("lib.py", companion, "lib"),),
            )
        ),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def feature_facts(payload: dict) -> list[dict]:
    return [
        item["value"]
        for item in table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"]
    ]


def nodes(payload: dict) -> dict[str, dict]:
    return {item["node_id"]: item for item in payload["python_ir"]["nodes"]}


def source_name_by_node(payload: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in table(payload, "binding-facts")["records"]:
        value = item["value"]
        for node_id in value["occurrence_node_ids"]:
            result[node_id] = value["source_name"]
    return result


class Phase14DKeywordOnlyAnalysisTests(unittest.TestCase):
    def converted(self, source: str, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.stage_artifact)
        return result

    def test_required_keyword_only_formals_publish_exact_kinds_and_orders(self) -> None:
        source = (
            "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return left\n\n"
            "def run(x: int, y: bool, z: float) -> int:\n"
            "    return choose(ratio=z, left=x, flag=y)\n"
        )
        result = self.converted(source, full=True)
        payload = result.stage_artifact.payload
        facts = feature_facts(payload)
        self.assertEqual(len(facts), 1)
        fact = facts[0]

        self.assertEqual(fact["parameter_names"], ["left", "flag", "ratio"])
        self.assertEqual(
            fact["parameter_kinds"],
            ["positional-or-keyword", "keyword-only", "keyword-only"],
        )
        self.assertEqual(
            fact["parameter_categories"],
            ["integer-like", "boolean-like", "floating-like"],
        )
        self.assertEqual(fact["positional_only_parameter_count"], 0)
        self.assertEqual(fact["positional_or_keyword_parameter_count"], 1)
        self.assertEqual(fact["keyword_only_parameter_count"], 2)
        self.assertEqual(fact["required_keyword_only_parameter_names"], ["flag", "ratio"])
        self.assertEqual(
            fact["required_keyword_only_parameter_categories"],
            ["boolean-like", "floating-like"],
        )
        self.assertEqual(fact["positional_argument_node_ids"], [])
        self.assertEqual(fact["keyword_names"], ["ratio", "left", "flag"])
        self.assertEqual(
            fact["source_argument_categories"],
            ["floating-like", "integer-like", "boolean-like"],
        )
        self.assertEqual(fact["source_to_parameter_ordinals"], [2, 0, 1])
        self.assertEqual(fact["parameter_to_source_ordinals"], [1, 2, 0])
        self.assertEqual(
            fact["parameter_argument_node_ids"],
            [
                fact["source_argument_node_ids"][1],
                fact["source_argument_node_ids"][2],
                fact["source_argument_node_ids"][0],
            ],
        )
        self.assertEqual(fact["evaluation_order"], fact["source_argument_node_ids"])
        self.assertEqual(fact["source_argument_node_ids"], fact["keyword_value_node_ids"])
        self.assertTrue(fact["parameter_coverage_exact"])
        self.assertTrue(fact["keyword_only_coverage_exact"])
        self.assertTrue(fact["arguments_evaluated_once"])
        self.assertIsNone(fact["diagnostic_code"])
        self.assertIsNone(fact["rejection_node_id"])

        bindings = fact["argument_bindings"]
        self.assertEqual([item["source_ordinal"] for item in bindings], [0, 1, 2])
        self.assertEqual([item["keyword_name"] for item in bindings], ["ratio", "left", "flag"])
        self.assertEqual([item["parameter_ordinal"] for item in bindings], [2, 0, 1])
        self.assertEqual(
            [item["parameter_kind"] for item in bindings],
            ["keyword-only", "positional-or-keyword", "keyword-only"],
        )
        self.assertEqual(
            [item["expected_category"] for item in bindings],
            ["floating-like", "integer-like", "boolean-like"],
        )

        self.assertEqual(list(result.conversion_summary["keyword_only_calls"]), facts)
        plans = [
            item
            for item in payload["rule_plans"]
            if item["rule_id"] == "phase14.keyword_only_call.exact_binding"
        ]
        traced = [
            item
            for item in result.decision_trace["rule_decisions"]
            if item["rule_id"] == "phase14.keyword_only_call.exact_binding"
        ]
        self.assertEqual(traced, plans)

    def test_positional_prefix_and_interleaved_keywords_preserve_both_orders(self) -> None:
        source = (
            "def choose(head: int, left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return head\n\n"
            "def run(a: int, b: int, y: bool, z: float) -> int:\n"
            "    return choose(a, ratio=z, left=b, flag=y)\n"
        )
        payload = self.converted(source).stage_artifact.payload
        fact = feature_facts(payload)[0]
        names = source_name_by_node(payload)

        self.assertEqual(len(fact["positional_argument_node_ids"]), 1)
        self.assertEqual(fact["keyword_names"], ["ratio", "left", "flag"])
        self.assertEqual(fact["source_to_parameter_ordinals"], [0, 3, 1, 2])
        self.assertEqual(fact["parameter_to_source_ordinals"], [0, 2, 3, 1])
        self.assertEqual(
            [names[item] for item in fact["source_argument_node_ids"]],
            ["a", "z", "b", "y"],
        )
        self.assertEqual(
            [names[item] for item in fact["parameter_argument_node_ids"]],
            ["a", "b", "y", "z"],
        )

    def test_positional_only_prefix_can_compose_with_required_keyword_only(self) -> None:
        source = (
            "def choose(head: int, /, left: int, *, flag: bool) -> int:\n"
            "    return head\n\n"
            "def run(a: int, b: int, y: bool) -> int:\n"
            "    return choose(a, flag=y, left=b)\n"
        )
        fact = feature_facts(self.converted(source).stage_artifact.payload)[0]

        self.assertEqual(fact["positional_only_parameter_count"], 1)
        self.assertEqual(fact["positional_or_keyword_parameter_count"], 1)
        self.assertEqual(fact["keyword_only_parameter_count"], 1)
        self.assertEqual(
            fact["parameter_kinds"],
            ["positional-only", "positional-or-keyword", "keyword-only"],
        )
        self.assertEqual(fact["source_to_parameter_ordinals"], [0, 2, 1])
        self.assertEqual(fact["parameter_to_source_ordinals"], [0, 2, 1])
        self.assertTrue(fact["supported"])

    def test_nested_actuals_keep_source_order_separate_from_formal_order(self) -> None:
        source = (
            "def mark_int(value: int) -> int:\n    return value\n\n"
            "def mark_bool(value: bool) -> bool:\n    return value\n\n"
            "def mark_float(value: float) -> float:\n    return value\n\n"
            "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return left\n\n"
            "def run(x: int, y: bool, z: float) -> int:\n"
            "    return choose(\n"
            "        ratio=mark_float(z),\n"
            "        left=mark_int(x),\n"
            "        flag=mark_bool(y),\n"
            "    )\n"
        )
        payload = self.converted(source).stage_artifact.payload
        feature = next(item for item in feature_facts(payload) if item["target_name"] == "choose")
        by_id = nodes(payload)

        source_targets = [
            by_id[by_id[node_id]["fields"]["func"]]["fields"]["id"]
            for node_id in feature["source_argument_node_ids"]
        ]
        formal_targets = [
            by_id[by_id[node_id]["fields"]["func"]]["fields"]["id"]
            for node_id in feature["parameter_argument_node_ids"]
        ]
        self.assertEqual(source_targets, ["mark_float", "mark_int", "mark_bool"])
        self.assertEqual(formal_targets, ["mark_int", "mark_bool", "mark_float"])
        self.assertEqual(feature["source_to_parameter_ordinals"], [2, 0, 1])

    def test_cross_module_binding_reuses_exact_target_signature(self) -> None:
        primary = (
            "from lib import choose\n\n"
            "def run(value: int, flag: bool, ratio: float) -> int:\n"
            "    return choose(ratio=ratio, flag=flag, left=value)\n"
        )
        companion = (
            "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return left\n"
        )
        result = convert_bundle(primary, companion, full=True)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        payload = result.stage_artifact.payload
        fact = feature_facts(payload)[0]
        module_functions = {
            item["value"]["function_node_id"]: item["value"]
            for item in table(payload, "module-function-facts")["records"]
        }

        self.assertEqual(
            module_functions[fact["target_function_node_id"]]["module_id"],
            "lib",
        )
        self.assertEqual(fact["parameter_names"], ["left", "flag", "ratio"])
        self.assertEqual(fact["source_to_parameter_ordinals"], [2, 1, 0])
        self.assertTrue(fact["supported"])
        self.assertEqual(
            result.conversion_summary["module_initialization"]["module_order"],
            ["lib", "app"],
        )

    def test_no_keyword_call_is_a_complete_missing_coverage_candidate(self) -> None:
        source = (
            "def sink(value: int, *, flag: bool) -> int:\n"
            "    return value\n\n"
            "def run(value: int) -> int:\n"
            "    return sink(value)\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in result.diagnostics], ["PYC2904"])
        facts = feature_facts(result.stage_artifact.payload)
        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertFalse(fact["supported"])
        self.assertFalse(fact["parameter_coverage_exact"])
        self.assertFalse(fact["keyword_only_coverage_exact"])
        self.assertEqual(fact["keyword_names"], [])
        self.assertEqual(fact["diagnostic_code"], "PYC2904")
        self.assertTrue(fact["reason"])
        self.assertEqual(fact["rejection_node_id"], fact["call_node_id"])


if __name__ == "__main__":
    unittest.main()
