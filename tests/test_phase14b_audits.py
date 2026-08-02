from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.core.artifact_io import save_artifact
from pycforge.converter.io.atomic_writer import AtomicWriter
from pycforge.laboratory.audits import (
    audit_architecture,
    audit_conditional,
    audit_rules,
    audit_transition,
)


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


class Phase14BAuditTests(unittest.TestCase):
    def test_architecture_and_rules_recognize_the_bounded_region_slice(self) -> None:
        architecture = audit_architecture(ROOT)
        self.assertTrue(architecture["passed"], architecture)
        self.assertTrue(architecture["conditional_analysis_present"])
        self.assertTrue(architecture["conditional_validation_present"])
        self.assertTrue(architecture["conditional_lowering_present"])
        self.assertFalse(architecture["conditional_analysis_depends_on_c_ir"])
        self.assertFalse(
            architecture["conditional_validation_depends_on_producer_or_lowerer"]
        )
        self.assertLessEqual(architecture["cumulative_lowerer_lines"], 1000)

        rules = audit_rules(ROOT)
        self.assertTrue(rules["passed"], rules)
        self.assertTrue(rules["active_registry_includes_conditional_regions"])
        self.assertTrue(rules["active_contract_identities_valid"])
        self.assertEqual(
            rules["active_rule_set"],
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(
            rules["phase14b_required_rules"],
            [
                "phase14.conditional.boolean_region",
                "phase14.conditional.comparison_region",
            ],
        )
        self.assertEqual(rules["missing_phase14b_rules"], [])

    def test_independent_conditional_audit_closes_the_vertical_contract(self) -> None:
        report = audit_conditional(ROOT)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["conditional_fact_count"], 3)
        self.assertEqual(report["conditional_rule_plan_count"], 3)
        self.assertEqual(report["expected_region_guard_count"], 5)
        self.assertEqual(report["c_ir_region_guard_count"], 5)
        self.assertTrue(report["flat_branch_containment_valid"])
        self.assertTrue(report["boolean_accumulator_reuse_valid"])
        self.assertTrue(report["chained_middle_reuse_valid"])
        self.assertTrue(report["c_ir_node_ids_unique"])
        self.assertTrue(report["observer_evidence_valid"])
        self.assertTrue(report["phase14a_exact_compatibility"])
        self.assertTrue(report["active_no_region_output_compatible"])
        self.assertEqual(
            report["composed_helper_references"],
            ["pycf.i64.floor_div@1.0.0"],
        )
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_phase14b_opening_is_recognized_without_relabeling_phase14(self) -> None:
        sealed = audit_transition(ROOT, "phase_14")
        self.assertTrue(sealed["passed"], sealed)
        self.assertEqual(sealed["minimum_tests"], 335)
        self.assertEqual(sealed["required_tests"], 365)
        self.assertIn("manifest.json", sealed["required_files"])
        self.assertIn("gate_evidence.md", sealed["required_files"])
        self.assertIn("release_fingerprint.json", sealed["required_files"])

        opening = audit_transition(ROOT, "phase_14b")
        self.assertTrue(opening["passed"], opening)
        self.assertEqual(opening["opening_status"], "entry-feasibility-only")
        self.assertEqual(opening["authenticated_predecessor_tests"], 365)
        self.assertFalse(opening["manifest_required"])
        self.assertFalse(opening["promotion_claimed"])
        self.assertNotIn("manifest.json", opening["required_files"])
        self.assertNotIn("gate_evidence.md", opening["required_files"])

    def test_conditional_audit_is_exposed_by_the_cli(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pycforge",
                "--format",
                "json",
                "audit",
                "conditional",
            ],
            cwd=ROOT,
            env=ENV,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["active_contracts"]["c_ir"], "c-ir/0.14.3")
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_cli_inspect_accepts_the_current_generated_artifact_identity(self) -> None:
        result = PythonToCConverter().convert(
            ConversionRequest.from_source("def run() -> int:\n    return 1\n")
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertIsNotNone(result.stage_artifact)
        assert result.stage_artifact is not None
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "current-stage.json"
            save_artifact(path, result.stage_artifact, AtomicWriter())
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pycforge",
                    "--format",
                    "json",
                    "inspect",
                    str(path),
                ],
                cwd=ROOT,
                env=ENV,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        inspected = json.loads(completed.stdout)
        self.assertEqual(inspected["kind"], "generated_c")
        self.assertEqual(inspected["schema_version"], "0.14.3")


if __name__ == "__main__":
    unittest.main()
