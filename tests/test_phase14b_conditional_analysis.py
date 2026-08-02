from __future__ import annotations

import unittest

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.conditional_regions import (
    ConditionalRegionAnalysisCanceled,
    ConditionalRegionAnalyzer,
)
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.frontend.normalizer import PythonNormalizer
from pycforge.converter.frontend.parser import Python311ParserAdapter
from pycforge.converter.frontend.source_document import SourceDocument


def normalized(source: str) -> dict:
    document = SourceDocument.create("app.py", source)
    tree = Python311ParserAdapter().parse(document, "3.11")
    return PythonNormalizer().normalize(tree, document).to_dict()


def node_map(module: dict) -> dict[str, dict]:
    return {item["node_id"]: item for item in module["nodes"]}


def function_node(module: dict, name: str) -> dict:
    return next(
        item
        for item in module["nodes"]
        if item["kind"] == "FunctionDef" and item["fields"]["name"] == name
    )


def inferred_categories(
    module: dict,
    *,
    boolean_names: tuple[str, ...] = (),
    floating_names: tuple[str, ...] = (),
    boolean_calls: tuple[str, ...] = (),
    floating_calls: tuple[str, ...] = (),
) -> dict[str, ValueCategory]:
    """Provide exact scalar categories without depending on the planning pass."""

    nodes = node_map(module)
    result: dict[str, ValueCategory] = {}
    for node in module["nodes"]:
        kind = node["kind"]
        fields = node.get("fields", {})
        if kind == "Constant":
            value = fields.get("value")
            if isinstance(value, bool):
                result[node["node_id"]] = ValueCategory.BOOLEAN
            elif isinstance(value, int):
                result[node["node_id"]] = ValueCategory.INTEGER
            elif isinstance(value, float):
                result[node["node_id"]] = ValueCategory.FLOAT
        elif kind == "Name":
            name = fields.get("id")
            if name in boolean_names or name == "bool":
                result[node["node_id"]] = ValueCategory.BOOLEAN
            elif name in floating_names or name == "float":
                result[node["node_id"]] = ValueCategory.FLOAT
            elif name == "int" or (
                isinstance(name, str)
                and name not in {*boolean_calls, *floating_calls}
                and name not in {"flag", "predicate", "choose", "ratio"}
            ):
                result[node["node_id"]] = ValueCategory.INTEGER
        elif kind in {"BoolOp", "Compare"}:
            result[node["node_id"]] = ValueCategory.BOOLEAN
        elif kind in {"Attribute", "Subscript"}:
            result[node["node_id"]] = ValueCategory.INTEGER

    # Normalize expression categories to a fixed point.  Calls depend only on
    # their direct target name; wrappers inherit the existing operand category.
    for _ in range(len(module["nodes"]) + 1):
        changed = False
        for node in module["nodes"]:
            node_id = node["node_id"]
            fields = node.get("fields", {})
            value: ValueCategory | None = None
            if node["kind"] == "Call":
                target = nodes.get(fields.get("func"), {}).get("fields", {}).get("id")
                value = (
                    ValueCategory.BOOLEAN
                    if target in boolean_calls
                    else ValueCategory.FLOAT
                    if target in floating_calls
                    else ValueCategory.INTEGER
                )
            elif node["kind"] == "UnaryOp":
                operator = nodes.get(fields.get("op"), {}).get("kind")
                value = (
                    ValueCategory.BOOLEAN
                    if operator == "Not"
                    else result.get(fields.get("operand"))
                )
            elif node["kind"] == "BinOp":
                operator = nodes.get(fields.get("op"), {}).get("kind")
                value = (
                    ValueCategory.FLOAT
                    if operator == "Div"
                    else result.get(fields.get("left"), ValueCategory.INTEGER)
                )
            if value is not None and result.get(node_id) is not value:
                result[node_id] = value
                changed = True
        if not changed:
            break
    return result


