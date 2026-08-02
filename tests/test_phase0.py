from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Phase0ContractTests(unittest.TestCase):
    def test_manifest_files_exist(self) -> None:
        manifest = json.loads((ROOT / "transition/phase_0/manifest.json").read_text())
        self.assertFalse([p for p in manifest["required_files"] if not (ROOT / p).exists()])

    def test_observer_schemas_are_separate(self) -> None:
        trace = json.loads((ROOT / "schemas/decision_trace.schema.json").read_text())
        telemetry = json.loads((ROOT / "schemas/telemetry.schema.json").read_text())
        self.assertNotEqual(trace["$id"], telemetry["$id"])
        self.assertIn("rule_decisions", trace["properties"])
        self.assertNotIn("rule_decisions", telemetry["properties"])

    def test_approximations_default_empty(self) -> None:
        plans = json.loads((ROOT / "fixtures/first_milestone/expected_ruleplans.json").read_text())
        self.assertEqual(plans["approximations"], [])

    def test_validation_is_deterministic(self) -> None:
        cmd = [sys.executable, str(ROOT / "tools/validate_phase0.py")]
        baseline = ROOT / "transition/phase_0/baseline_fingerprint.json"
        sealed_bytes = baseline.read_bytes()
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            first = baseline.read_text()
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            second = baseline.read_text()
            self.assertEqual(first, second)
        finally:
            baseline.write_bytes(sealed_bytes)

    def test_mandatory_gui_dependency_and_no_toolchain_declared(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text().lower()
        self.assertIn('dependencies = ["pyqt5>=5.15.11,<6"]', pyproject)
        self.assertNotIn("[project.optional-dependencies]", pyproject)
        self.assertNotIn("gcc", pyproject)
        self.assertNotIn("clang", pyproject)


if __name__ == "__main__":
    unittest.main()
