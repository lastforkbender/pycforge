from __future__ import annotations

import re
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.conditional_regions import CONDITIONAL_REGION_OBLIGATIONS
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.support_templates import FLOOR_DIV_REFERENCE


def convert(source: str, *, full: bool = False):
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def walk(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from walk(child)


def function_definition(payload: dict, name: str) -> dict:
    return next(
        item
        for item in payload["c_ir"]["declarations"]
        if item.get("kind") == "CFunctionDefinition"
        and item.get("identifier", {}).get("spelling") == name
    )


def fact_table(payload: dict) -> dict:
    return next(
        item
        for item in payload["fact_tables"]
        if item["table_id"] == "conditional-region-facts"
    )


class Phase14BConditionalLoweringTests(unittest.TestCase):
    def converted(self, source: str, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.generated_c)
        self.assertIsNotNone(result.stage_artifact)
        return result

    def test_existing_scalar_regions_work_in_all_existing_expression_contexts(self) -> None:
        cases = {
            "return": (
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n    return a and flag(b)\n"
            ),
            "assignment": (
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    result = a and flag(b)\n"
                "    return result\n"
            ),
            "if": (
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    if a and flag(b):\n"
                "        return True\n"
                "    return False\n"
            ),
            "while": (
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    while a and flag(b):\n"
                "        return False\n"
                "    return True\n"
            ),
            "call-argument": (
                "def flag(v: bool) -> bool:\n    return v\n\n"
                "def sink(v: bool) -> bool:\n    return v\n\n"
                "def run(a: bool, b: bool) -> bool:\n"
                "    return sink(a and flag(b))\n"
            ),
            "chained-call-arithmetic": (
                "def value(v: int) -> int:\n    return v\n\n"
                "def run(a: int, b: int, c: int) -> bool:\n"
                "    return a < b < value(c) + 1\n"
            ),
        }
        for context, source in cases.items():
            with self.subTest(context=context):
                result = self.converted(source)
                self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
                self.assertEqual(
                    result.stage_artifact.payload["schema_version"],
                    "generated-c/0.14.3",
                )
                self.assertEqual(
                    result.stage_artifact.payload["c_ir_schema"],
                    "c-ir/0.14.3",
                )

    def test_and_uses_initialized_result_and_flat_true_guard_siblings(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return flag(a) and flag(b) and flag(c)\n"
        )
        result = self.converted(source)
        payload = result.stage_artifact.payload
        run = function_definition(payload, "run")
        statements = run["body"]["statements"]
        guards = [
            item
            for item in statements
            if item.get("node_id", "").startswith("c-bool-region-if-")
        ]
        result_declaration = next(
            item
            for item in statements
            if item.get("node_id", "").startswith("c-bool_region_result-temp-")
        )
        result_binding = result_declaration["identifier"]["binding_id"]

        self.assertEqual(len(guards), 2)
        self.assertTrue(all(item["condition"]["kind"] == "CIdentifierRef" for item in guards))
        self.assertTrue(
            all(item["condition"]["binding_id"] == result_binding for item in guards)
        )
        self.assertTrue(all(item["else_block"] is None for item in guards))
        self.assertTrue(
            all(
                item["then_block"]["statements"][-1]["kind"]
                == "CAssignmentStatement"
                and item["then_block"]["statements"][-1]["target"]["binding_id"]
                == result_binding
                for item in guards
            )
        )
        self.assertEqual(
            [
                len([item for item in walk(guard["then_block"]) if item.get("kind") == "CCallExpr"])
                for guard in guards
            ],
            [1, 1],
        )
        self.assertEqual(
            len([item for item in statements if item.get("kind") == "CIfStatement"]),
            2,
        )
        self.assertEqual((result.generated_c or "").count(f"if (pycf_bool_region_result_"), 2)

    def test_or_uses_flat_false_guards(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return a or flag(b) or flag(c)\n"
        )
        result = self.converted(source)
        run = function_definition(result.stage_artifact.payload, "run")
        guards = [
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        ]
        self.assertEqual(len(guards), 2)
        self.assertTrue(
            all(
                item["condition"]["kind"] == "CUnaryExpr"
                and item["condition"]["op"] == "!"
                and item["condition"]["operand"]["kind"] == "CIdentifierRef"
                for item in guards
            )
        )
        generated = result.generated_c or ""
        self.assertEqual(len(re.findall(r"if \(!pycf_bool_region_result_[0-9a-f]+\)", generated)), 2)

    def test_chained_calls_use_flat_true_guards_and_once_only_middle_values(self) -> None:
        source = (
            "def value(item: int) -> int:\n"
            "    return item\n\n"
            "def run(a: int, b: int, c: int, d: int) -> bool:\n"
            "    return a < b < value(c) < value(d)\n"
        )
        result = self.converted(source)
        run = function_definition(result.stage_artifact.payload, "run")
        statements = run["body"]["statements"]
        guards = [
            item
            for item in statements
            if item.get("node_id", "").startswith("c-chain-region-if-")
        ]
        comparisons = [
            item
            for item in walk(run)
            if item.get("node_id", "").startswith("c-chain-region-compare-")
        ]

        self.assertEqual(len(guards), 2)
        self.assertTrue(all(item["condition"]["kind"] == "CIdentifierRef" for item in guards))
        self.assertTrue(all(item["else_block"] is None for item in guards))
        self.assertTrue(
            all(
                len([item for item in walk(guard["then_block"]) if item.get("kind") == "CCallExpr"])
                == 1
                for guard in guards
            )
        )
        self.assertEqual(len(comparisons), 3)
        adjacent_bindings = [
            (item["left"]["binding_id"], item["right"]["binding_id"])
            for item in comparisons
        ]
        self.assertEqual(adjacent_bindings[0][1], adjacent_bindings[1][0])
        self.assertEqual(adjacent_bindings[1][1], adjacent_bindings[2][0])
        self.assertEqual((result.generated_c or "").count(" = value("), 2)

    def test_nested_child_region_remains_lexically_inside_parent_guard(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return a and (b or flag(c))\n"
        )
        result = self.converted(source)
        run = function_definition(result.stage_artifact.payload, "run")
        top_level_guards = [
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        ]
        self.assertEqual(len(top_level_guards), 1)
        nested_guards = [
            item
            for item in top_level_guards[0]["then_block"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        ]
        self.assertEqual(len(nested_guards), 1)
        self.assertEqual(nested_guards[0]["condition"]["kind"], "CUnaryExpr")
        self.assertEqual(nested_guards[0]["condition"]["op"], "!")
        top_level_calls = [
            item for item in walk(run["body"]) if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(len(top_level_calls), 1)
        self.assertEqual(
            len([item for item in walk(nested_guards[0]) if item.get("kind") == "CCallExpr"]),
            1,
        )

    def test_numeric_helper_prerequisites_remain_inside_chain_guard(self) -> None:
        source = (
            "def value(item: int) -> int:\n"
            "    return item\n\n"
            "def run(a: int, b: int, c: int) -> bool:\n"
            "    return a < b < (value(c) // 2)\n"
        )
        result = self.converted(source)
        payload = result.stage_artifact.payload
        run = function_definition(payload, "run")
        guard = next(
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-chain-region-if-")
        )
        helper_binding = f"helper-binding:{FLOOR_DIV_REFERENCE.canonical}:function"
        helper_calls_inside = [
            item
            for item in walk(guard["then_block"])
            if item.get("kind") == "CCallExpr"
            and item.get("callee", {}).get("binding_id") == helper_binding
        ]
        helper_calls_in_run = [
            item
            for item in walk(run)
            if item.get("kind") == "CCallExpr"
            and item.get("callee", {}).get("binding_id") == helper_binding
        ]
        self.assertEqual(len(helper_calls_inside), 1)
        self.assertEqual(helper_calls_inside, helper_calls_in_run)
        self.assertEqual(payload["helper_requirements"], [FLOOR_DIV_REFERENCE.canonical])

    def test_facts_plans_observers_and_mappings_publish_the_same_regions(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def value(item: int) -> int:\n"
            "    return item\n\n"
            "def bool_run(a: bool, b: bool) -> bool:\n"
            "    return a and flag(b)\n\n"
            "def chain_run(a: int, b: int, c: int) -> bool:\n"
            "    return a < b < value(c)\n"
        )
        result = self.converted(source, full=True)
        payload = result.stage_artifact.payload
        table = fact_table(payload)
        facts = [item["value"] for item in table["records"]]
        plans = [
            item
            for item in payload["rule_plans"]
            if item["rule_id"].startswith("phase14.conditional.")
        ]

        self.assertEqual(table["schema_version"], "fact-table/0.14.1")
        self.assertEqual(table["key_domain"], "conditional-region-node-id")
        self.assertEqual(table["completeness"], "complete")
        self.assertEqual(
            {item["region_kind"] for item in facts},
            {"boolean-short-circuit", "chained-comparison"},
        )
        self.assertEqual(
            {item["rule_id"] for item in plans},
            {
                "phase14.conditional.boolean_region",
                "phase14.conditional.comparison_region",
            },
        )
        self.assertTrue(all(item["rule_version"] == "0.14.1" for item in plans))
        self.assertTrue(all(item["helper_requirements"] == [] for item in plans))
        self.assertTrue(
            all(item["semantic_obligations"] == list(CONDITIONAL_REGION_OBLIGATIONS) for item in plans)
        )
        self.assertTrue(
            all(item["resolved_obligations"] == item["semantic_obligations"] for item in plans)
        )
        self.assertEqual(list(result.conversion_summary["conditional_regions"]), facts)
        traced = [
            item
            for item in result.decision_trace["rule_decisions"]
            if item["rule_id"].startswith("phase14.conditional.")
        ]
        self.assertEqual(traced, plans)

        plan_ids = {item["plan_id"] for item in plans}
        region_mappings = [
            item
            for item in payload["source_output_mappings"]
            if "-region-" in item["c_node_id"]
            or "_region_result-" in item["c_node_id"]
        ]
        self.assertTrue(region_mappings)
        self.assertTrue(
            all(item["rule_plan_id"] in plan_ids for item in region_mappings)
        )
        self.assertTrue(all(item["start_byte"] < item["end_byte"] for item in region_mappings))
        self.assertTrue(all(item["source_document_id"] for item in region_mappings))
        self.assertTrue(all(item["logical_source_name"] == "main.py" for item in region_mappings))


if __name__ == "__main__":
    unittest.main()
