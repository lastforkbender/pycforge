from __future__ import annotations

import json
import unittest
from pathlib import Path

from pycforge import __version__
from pycforge.converter.contracts.configuration import (
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE12_MODULE_POLICY,
    PHASE12_RENDERER,
    PHASE12_RULE_SET,
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONVERTER_CONTRACT_VERSION,
    CONVERSION_PLAN_SCHEMA,
    GENERATED_C_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE12_C_IR_SCHEMA,
    PHASE12_CONVERSION_PLAN_SCHEMA,
    PHASE12_GENERATED_C_SCHEMA,
    PHASE13_C_IR_SCHEMA,
    PHASE13_CONVERSION_PLAN_SCHEMA,
    PHASE13_GENERATED_C_SCHEMA,
    RECORD_FACT_SCHEMA,
)
from pycforge.ide import WORKSPACE_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataAndPhase122CustodyTests(unittest.TestCase):
    def test_active_package_identity_is_phase15c_and_converter_remains_phase14d(self) -> None:
        self.assertEqual(__version__, "0.15.2")
        self.assertIn('version = "0.15.2"', (ROOT / "pyproject.toml").read_text())
        self.assertIn("Version: 0.15.2", (ROOT / "pycforge.egg-info/PKG-INFO").read_text())
        self.assertEqual(CONVERTER_CONTRACT_VERSION, "0.14.3")
        self.assertEqual(WORKSPACE_CONTRACT_VERSION, "pycforge-workspace/0.5")
        self.assertTrue((ROOT / "specifications/static_records.md").is_file())
        self.assertTrue((ROOT / "specifications/phase14a_bounded_integer_divmod.md").is_file())
        self.assertTrue((ROOT / "PyCForge_Phase_13_v0_13_0_Project_Handoff.txt").is_file())
        self.assertTrue((ROOT / "PyCForge_Phase_14A_v0_14_0_Project_Handoff.txt").is_file())

    def test_active_phase14_and_historical_phase13_and_phase12_identities_are_distinct(self) -> None:
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(C_IR_SCHEMA, "c-ir/0.14.3")
        self.assertEqual(GENERATED_C_SCHEMA, "generated-c/0.14.3")
        self.assertEqual(NUMERIC_FACT_SCHEMA, "fact-table/0.14")
        self.assertEqual(RECORD_FACT_SCHEMA, "fact-table/0.13")
        self.assertEqual(
            DEFAULT_RULE_SET,
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        self.assertEqual(DEFAULT_RENDERER, "c-renderer-v0.14.3")
        self.assertEqual(DEFAULT_NUMERIC_POLICY, "phase14-proved-floor-arithmetic-v0.14")
        self.assertEqual(DEFAULT_MODULE_POLICY, "phase13-explicit-record-modules-v0.13")
        self.assertEqual(
            DEFAULT_RECORD_POLICY,
            "phase13-immutable-automatic-records-v0.13",
        )

        self.assertEqual(PHASE13_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.13")
        self.assertEqual(PHASE13_C_IR_SCHEMA, "c-ir/0.13")
        self.assertEqual(PHASE13_GENERATED_C_SCHEMA, "generated-c/0.13")
        self.assertEqual(PHASE13_RULE_SET, "phase13-static-records-v0.13")
        self.assertEqual(PHASE13_RENDERER, "c-renderer-v0.13")

        self.assertEqual(PHASE12_CONVERSION_PLAN_SCHEMA, "conversion-plan/0.12")
        self.assertEqual(PHASE12_C_IR_SCHEMA, "c-ir/0.12")
        self.assertEqual(PHASE12_GENERATED_C_SCHEMA, "generated-c/0.12")
        self.assertEqual(PHASE12_RULE_SET, "phase12-explicit-module-bundles-v0.12")
        self.assertEqual(PHASE12_RENDERER, "c-renderer-v0.12")
        self.assertEqual(
            PHASE12_MODULE_POLICY,
            "phase12-explicit-sourcebundle-modules-v0.12",
        )

    def test_promoted_0122_workspace_evidence_remains_historical_custody(self) -> None:
        transition = json.loads(
            (ROOT / "transition/workspace_hardening_0_12_2/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(transition["version"], "0.12.2")
        self.assertEqual(transition["status"], "promoted")
        self.assertFalse(transition["opens_new_converter_phase"])

        report = json.loads(
            (ROOT / "evidence/pycforge_workspace_0_12_2/release_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["release_version"], "0.12.2")
        self.assertEqual(report["status"], "promoted")
        self.assertFalse(report["phase_13_opened"])

        opening = json.loads(
            (ROOT / "transition/phase_13/baseline_fingerprint.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(opening["status"], "authenticated-before-phase-13-edits")
        self.assertEqual(
            opening["predecessor_archive_sha256"],
            "6a603684001f2cb2e9365d7e9b318f1a95dbe95b2cb36cf8821c30403c1754d0",
        )
        self.assertEqual(
            opening["predecessor_tree_sha256"],
            "434981decfd2b2fc2b344f5b9a3b37377396376c2e0a8c8ed00bb9fa9077d765",
        )
        self.assertEqual(
            opening["predecessor_converter_subtree_sha256"],
            "4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51",
        )

    def test_phase13_docs_publish_the_closed_record_and_next_phase_boundary(self) -> None:
        record_spec = (ROOT / "specifications/static_records.md").read_text(
            encoding="utf-8"
        )
        for phrase in (
            "1–64",
            "`int`, `float`, or `bool`",
            "structural declaration evidence",
            "left to right and exactly once",
            "`typedef struct`",
            "`const` aggregate",
            "There is no heap allocation",
            "ordinary method",
            "record names are not importable",
            "does not\ncompile, link, load, execute",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, record_spec)

        feature_matrix = json.loads(
            (ROOT / "specifications/feature_matrix.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(feature_matrix["schema"], "pycforge.feature-matrix/0.14.3")
        self.assertEqual(
            feature_matrix["record_policy"],
            "phase13-immutable-automatic-records-v0.13",
        )
        class_entries = [
            item for item in feature_matrix["entries"]
            if item["construct"] == "ClassDef"
        ]
        self.assertTrue(any(item["state"] == "supported" for item in class_entries))
        self.assertFalse(any(item["state"] == "planned" for item in class_entries))

        handoff = (
            ROOT / "PyCForge_Phase_13_v0_13_0_Project_Handoff.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("no Windows execution claim", handoff)
        self.assertIn("Phase 14 has not started", handoff)

    def test_workspace_spec_keeps_professional_safety_boundary(self) -> None:
        specification = (
            ROOT / "specifications/pycforge_workspace_legacy_0_1.md"
        ).read_text(encoding="utf-8")
        required = (
            "Converter boundary",
            "Explicit bundle workspace",
            "quantum visibility rail",
            "Find and replace",
            "Diagnostics and inspection",
            "Linked generated-C save",
            "atomic writer",
            "PyCForge visual and accessibility contract",
            "Presentation persistence",
            "last file-dialog directory",
            "reopened only after explicit user action",
            "not persist unsaved Python contents",
            "never writes the linked",
            "does not compile, link, load, or execute",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, specification)


if __name__ == "__main__":
    unittest.main()
