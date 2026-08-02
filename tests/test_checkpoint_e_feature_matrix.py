from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from pycforge.laboratory.checkpoint_e import (
    FEATURE_MATRIX_ENTRY_COUNT,
    FEATURE_MATRIX_SCHEMA,
    FEATURE_MATRIX_SHA256,
    FEATURE_MATRIX_WITNESSES,
    FEATURE_MATRIX_WITNESS_ORDER,
    UNLISTED_DEFAULT_WITNESS,
    audit_feature_matrix,
)


ROOT = Path(__file__).resolve().parents[1]


class CheckpointEFeatureMatrixTests(unittest.TestCase):
    def test_exact_matrix_rows_have_one_ordered_keyed_witness_each(self) -> None:
        matrix_path = ROOT / "specifications" / "feature_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        entries = matrix["entries"]

        self.assertEqual(matrix["schema"], FEATURE_MATRIX_SCHEMA)
        self.assertEqual(FEATURE_MATRIX_ENTRY_COUNT, 69)
        self.assertEqual(len(entries), FEATURE_MATRIX_ENTRY_COUNT)
        self.assertEqual(
            len(FEATURE_MATRIX_WITNESS_ORDER),
            FEATURE_MATRIX_ENTRY_COUNT,
        )
        self.assertEqual(len(FEATURE_MATRIX_WITNESSES), FEATURE_MATRIX_ENTRY_COUNT)
        self.assertEqual(
            [
                (entry["construct"], entry["context"])
                for entry in entries
            ],
            [witness.key for witness in FEATURE_MATRIX_WITNESS_ORDER],
        )
        self.assertEqual(
            Counter(witness.state for witness in FEATURE_MATRIX_WITNESS_ORDER),
            Counter({"supported": 37, "unsupported": 31, "deferred": 1}),
        )
        for entry, witness in zip(
            entries,
            FEATURE_MATRIX_WITNESS_ORDER,
            strict=True,
        ):
            with self.subTest(witness=witness.witness_id):
                self.assertEqual(witness.construct, entry["construct"])
                self.assertEqual(witness.context, entry["context"])
                self.assertEqual(witness.state, entry["state"])
                self.assertEqual(
                    witness.diagnostic,
                    entry.get("diagnostic"),
                )
                self.assertTrue(witness.exercise)
                self.assertTrue(witness.required_ast_kinds)

    def test_executable_matrix_and_unlisted_default_close_the_boundary(self) -> None:
        report = audit_feature_matrix(ROOT)

        self.assertTrue(report["passed"], report["errors"])
        self.assertTrue(report["coverage_complete"])
        self.assertEqual(report["matrix_sha256"], FEATURE_MATRIX_SHA256)
        self.assertEqual(report["matrix_entry_count"], 69)
        self.assertEqual(report["matrix_witness_count"], 69)
        self.assertEqual(report["unlisted_default_witness_count"], 1)
        self.assertEqual(report["total_primary_execution_count"], 70)
        self.assertEqual(report["precedence_profile_execution_count"], 1)
        self.assertEqual(
            report["matrix_state_counts"],
            {"deferred": 1, "supported": 37, "unsupported": 31},
        )
        self.assertEqual(
            report["actual_status_counts"],
            {"Converted": 37, "Rejected": 33},
        )
        self.assertEqual(report["matrix_contract_mismatches"], [])
        self.assertEqual(report["witness_errors"], [])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])
        for digest_name in (
            "witness_manifest_sha256",
            "execution_sha256",
            "report_sha256",
        ):
            self.assertRegex(str(report[digest_name]), r"^[0-9a-f]{64}$")

        rows = {
            row["witness_id"]: row for row in report["execution_rows"]
        }
        async_profiles = rows["feature-matrix-67"]["profiles"]
        self.assertEqual(
            [
                (
                    profile["profile_id"],
                    profile["actual_diagnostics"],
                )
                for profile in async_profiles
            ],
            [
                ("matrix-owner", ["PYC2902"]),
                ("current-default-precedence", ["PYC3509"]),
            ],
        )
        match_profile = rows["feature-matrix-68"]["profiles"][0]
        self.assertEqual(match_profile["actual_diagnostics"], ["PYC2812"])
        self.assertIn(
            "Unsupported statement in the selected subset: Match",
            match_profile["actual_reasons"],
        )
        default_profile = rows[
            UNLISTED_DEFAULT_WITNESS.witness_id
        ]["profiles"][0]
        self.assertEqual(default_profile["actual_diagnostics"], ["PYC2812"])
        self.assertIn(
            "Unsupported statement in the selected subset: Try",
            default_profile["actual_reasons"],
        )

    def test_hash_order_context_state_and_diagnostic_drift_fail_closed(self) -> None:
        matrix = json.loads(
            (ROOT / "specifications" / "feature_matrix.json").read_text(
                encoding="utf-8"
            )
        )
        matrix["entries"][0], matrix["entries"][1] = (
            matrix["entries"][1],
            matrix["entries"][0],
        )
        matrix["entries"][2]["state"] = "supported"
        matrix["entries"][2].pop("diagnostic")
        matrix["entries"][68]["context"] = "changed-context"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specifications = root / "specifications"
            specifications.mkdir()
            (specifications / "feature_matrix.json").write_text(
                json.dumps(matrix, indent=2) + "\n",
                encoding="utf-8",
            )
            report = audit_feature_matrix(root)

        self.assertFalse(report["passed"])
        self.assertNotEqual(report["matrix_sha256"], FEATURE_MATRIX_SHA256)
        mismatch_kinds = {
            item["kind"] for item in report["matrix_contract_mismatches"]
        }
        self.assertIn("order-or-key-drift", mismatch_kinds)
        self.assertIn("entry-contract-drift", mismatch_kinds)
        self.assertIn("missing-entry", mismatch_kinds)
        self.assertIn("unexpected-entry", mismatch_kinds)
        self.assertTrue(
            any("SHA-256 drift" in error for error in report["errors"])
        )


if __name__ == "__main__":
    unittest.main()
