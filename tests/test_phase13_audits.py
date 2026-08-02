from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from pycforge.laboratory.audits import (
    audit_architecture,
    audit_containers,
    audit_modules,
    audit_records,
    audit_rules,
    audit_transition,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase13AuditTests(unittest.TestCase):
    def test_architecture_proves_the_separate_record_boundary(self) -> None:
        report = audit_architecture(ROOT)
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["record_analysis_present"])
        self.assertTrue(report["record_lowering_present"])
        self.assertFalse(report["record_analysis_depends_on_c_ir"])

    def test_active_registry_contains_all_cumulative_record_rules(self) -> None:
        report = audit_rules(ROOT)
        self.assertTrue(report["passed"], report)
        self.assertEqual(
            report["active_rule_set"],
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertTrue(report["active_registry_includes_records"])
        self.assertTrue(report["active_registry_includes_numeric"])
        self.assertEqual(len(report["phase13_required_rules"]), 7)
        self.assertEqual(report["phase14_required_rules"], ["phase14.numeric.floor_arithmetic"])
        self.assertEqual(report["missing_phase14_rules"], [])
        self.assertEqual(report["missing_phase13_rules"], [])
        self.assertEqual(report["missing_phase12_rules"], [])
        self.assertEqual(report["missing_phase11_rules"], [])
        self.assertEqual(report["missing_phase9_rules"], [])

    def test_cumulative_container_and_module_audits_use_active_c_ir(self) -> None:
        containers = audit_containers(ROOT)
        modules = audit_modules(ROOT)
        self.assertTrue(containers["passed"], containers)
        self.assertTrue(modules["passed"], modules)
        self.assertEqual(containers["active_c_ir_schema"], "c-ir/0.14.3")
        self.assertIn("c-ir/0.12", containers["historical_c_ir_schemas"])
        self.assertEqual(modules["active_c_ir_schema"], "c-ir/0.14.3")
        self.assertEqual(modules["historical_c_ir_schema"], "c-ir/0.12")

    def test_records_audit_closes_positive_negative_and_nonexecution_claims(self) -> None:
        report = audit_records(ROOT)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["record_fact_schema"], "fact-table/0.13")
        self.assertEqual(len(report["record_fact_tables"]), 6)
        self.assertEqual(len(report["record_rule_ids"]), 7)
        self.assertEqual(report["c_ir_schema"], "c-ir/0.14.3")
        self.assertTrue(report["generated_c_textually_valid"])
        self.assertTrue(report["deterministic"])
        self.assertTrue(report["helper_manifest_empty"])
        self.assertEqual(
            report["rejection_codes"],
            [f"PYC360{ordinal}" for ordinal in range(1, 8)],
        )
        self.assertEqual(report["cross_module_record_rejection_code"], "PYC3610")
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_phase13_transition_and_historical_transition_audits(self) -> None:
        for phase in ("phase_9", "phase_10", "phase_11", "phase_12"):
            with self.subTest(phase=phase):
                report = audit_transition(ROOT, phase)
                self.assertTrue(report["passed"], report)
        report = audit_transition(ROOT, "phase_13")
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["minimum_tests"], 224)
        self.assertGreaterEqual(report["required_tests"], report["minimum_tests"])
        self.assertIn("candidate_reseed.md", report["required_files"])
        self.assertIn("record_representation_decisions.md", report["required_files"])
        self.assertIn("release_fingerprint.json", report["required_files"])

    def test_records_audit_is_exposed_by_the_cli(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pycforge", "--format", "json", "audit", "records"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertTrue(report["passed"], report)
        self.assertFalse(report["generated_c_compiled_or_executed"])


if __name__ == "__main__":
    unittest.main()
