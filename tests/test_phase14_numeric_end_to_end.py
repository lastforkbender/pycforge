from __future__ import annotations

from collections import Counter
import re
import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.contracts.configuration import DEFAULT_NUMERIC_POLICY
from pycforge.converter.contracts.versions import (
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    NUMERIC_FACT_SCHEMA,
)
from pycforge.converter.core.request import (
    ObservationOptions,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
)


DIV = FLOOR_DIV_REFERENCE.canonical
MOD = FLOOR_MOD_REFERENCE.canonical


def convert(source: str, *, full: bool = False):
    return PythonToCConverter().convert(
        ConversionRequest.from_source(source),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def walk(value: object):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from walk(item)


class Phase14NumericEndToEndTests(unittest.TestCase):
    def test_exact_literal_shapes_and_domain_edges_are_accepted(self) -> None:
        cases = (
            ("//", "1", 1, 1, DIV),
            ("%", "+1", 1, 3, MOD),
            ("//", "-2", -2, 3, DIV),
            ("%", "9223372036854775807", 9223372036854775807, 1, MOD),
            ("//", "+9223372036854775807", 9223372036854775807, 3, DIV),
            ("%", "-9223372036854775807", -9223372036854775807, 3, MOD),
        )
        for operator, spelling, expected, literal_node_count, helper in cases:
            with self.subTest(operator=operator, spelling=spelling):
                result = convert(
                    "def bounded(value: int) -> int:\n"
                    f"    return value {operator} {spelling}\n"
                )
                self.assertEqual(result.status, ResultStatus.CONVERTED)
                self.assertEqual(result.diagnostics, ())
                facts = table(
                    result.stage_artifact.payload,
                    "numeric-operation-facts",
                )
                self.assertEqual(facts["schema_version"], NUMERIC_FACT_SCHEMA)
                self.assertEqual(len(facts["records"]), 1)
                fact = facts["records"][0]["value"]
                self.assertEqual(fact["divisor_value"], expected)
                self.assertEqual(len(fact["divisor_literal_node_ids"]), literal_node_count)
                self.assertEqual(fact["helper_requirement"], helper)
                self.assertEqual(fact["left_category"], "integer-like")
                self.assertEqual(fact["right_category"], "integer-like")
                self.assertEqual(fact["result_category"], "integer-like")
                self.assertEqual(fact["c_type"], "int64_t")
                self.assertEqual(
                    fact["failure_policy"],
                    "caller-proved-no-runtime-failure-channel",
                )
                self.assertTrue(fact["operands_evaluated_once"])
                self.assertEqual(
                    [item["reference"] for item in result.stage_artifact.payload["helper_manifest"]],
                    [helper],
                )

    def test_positive_and_mixed_sign_quadrants_select_exact_helper_calls(self) -> None:
        source = (
            "def quadrants() -> int:\n"
            "    pp_div = 7 // 3\n"
            "    np_div = -7 // 3\n"
            "    pn_div = 7 // -3\n"
            "    nn_div = -7 // -3\n"
            "    pp_mod = 7 % 3\n"
            "    np_mod = -7 % 3\n"
            "    pn_mod = 7 % -3\n"
            "    nn_mod = -7 % -3\n"
            "    return pp_div + np_div + pn_div + nn_div + pp_mod + np_mod + pn_mod + nn_mod\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        facts = [
            record["value"]
            for record in table(
                result.stage_artifact.payload,
                "numeric-operation-facts",
            )["records"]
        ]
        self.assertEqual(
            Counter(item["operator_kind"] for item in facts),
            Counter({"floor-divide": 4, "floor-modulo": 4}),
        )
        self.assertEqual(
            Counter(item["divisor_value"] for item in facts),
            Counter({3: 4, -3: 4}),
        )
        self.assertEqual(
            Counter(item["helper_requirement"] for item in facts),
            Counter({DIV: 4, MOD: 4}),
        )

        helper_calls = [
            item
            for item in walk(result.stage_artifact.payload["c_ir"])
            if item.get("kind") == "CCallExpr"
            and item.get("callee", {}).get("binding_id", "").startswith("helper-binding:")
        ]
        self.assertEqual(
            Counter(item["callee"]["binding_id"] for item in helper_calls),
            Counter(
                {
                    f"helper-binding:{DIV}:function": 4,
                    f"helper-binding:{MOD}:function": 4,
                }
            ),
        )
        self.assertTrue(all(len(item["arguments"]) == 2 for item in helper_calls))
        self.assertTrue(
            all(
                [argument["kind"] for argument in item["arguments"]]
                == ["CIdentifierRef", "CIdentifierRef"]
                for item in helper_calls
            )
        )
        self.assertIn(" = 7LL;", result.generated_c)
        self.assertIn(" = -7LL;", result.generated_c)

    def test_helper_union_is_exact_deduplicated_and_registry_ordered(self) -> None:
        source = (
            "def repeated(value: int) -> int:\n"
            "    first = value % 2\n"
            "    second = value // 3\n"
            "    third = value % -4\n"
            "    fourth = value // 5\n"
            "    return first + second + third + fourth\n"
        )
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        self.assertEqual(list(payload["helper_requirements"]), [DIV, MOD])
        self.assertEqual(
            [item["reference"] for item in payload["helper_manifest"]],
            [DIV, MOD],
        )
        plans = [
            item
            for item in payload["rule_plans"]
            if item["rule_id"] == "phase14.numeric.floor_arithmetic"
        ]
        self.assertEqual(len(plans), 4)
        self.assertEqual(
            Counter(item["helper_requirements"][0] for item in plans),
            Counter({DIV: 2, MOD: 2}),
        )
        self.assertTrue(all(item["support_state"] == "SupportedWithHelper" for item in plans))

        declarations = payload["c_ir"]["declarations"]
        identities = [
            (item["kind"], item["identifier"]["binding_id"])
            for item in declarations
        ]
        self.assertEqual(
            identities[:2],
            [
                ("CFunctionPrototype", f"helper-binding:{DIV}:function"),
                ("CFunctionPrototype", f"helper-binding:{MOD}:function"),
            ],
        )
        self.assertEqual(
            [item for item in identities if item[1].startswith("helper-binding:")],
            [
                ("CFunctionPrototype", f"helper-binding:{DIV}:function"),
                ("CFunctionPrototype", f"helper-binding:{MOD}:function"),
                ("CFunctionDefinition", f"helper-binding:{DIV}:function"),
                ("CFunctionDefinition", f"helper-binding:{MOD}:function"),
            ],
        )
        self.assertEqual(
            result.generated_c.count("static int64_t pycf_i64_floor_div_v1("),
            2,
        )
        self.assertEqual(
            result.generated_c.count("static int64_t pycf_i64_floor_mod_v1("),
            2,
        )

    def test_nested_left_operations_materialize_left_right_result_in_order(self) -> None:
        result = convert(
            "def nested(value: int) -> int:\n"
            "    return (value // 2) % -3\n"
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        declarations = re.findall(
            r"^\s*int64_t (pycf_numeric_(left|right|result)_[a-f0-9]+) = (.+);$",
            result.generated_c,
            re.MULTILINE,
        )
        self.assertEqual(
            [role for _name, role, _initializer in declarations],
            ["left", "right", "result", "left", "right", "result"],
        )
        first_result_name = declarations[2][0]
        self.assertIn("pycf_i64_floor_div_v1(", declarations[2][2])
        self.assertIn(first_result_name, declarations[3][2])
        self.assertIn("pycf_i64_floor_mod_v1(", declarations[5][2])
        self.assertEqual(declarations[1][2], "2LL")
        self.assertEqual(declarations[4][2], "-3LL")

        facts = [
            item["value"]
            for item in table(
                result.stage_artifact.payload,
                "numeric-operation-facts",
            )["records"]
        ]
        inner = next(item for item in facts if item["operator_kind"] == "floor-divide")
        outer = next(item for item in facts if item["operator_kind"] == "floor-modulo")
        self.assertEqual(outer["left_node_id"], inner["binop_node_id"])
        self.assertEqual(inner["evaluation_order"], [inner["left_node_id"], inner["right_node_id"]])
        self.assertEqual(outer["evaluation_order"], [outer["left_node_id"], outer["right_node_id"]])

    def test_facts_plans_summary_trace_and_mappings_are_closed_and_qualified(self) -> None:
        request = ConversionRequest(
            SourceBundle(
                SourceDocumentInput(
                    "app.py",
                    "from lib.math import halve\n\n"
                    "def run(value: int) -> int:\n"
                    "    return halve(value) % 3\n",
                    "app",
                ),
                (
                    SourceDocumentInput(
                        "lib/math.py",
                        "def halve(value: int) -> int:\n"
                        "    return value // 2\n",
                        "lib.math",
                    ),
                ),
            )
        )
        result = PythonToCConverter().convert(
            request,
            observation=ObservationOptions("Full", False),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        fact_table = table(payload, "numeric-operation-facts")
        self.assertEqual(fact_table["schema_version"], NUMERIC_FACT_SCHEMA)
        self.assertEqual(fact_table["producer_stage"], "analysis.plan")
        self.assertEqual(fact_table["key_domain"], "binop-node-id")
        self.assertEqual(fact_table["completeness"], "complete")
        self.assertEqual(
            list(fact_table["invalidation_dependencies"]),
            ["value-category-facts", "evaluation-order-facts"],
        )
        fact_values = [item["value"] for item in fact_table["records"]]
        self.assertEqual(
            {(item["module_id"], item["logical_name"]) for item in fact_values},
            {("app", "app.py"), ("lib.math", "lib/math.py")},
        )
        self.assertTrue(
            all(item["binop_node_id"] == record["key"] for item, record in zip(fact_values, fact_table["records"]))
        )
        self.assertTrue(
            all(
                {
                    item["binop_node_id"],
                    item["function_node_id"],
                    item["operator_node_id"],
                    item["left_node_id"],
                    *item["divisor_literal_node_ids"],
                }.issubset(set(record["provenance"]["source_node_ids"]))
                for item, record in zip(fact_values, fact_table["records"])
            )
        )

        plans = [
            item
            for item in payload["rule_plans"]
            if item["rule_id"] == "phase14.numeric.floor_arithmetic"
        ]
        self.assertEqual(len(plans), 2)
        self.assertEqual(
            {item["source_node_id"] for item in plans},
            {item["binop_node_id"] for item in fact_values},
        )
        self.assertTrue(all(item["rule_version"] == "0.14" for item in plans))
        self.assertTrue(all(item["support_state"] == "SupportedWithHelper" for item in plans))
        self.assertTrue(all(not item["unresolved_obligations"] for item in plans))
        self.assertTrue(
            all(
                item["semantic_obligations"] == item["resolved_obligations"]
                for item in plans
            )
        )

        self.assertEqual(result.conversion_summary["schema_version"], CONVERSION_SUMMARY_SCHEMA)
        self.assertEqual(
            result.conversion_summary["numeric_policy_version"],
            DEFAULT_NUMERIC_POLICY,
        )
        self.assertEqual(list(result.conversion_summary["numeric_operations"]), fact_values)
        self.assertEqual(
            [item["reference"] for item in result.conversion_summary["helpers"]],
            [DIV, MOD],
        )
        self.assertEqual(result.decision_trace["schema_version"], DECISION_TRACE_SCHEMA)
        self.assertEqual(
            result.decision_trace["numeric_policy_version"],
            DEFAULT_NUMERIC_POLICY,
        )
        traced = [
            item
            for item in result.decision_trace["rule_decisions"]
            if item["rule_id"] == "phase14.numeric.floor_arithmetic"
        ]
        self.assertEqual(traced, plans)
        self.assertEqual(
            list(result.decision_trace["helper_manifest"]),
            list(payload["helper_manifest"]),
        )
        self.assertEqual(
            list(result.decision_trace["source_output_mappings"]),
            list(payload["source_output_mappings"]),
        )

        numeric_calls = [
            item
            for item in payload["source_output_mappings"]
            if item["c_node_id"].startswith("c-numeric-helper-call-")
        ]
        self.assertEqual(len(numeric_calls), 2)
        self.assertEqual(
            {(item["module_id"], item["logical_source_name"]) for item in numeric_calls},
            {("app", "app.py"), ("lib.math", "lib/math.py")},
        )
        self.assertTrue(all(item["source_document_id"] for item in numeric_calls))
        self.assertTrue(all(item["rule_plan_id"] in {plan["plan_id"] for plan in plans} for item in numeric_calls))
        self.assertTrue(all(item["start_byte"] < item["end_byte"] for item in numeric_calls))

    def test_pyc3701_rejects_category_and_context_near_misses(self) -> None:
        cases = (
            (
                "float-left",
                "def f(value: float) -> float:\n    return value // 2\n",
                "exact integer-like operands",
            ),
            (
                "float-right",
                "def f(value: int) -> float:\n    return value % 2.0\n",
                "exact integer-like operands",
            ),
            (
                "bool-left",
                "def f(value: bool) -> int:\n    return value // 2\n",
                "exact integer-like operands",
            ),
            (
                "bool-right",
                "def f(value: int) -> int:\n    return value % True\n",
                "exact integer-like operands",
            ),
            (
                "lambda-context",
                "def f(value: int) -> int:\n"
                "    hidden = lambda: value // 2\n"
                "    return value\n",
                "direct expression context",
            ),
        )
        for name, source, message in cases:
            with self.subTest(name=name):
                result = convert(source)
                self._assert_numeric_rejection(result, "PYC3701", message)

    def test_pyc3702_rejects_unproved_or_unsafe_divisors(self) -> None:
        cases = (
            ("zero", "value // 0", "zero divisor"),
            ("positive-zero", "value % +0", "zero divisor"),
            ("negative-zero", "value // -0", "zero divisor"),
            ("negative-one", "value % -1", "divisor of -1"),
            ("variable", "value // divisor", "directly recognized"),
            ("positive-out-of-range", "value % 9223372036854775808", "directly recognized"),
            ("int64-minimum", "value // -9223372036854775808", "directly recognized"),
            ("negative-out-of-range", "value % -9223372036854775809", "directly recognized"),
            ("folded-expression", "value // (1 + 1)", "directly recognized"),
            ("nested-sign", "value % --2", "directly recognized"),
        )
        for name, expression, message in cases:
            with self.subTest(name=name):
                source = (
                    "def f(value: int, divisor: int) -> int:\n"
                    f"    return {expression}\n"
                )
                result = convert(source)
                self._assert_numeric_rejection(result, "PYC3702", message)

    def _assert_numeric_rejection(self, result, code: str, message: str) -> None:
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertIsNone(result.generated_c)
        self.assertIsNone(result.output_fingerprint)
        self.assertEqual(len(result.diagnostics), 1)
        diagnostic = result.diagnostics[0]
        self.assertEqual(diagnostic.code, code)
        self.assertEqual(diagnostic.stage, "analysis.plan")
        self.assertIn(message, diagnostic.message)
        self.assertIsNotNone(diagnostic.source_span)
        self.assertEqual(diagnostic.source_module_id, "main")
        self.assertEqual(diagnostic.source_logical_name, "main.py")
        self.assertTrue(
            all(item.startswith("python-node:") for item in diagnostic.fact_references)
        )
        self.assertEqual(
            diagnostic.obligation_references,
            ("phase14-proved-floor-arithmetic",),
        )
        self.assertEqual(result.stage_artifact.kind, "python_ir")
        self.assertNotIn("helper_requirements", result.stage_artifact.payload)
        self.assertEqual(list(result.decision_trace["helper_manifest"]), [])


if __name__ == "__main__":
    unittest.main()
