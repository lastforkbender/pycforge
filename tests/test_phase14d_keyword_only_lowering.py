from __future__ import annotations

import unittest

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.keyword_only_calls import (
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_TABLE_ID,
)
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


def function(payload: dict, name: str) -> dict:
    return next(
        item
        for item in payload["c_ir"]["declarations"]
        if item.get("kind") == "CFunctionDefinition"
        and item.get("identifier", {}).get("spelling") == name
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def binding_names(payload: dict) -> dict[str, str]:
    return {
        item["value"]["binding_id"]: item["value"]["source_name"]
        for item in table(payload, "binding-facts")["records"]
    }


def call_name(call: dict, names: dict[str, str]) -> str | None:
    return names.get(call.get("callee", {}).get("binding_id"))


def call_named(value: object, names: dict[str, str], expected: str) -> dict:
    return next(
        item
        for item in walk(value)
        if item.get("kind") == "CCallExpr"
        and call_name(item, names) == expected
    )


class Phase14DKeywordOnlyLoweringTests(unittest.TestCase):
    def converted(self, source: str, *, full: bool = False):
        result = convert(source, full=full)
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.generated_c)
        self.assertTrue(validate_c_text(result.generated_c or "").accepted)
        return result

    def test_actuals_stage_in_source_order_then_references_use_formal_order(self) -> None:
        source = (
            "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
            "    return left\n\n"
            "def run(x: int, y: bool, z: float) -> int:\n"
            "    return choose(ratio=z, left=x, flag=y)\n"
        )
        result = self.converted(source, full=True)
        payload = result.stage_artifact.payload
        names = binding_names(payload)
        run = function(payload, "run")
        target_call = call_named(run, names, "choose")
        argument_binding_ids = [item["binding_id"] for item in target_call["arguments"]]
        staging = [
            item
            for item in run["body"]["statements"]
            if item.get("kind") == "CVariableDeclaration"
            and item.get("identifier", {}).get("binding_id") in argument_binding_ids
        ]

        self.assertEqual(len(staging), 3)
        self.assertEqual(
            [names[item["initializer"]["binding_id"]] for item in staging],
            ["z", "x", "y"],
        )
        declaration_by_binding = {
            item["identifier"]["binding_id"]: item for item in staging
        }
        self.assertEqual(
            [
                names[declaration_by_binding[binding_id]["initializer"]["binding_id"]]
                for binding_id in argument_binding_ids
            ],
            ["x", "y", "z"],
        )
        self.assertEqual(
            [item["kind"] for item in target_call["arguments"]],
            ["CIdentifierRef", "CIdentifierRef", "CIdentifierRef"],
        )

        feature_plan = next(
            item
            for item in payload["rule_plans"]
            if item["rule_id"] == KEYWORD_ONLY_CALL_RULE_ID
        )
        mapped = [
            item
            for item in payload["source_output_mappings"]
            if item.get("rule_plan_id") == feature_plan["plan_id"]
        ]
        self.assertTrue(mapped)
        self.assertTrue(all(item["source_document_id"] for item in mapped))
        self.assertTrue(all(item["start_byte"] < item["end_byte"] for item in mapped))

    def test_nested_calls_execute_in_source_order_before_formal_call(self) -> None:
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
        names = binding_names(payload)
        run = function(payload, "run")
        calls = [
            call_name(item, names)
            for statement in run["body"]["statements"]
            for item in walk(statement)
            if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(calls, ["mark_float", "mark_int", "mark_bool", "choose"])

        choose = call_named(run, names, "choose")
        declarations = {
            item["identifier"]["binding_id"]: item
            for item in run["body"]["statements"]
            if item.get("kind") == "CVariableDeclaration"
        }

        def originating_call(binding_id: str) -> str | None:
            seen: set[str] = set()
            while binding_id not in seen:
                seen.add(binding_id)
                declaration = declarations.get(binding_id)
                if not declaration:
                    return None
                initializer = declaration.get("initializer", {})
                if initializer.get("kind") == "CCallExpr":
                    return call_name(initializer, names)
                if initializer.get("kind") != "CIdentifierRef":
                    return None
                binding_id = initializer["binding_id"]
            return None

        self.assertEqual(
            [originating_call(item["binding_id"]) for item in choose["arguments"]],
            ["mark_int", "mark_bool", "mark_float"],
        )

    def test_phase14c_keyword_call_composes_inside_keyword_only_actual(self) -> None:
        source = (
            "def inner(left: int, flag: bool) -> int:\n"
            "    return left\n\n"
            "def outer(head: int, *, tail: int) -> int:\n"
            "    return head\n\n"
            "def run(x: int, y: bool) -> int:\n"
            "    return outer(tail=inner(flag=y, left=x), head=x)\n"
        )
        payload = self.converted(source).stage_artifact.payload
        names = binding_names(payload)
        run = function(payload, "run")
        calls = [
            call_name(item, names)
            for statement in run["body"]["statements"]
            for item in walk(statement)
            if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(calls, ["inner", "outer"])
        self.assertEqual(
            len(table(payload, "keyword-call-binding-facts")["records"]),
            1,
        )
        self.assertEqual(
            len(table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"]),
            1,
        )
        outer = call_named(run, names, "outer")
        self.assertTrue(
            all(item.get("kind") == "CIdentifierRef" for item in outer["arguments"])
        )

    def test_keyword_only_preludes_remain_inside_phase14b_guard(self) -> None:
        source = (
            "def mark(value: bool) -> bool:\n    return value\n\n"
            "def pair(left: bool, *, right: bool) -> bool:\n    return left\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return a and pair(right=mark(b), left=a)\n"
        )
        payload = self.converted(source).stage_artifact.payload
        names = binding_names(payload)
        run = function(payload, "run")
        guard = next(
            item
            for item in run["body"]["statements"]
            if item.get("node_id", "").startswith("c-bool-region-if-")
        )
        inside = [
            call_name(item, names)
            for item in walk(guard["then_block"])
            if item.get("kind") == "CCallExpr"
        ]
        outside = [
            call_name(item, names)
            for item in walk(run)
            if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(inside, ["mark", "pair"])
        self.assertEqual(inside, outside)
        self.assertFalse(
            any(
                item.get("kind") == "CCallExpr"
                for statement in run["body"]["statements"]
                if statement is not guard
                for item in walk(statement)
            )
        )

    def test_numeric_helper_actual_keeps_existing_helper_closure(self) -> None:
        source = (
            "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return sink(flag=flag, value=value // 2)\n"
        )
        result = self.converted(source)
        payload = result.stage_artifact.payload
        names = binding_names(payload)
        run = function(payload, "run")
        helper_binding = f"helper-binding:{FLOOR_DIV_REFERENCE.canonical}:function"
        calls = [
            item
            for statement in run["body"]["statements"]
            for item in walk(statement)
            if item.get("kind") == "CCallExpr"
        ]
        self.assertEqual(
            [
                "floor-helper"
                if item["callee"]["binding_id"] == helper_binding
                else call_name(item, names)
                for item in calls
            ],
            ["floor-helper", "sink"],
        )
        self.assertEqual(payload["helper_requirements"], [FLOOR_DIV_REFERENCE.canonical])
        self.assertEqual(
            [item["reference"] for item in payload["helper_manifest"]],
            [FLOOR_DIV_REFERENCE.canonical],
        )


if __name__ == "__main__":
    unittest.main()