def analyze(
    module: dict,
    *,
    categories: dict[str, ValueCategory],
    supported_calls: frozenset[str] = frozenset(),
    numeric_operations: frozenset[str] = frozenset(),
    container_accesses: frozenset[str] = frozenset(),
    record_accesses: frozenset[str] = frozenset(),
    cancellation: object | None = None,
):
    owner = function_node(module, "run")
    return ConditionalRegionAnalyzer(
        module,
        categories=categories,
        function_records={
            owner["node_id"]: {
                "module_id": "app",
                "document_id": "document-app",
                "logical_name": "app.py",
            }
        },
        owner_by_node={item["node_id"]: owner["node_id"] for item in module["nodes"]},
        supported_call_node_ids=supported_calls,
        numeric_operation_node_ids=numeric_operations,
        supported_container_access_node_ids=container_accesses,
        supported_record_access_node_ids=record_accesses,
        cancellation=cancellation or CancellationToken(),
    ).analyze()


class Phase14BConditionalAnalysisTests(unittest.TestCase):
    def test_boolean_fact_records_unconditional_prefix_and_and_polarity(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return flag(a) and b and flag(c)\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        result = analyze(
            module,
            categories=inferred_categories(
                module,
                boolean_names=("a", "b", "c", "value"),
                boolean_calls=("flag",),
            ),
            supported_calls=calls,
        )

        self.assertEqual(len(result.regions), 1)
        fact = result.regions[0]
        self.assertEqual(fact.region_kind.value, "boolean-short-circuit")
        self.assertEqual(fact.operator_kinds, ("And",))
        self.assertEqual(fact.unconditional_prefix_count, 1)
        self.assertEqual(fact.evaluation_order, fact.operand_node_ids)
        self.assertTrue(fact.operands_evaluated_once)
        self.assertEqual(fact.result_category, "boolean-like")
        self.assertEqual(fact.result_c_type, "bool")
        self.assertEqual(fact.allocation_model, "none")
        self.assertEqual(fact.cleanup_model, "none")
        self.assertEqual(fact.runtime_failure_channel, "unchanged")
        self.assertEqual(
            [item.evaluation_mode.value for item in fact.placements],
            ["unconditional", "guarded", "guarded"],
        )
        self.assertEqual(
            [item.guard_polarity.value for item in fact.placements],
            ["none", "when-result-true", "when-result-true"],
        )
        self.assertEqual(
            [item.guard_after_operand_ordinal for item in fact.placements],
            [None, 0, 1],
        )
        self.assertEqual(set(fact.prerequisite_node_ids), set(calls))

    def test_or_fact_uses_false_gates_and_nested_calls_close_in_source_order(self) -> None:
        source = (
            "def predicate(value: bool) -> bool:\n"
            "    return value\n\n"
            "def choose(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return a or choose(predicate(b))\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        result = analyze(
            module,
            categories=inferred_categories(
                module,
                boolean_names=("a", "b", "value"),
                boolean_calls=("predicate", "choose"),
            ),
            supported_calls=calls,
        )
        fact = result.regions[0]
        guarded = fact.placements[1]
        self.assertEqual(fact.operator_kinds, ("Or",))
        self.assertEqual(guarded.guard_polarity.value, "when-result-false")
        self.assertTrue(guarded.requires_statement_prelude)
        self.assertEqual(guarded.prerequisite_node_ids, fact.prerequisite_node_ids)
        nodes = node_map(module)
        call_names = {
            item["node_id"]: nodes[item["fields"]["func"]]["fields"]["id"]
            for item in module["nodes"]
            if item["kind"] == "Call"
        }
        self.assertEqual(
            [call_names[item] for item in guarded.prerequisite_node_ids],
            ["predicate", "choose"],
        )

    def test_nested_mixed_boolean_regions_are_proved_independently(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool, c: bool) -> bool:\n"
            "    return a and (b or flag(c))\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        result = analyze(
            module,
            categories=inferred_categories(
                module,
                boolean_names=("a", "b", "c", "value"),
                boolean_calls=("flag",),
            ),
            supported_calls=calls,
        )

        self.assertEqual(len(result.regions), 2)
        by_operator = {item.operator_kinds: item for item in result.regions}
        self.assertEqual(
            by_operator[("And",)].placements[1].guard_polarity.value,
            "when-result-true",
        )
        self.assertEqual(
            by_operator[("Or",)].placements[1].guard_polarity.value,
            "when-result-false",
        )
        self.assertTrue(
            set(by_operator[("Or",)].prerequisite_node_ids).issubset(
                by_operator[("And",)].prerequisite_node_ids
            )
        )

    def test_chained_call_and_arithmetic_operands_are_guarded_after_two_values(self) -> None:
        source = (
            "def value(item: int) -> int:\n"
            "    return item\n\n"
            "def run(a: int, b: int, c: int, d: int) -> bool:\n"
            "    return a < b < value(c) < d + 1\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        result = analyze(
            module,
            categories=inferred_categories(module),
            supported_calls=calls,
        )

        self.assertEqual(len(result.regions), 1)
        fact = result.regions[0]
        self.assertEqual(fact.region_kind.value, "chained-comparison")
        self.assertEqual(fact.operator_kinds, ("Lt", "Lt", "Lt"))
        self.assertEqual(fact.unconditional_prefix_count, 2)
        self.assertEqual(
            [item.evaluation_mode.value for item in fact.placements],
            ["unconditional", "unconditional", "guarded", "guarded"],
        )
        self.assertEqual(
            [item.guard_polarity.value for item in fact.placements],
            ["none", "none", "when-result-true", "when-result-true"],
        )
        self.assertTrue(fact.placements[2].requires_statement_prelude)
        self.assertFalse(fact.placements[3].requires_statement_prelude)
        self.assertFalse(fact.placements[2].legacy_direct_safe)
        self.assertFalse(fact.placements[3].legacy_direct_safe)

    def test_promoted_numeric_and_existing_container_record_reads_are_compositional(self) -> None:
        source = (
            "def run(a: int, b: int, values: int, record: int) -> bool:\n"
            "    return a < b < (values[0] // 2) < record.value\n"
        )
        module = normalized(source)
        numeric = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "BinOp"
        )
        accesses = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Subscript"
        )
        fields = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Attribute"
        )
        result = analyze(
            module,
            categories=inferred_categories(module),
            numeric_operations=numeric,
            container_accesses=accesses,
            record_accesses=fields,
        )

        fact = result.regions[0]
        self.assertEqual(fact.unconditional_prefix_count, 2)
        self.assertEqual(set(fact.prerequisite_node_ids), set(numeric))
        self.assertTrue(fact.placements[2].requires_statement_prelude)
        self.assertFalse(fact.placements[3].requires_statement_prelude)

    def test_regions_and_ids_are_deterministic(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return flag(a) and flag(b)\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        categories = inferred_categories(
            module,
            boolean_names=("a", "b", "value"),
            boolean_calls=("flag",),
        )
        first = analyze(module, categories=categories, supported_calls=calls)
        second = analyze(module, categories=categories, supported_calls=calls)
        self.assertEqual(
            [item.to_dict() for item in first.regions],
            [item.to_dict() for item in second.regions],
        )
        self.assertRegex(first.regions[0].region_id, r"^conditional-region-[0-9a-f]{20}$")

    def test_cancellation_during_region_construction_publishes_no_analysis(self) -> None:
        source = (
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return flag(a) and flag(b)\n"
        )
        module = normalized(source)
        calls = frozenset(
            item["node_id"] for item in module["nodes"] if item["kind"] == "Call"
        )
        token = CancellationToken()
        owner = function_node(module, "run")

        class CancelOnRegion(ConditionalRegionAnalyzer):
            def _region(self, node, kind):
                result = super()._region(node, kind)
                token.cancel()
                return result

        analyzer = CancelOnRegion(
            module,
            categories=inferred_categories(
                module,
                boolean_names=("a", "b", "value"),
                boolean_calls=("flag",),
            ),
            function_records={
                owner["node_id"]: {
                    "module_id": "app",
                    "document_id": "document-app",
                    "logical_name": "app.py",
                }
            },
            owner_by_node={item["node_id"]: owner["node_id"] for item in module["nodes"]},
            supported_call_node_ids=calls,
            numeric_operation_node_ids=frozenset(),
            cancellation=token,
        )
        with self.assertRaises(ConditionalRegionAnalysisCanceled):
            analyzer.analyze()


if __name__ == "__main__":
    unittest.main()
