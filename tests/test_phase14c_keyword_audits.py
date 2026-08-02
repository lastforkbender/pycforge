from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from pycforge.laboratory.audits import (
    audit_architecture,
    audit_conditional,
    audit_containers,
    audit_keyword,
    audit_modules,
    audit_numeric,
    audit_records,
    audit_rules,
)
from pycforge.laboratory.cli import main


ROOT = Path(__file__).resolve().parents[1]


class Phase14CKeywordAuditTests(unittest.TestCase):
    def test_architecture_and_rule_audits_publish_the_single_keyword_contract(self) -> None:
        architecture = audit_architecture(ROOT)
        rules = audit_rules(ROOT)

        self.assertTrue(architecture["passed"], architecture)
        self.assertTrue(architecture["active_contract_identities_valid"])
        self.assertTrue(architecture["keyword_contract_valid"])
        self.assertEqual(
            architecture["keyword_rule_id"],
            "phase14.keyword_call.exact_binding",
        )
        self.assertEqual(architecture["keyword_fact_schema"], "fact-table/0.14.2")

        self.assertTrue(rules["passed"], rules)
        self.assertTrue(rules["active_registry_includes_keyword_calls"])
        self.assertEqual(
            rules["phase14c_required_rules"],
            ["phase14.keyword_call.exact_binding"],
        )
        keyword_rules = [
            item
            for item in rules["manifest"]
            if item["rule_id"].startswith("phase14.keyword_call.")
        ]
        self.assertEqual(
            keyword_rules,
            [
                {
                    "rule_id": "phase14.keyword_call.exact_binding",
                    "rule_version": "0.14.2",
                    "node_kind": "Call",
                    "specificity": [80],
                }
            ],
        )

    def test_keyword_audit_proves_positive_negative_historical_and_nonexecution_evidence(self) -> None:
        report = audit_keyword(ROOT)

        self.assertTrue(report["passed"], report)
        self.assertTrue(report["active_contract_identities_valid"])
        self.assertEqual(report["keyword_fact_count"], 2)
        self.assertTrue(report["independent_fact_and_plan_validation"])
        self.assertTrue(report["source_order_staging_and_formal_reference_permutation_valid"])
        self.assertEqual(report["direct_source_to_parameter_ordinals"], [0, 1, 2])
        self.assertEqual(report["direct_parameter_to_source_ordinals"], [0, 1, 2])
        self.assertEqual(report["reordered_source_to_parameter_ordinals"], [2, 0, 1])
        self.assertEqual(report["reordered_parameter_to_source_ordinals"], [1, 2, 0])
        self.assertTrue(report["cross_module_valid"])
        self.assertEqual(report["cross_module_target_module"], "lib")
        self.assertEqual(report["cross_module_order"], ["lib", "app"])
        self.assertEqual(report["rejection_case_count"], 16)
        self.assertTrue(report["rejections_exact_and_publish_no_c"])
        self.assertTrue(report["phase14b_exact_keyword_rejection"])
        self.assertTrue(report["deterministic"])
        self.assertTrue(report["fresh_process_deterministic"])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_cumulative_audits_publish_active_0143_identities(self) -> None:
        for audit in (
            audit_containers,
            audit_modules,
            audit_records,
            audit_numeric,
            audit_conditional,
        ):
            with self.subTest(audit=audit.__name__):
                report = audit(ROOT)
                self.assertTrue(report["passed"], report)
                self.assertTrue(report["active_contract_identities_valid"], report)
                self.assertEqual(
                    report["active_contracts"]["rule_set"],
                    "phase14-required-keyword-only-calls-v0.14.3",
                )
                self.assertEqual(
                    report["active_contracts"]["renderer"],
                    "c-renderer-v0.14.3",
                )
                self.assertEqual(
                    report["active_contracts"]["c_ir"],
                    "c-ir/0.14.3",
                )
                self.assertEqual(
                    report["active_contracts"]["generated_c"],
                    "generated-c/0.14.3",
                )

    def test_cli_exposes_keyword_audit(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--format", "json", "audit", "keyword"])

        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["audit"], "keyword")
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["rejection_case_count"], 16)


if __name__ == "__main__":
    unittest.main()
