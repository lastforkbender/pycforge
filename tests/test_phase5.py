from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.analysis.planning import FrozenRuleRegistry, RuleDefinition
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
FIRST_SLICE = "def add(a: int, b: int) -> int:\n    return a + b\n"


class Phase5Tests(unittest.TestCase):
    def convert(self, source: str = FIRST_SLICE, **kwargs):
        request = ConversionRequest.from_source(source, rule_set_version="phase5-planning-v0.5")
        return PythonToCConverter(Pipeline(Pipeline().stages[:-1])).convert(request, **kwargs)

    def test_pipeline_publishes_conversion_plan_without_c(self):
        result = self.convert()
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(result.last_completed_stage, "analysis.plan")
        self.assertEqual(result.stage_artifact.kind, "conversion_plan")
        self.assertEqual(result.stage_artifact.schema_version, "0.5")
        self.assertIsNone(result.generated_c)
        self.assertEqual(result.stage_artifact.payload["helper_requirements"], [])

    def test_first_slice_selects_function_add_return_and_name_plans(self):
        payload = self.convert().stage_artifact.payload
        rule_ids = {plan["rule_id"] for plan in payload["rule_plans"]}
        self.assertIn("phase6.function.annotated", rule_ids)
        self.assertIn("phase6.numeric.arithmetic", rule_ids)
        self.assertIn("phase6.return.simple", rule_ids)
        self.assertIn("phase6.name.bound", rule_ids)
        self.assertTrue(all(not plan["unresolved_obligations"] for plan in payload["rule_plans"]))

    def test_binding_identity_is_distinct_from_occurrence_identity(self):
        payload = self.convert().stage_artifact.payload
        binding_table = next(t for t in payload["fact_tables"] if t["table_id"] == "binding-facts")
        parameters = [r["value"] for r in binding_table["records"] if r["value"]["binding_kind"] == "parameter"]
        self.assertEqual({p["source_name"] for p in parameters}, {"a", "b"})
        for parameter in parameters:
            self.assertEqual(len(parameter["occurrence_node_ids"]), 1)
            self.assertNotEqual(parameter["binding_id"], parameter["occurrence_node_ids"][0])

    def test_nested_function_builds_immutable_scope_graph(self):
        source = "def outer(a: int) -> int:\n    def inner(b: int) -> int:\n        return b\n    return a\n"
        payload = self.convert(source).stage_artifact.payload
        scope_table = next(t for t in payload["fact_tables"] if t["table_id"] == "scope-facts")
        scopes = [r["value"] for r in scope_table["records"]]
        self.assertEqual(sum(s["scope_kind"] == "module" for s in scopes), 1)
        self.assertEqual(sum(s["scope_kind"] == "function" for s in scopes), 2)
        self.assertTrue(any(s["parent_scope_id"] is not None for s in scopes))

    def test_unknown_and_contradictory_categories_remain_distinct(self):
        source = "x = unknown\ny = 1 + 's'\n"
        payload = self.convert(source).stage_artifact.payload
        category_table = next(t for t in payload["fact_tables"] if t["table_id"] == "value-category-facts")
        values = {record["value"] for record in category_table["records"]}
        self.assertIn(ValueCategory.UNKNOWN.value, values)
        self.assertIn(ValueCategory.CONTRADICTORY.value, values)

    def test_fact_tables_publish_contract_metadata_and_sorted_keys(self):
        tables = self.convert().stage_artifact.payload["fact_tables"]
        for table in tables:
            self.assertEqual(table["schema_version"], "fact-table/0.5")
            self.assertEqual(table["producer_stage"], "analysis.plan")
            self.assertEqual(table["completeness"], "complete")
            self.assertTrue(table["invalidation_dependencies"])
            keys = [record["key"] for record in table["records"]]
            self.assertEqual(keys, sorted(keys))
            self.assertTrue(all(record["provenance"]["source_node_ids"] for record in table["records"]))

    def test_registry_is_independent_of_registration_order(self):
        predicate = lambda node, cats: True
        a = RuleDefinition("a", "1", "Constant", (20,), predicate, ())
        b = RuleDefinition("b", "1", "Constant", (10,), predicate, ())
        node = {"node_id": "py-x", "kind": "Constant", "fields": {}}
        categories = {"py-x": ValueCategory.INTEGER}
        left = FrozenRuleRegistry((a, b)).select(node, categories, "decision")
        right = FrozenRuleRegistry((b, a)).select(node, categories, "decision")
        self.assertEqual(left.rule_id, right.rule_id)
        self.assertEqual(left.plan_id, right.plan_id)

    def test_equal_specificity_overlap_is_rejected(self):
        predicate = lambda node, cats: True
        a = RuleDefinition("a", "1", "Constant", (10,), predicate, ())
        b = RuleDefinition("b", "1", "Constant", (10,), predicate, ())
        with self.assertRaises(ValueError):
            FrozenRuleRegistry((a, b))

    def test_generated_names_are_unique_and_deterministic(self):
        source = "x = 1\ndef f(x: int) -> int:\n    return x\n"
        first = self.convert(source).stage_artifact.payload["generated_name_plans"]
        second = self.convert(source).stage_artifact.payload["generated_name_plans"]
        self.assertEqual(first, second)
        names = [item["generated_name"] for item in first]
        self.assertEqual(len(names), len(set(names)))

    def test_representation_unknown_is_explicitly_unresolved(self):
        payload = self.convert("x = unknown\n").stage_artifact.payload
        unresolved = [p for p in payload["representation_plans"] if p["c_type"] is None and p["unresolved_obligations"]]
        self.assertTrue(unresolved)
        self.assertTrue(all(p["passing"] == "unresolved" for p in unresolved))

    def test_analysis_validator_rejects_supported_decision_without_plan(self):
        payload = json.loads(json.dumps(dict(self.convert().stage_artifact.payload)))
        supported = next(item for item in payload["support_decisions"] if item["state"].startswith("Supported"))
        supported["rule_plan_id"] = None
        valid, message = validate_analysis_payload(payload)
        self.assertFalse(valid)
        self.assertIn("lacks exactly one RulePlan", message)

    def test_observers_do_not_change_analysis_artifact(self):
        plain = self.convert()
        observed = self.convert(observation=ObservationOptions("Full", True), inject_trace_failure=True, inject_telemetry_failure=True)
        self.assertEqual(plain.stage_artifact.artifact_fingerprint, observed.stage_artifact.artifact_fingerprint)
        self.assertEqual(dict(plain.stage_artifact.payload), dict(observed.stage_artifact.payload))

    def test_cross_process_conversion_plan_determinism(self):
        code = (
            "from pycforge import *;import json;"
            f"r=PythonToCConverter(__import__('pycforge.converter.core.pipeline',fromlist=['Pipeline']).Pipeline(__import__('pycforge.converter.core.pipeline',fromlist=['Pipeline']).Pipeline().stages[:-1])).convert(ConversionRequest.from_source({FIRST_SLICE!r},rule_set_version='phase5-planning-v0.5'));"
            "print(json.dumps(dict(r.stage_artifact.payload),sort_keys=True,separators=(',',':')),end='')"
        )
        a = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=ENV)
        b = subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=ENV)
        self.assertEqual(a, b)

    def test_no_lowering_or_generated_c_is_present(self):
        payload_text = json.dumps(dict(self.convert().stage_artifact.payload), sort_keys=True)
        self.assertNotIn("generated_c", payload_text)
        self.assertNotIn("c_ir", payload_text)
        self.assertFalse((ROOT / "pycforge/converter/rules/lowering.py").exists())


if __name__ == "__main__":
    unittest.main()
