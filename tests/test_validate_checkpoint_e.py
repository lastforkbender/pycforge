from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.validate_checkpoint_e import (
    CHECKPOINT_E_VERSION,
    FEATURE_MATRIX_ENTRY_COUNT,
    FEATURE_MATRIX_SCHEMA,
    FEATURE_MATRIX_SHA256,
    GENERATED_C_COMPILED_OR_EXECUTED,
    SEALED_PREDECESSOR_NAME,
    SEALED_PREDECESSOR_SHA256,
    SEALED_PREDECESSOR_SIZE,
    TOOLCHAIN_INVOKED,
    WORKSPACE_CONTRACT,
    audit_checkpoint_metadata,
    audit_release_fingerprint,
    authenticate_predecessor_archive,
    locate_predecessor_archive,
    main,
    validate_checkpoint_e,
)


ROOT = Path(__file__).resolve().parents[1]


class CheckpointEValidatorTests(unittest.TestCase):
    def _available_predecessor_or_skip(self) -> Path:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest(
                "sealed Phase 14D predecessor archive is not beside this tree"
            )
        return archive

    def test_sealed_phase14d_identity_is_exact(self) -> None:
        self.assertEqual(CHECKPOINT_E_VERSION, "0.14.4")
        self.assertEqual(WORKSPACE_CONTRACT, "pycforge-workspace/0.2")
        self.assertEqual(
            FEATURE_MATRIX_SCHEMA,
            "pycforge.feature-matrix/0.14.3",
        )
        self.assertEqual(FEATURE_MATRIX_ENTRY_COUNT, 69)
        self.assertEqual(
            FEATURE_MATRIX_SHA256,
            "ca78dff3ea203130781f5e0fde879c0ca9d7b7a0e550a05ab5d46ea3432cc01a",
        )
        self.assertEqual(
            SEALED_PREDECESSOR_NAME,
            "pycforge_phase_14d_v0_14_3.tar.gz",
        )
        self.assertEqual(SEALED_PREDECESSOR_SIZE, 1_282_543)
        self.assertEqual(
            SEALED_PREDECESSOR_SHA256,
            "13228fe8e40c89335cf1bb6c44a2ebb94bc581e287873520b7c530984053c4f1",
        )
        self.assertFalse(TOOLCHAIN_INVOKED)
        self.assertFalse(GENERATED_C_COMPILED_OR_EXECUTED)

    def test_historical_metadata_audit_rejects_the_phase15c_successor(
        self,
    ) -> None:
        report = audit_checkpoint_metadata(ROOT)

        self.assertFalse(report["passed"])
        self.assertEqual(report["package_version"], "0.15.2")
        self.assertEqual(report["project_version"], "0.15.2")
        self.assertEqual(
            report["converter_contract_version"],
            "0.14.3",
        )
        self.assertEqual(
            report["workspace_contract"],
            "pycforge-workspace/0.5",
        )
        self.assertEqual(report["feature_matrix_entry_count"], 69)
        self.assertIn(
            "imported package version is '0.15.2', expected '0.14.4'",
            report["errors"],
        )
        self.assertIn(
            "workspace contract identity changed: 'pycforge-workspace/0.5'",
            report["errors"],
        )
        self.assertIn(
            "project version is '0.15.2', expected '0.14.4'",
            report["errors"],
        )

    def test_authenticates_available_sealed_predecessor_without_extraction(self) -> None:
        archive = self._available_predecessor_or_skip()

        report = authenticate_predecessor_archive(archive)

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["actual_size"], SEALED_PREDECESSOR_SIZE)
        self.assertEqual(report["actual_sha256"], SEALED_PREDECESSOR_SHA256)
        self.assertEqual(
            report["archive_roots"],
            ["pycforge_phase_14d_v0_14_3"],
        )
        self.assertGreater(report["regular_file_count"], 0)
        self.assertFalse(report["archive_extracted"])

    def test_rejects_tampered_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / SEALED_PREDECESSOR_NAME
            archive.write_bytes(b"not the sealed predecessor")

            report = authenticate_predecessor_archive(archive)

        self.assertFalse(report["passed"])
        joined = "\n".join(report["errors"])
        self.assertIn("size mismatch", joined)
        self.assertIn("SHA-256 mismatch", joined)
        self.assertIn("not a readable gzip tar", joined)
        self.assertFalse(report["archive_extracted"])

    def test_historical_validator_fails_closed_on_phase15c_but_preserves_audits(
        self,
    ) -> None:
        archive = self._available_predecessor_or_skip()

        report = validate_checkpoint_e(
            ROOT,
            predecessor_archive=archive,
            require_predecessor=True,
            run_fuzz=False,
            run_predecessor_equivalence=False,
        )

        self.assertFalse(report["passed"])
        self.assertEqual(
            report["errors"],
            ["Checkpoint E metadata, roadmap, or feature matrix audit failed"],
        )
        self.assertEqual(report["identity_mismatches"], {})
        self.assertTrue(
            report["architecture_branding_product_boundary"]["passed"]
        )
        self.assertTrue(report["sealed_predecessor"]["passed"])
        metadata = report["metadata_roadmap_feature_matrix"]
        self.assertFalse(metadata["passed"])
        self.assertEqual(metadata["package_version"], "0.15.2")
        self.assertEqual(metadata["workspace_contract"], "pycforge-workspace/0.5")
        self.assertTrue(report["full_supported_subset"]["skipped"])
        self.assertTrue(report["sealed_predecessor_equivalence"]["skipped"])
        self.assertTrue(report["executable_feature_matrix"]["coverage_complete"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["sealed_release_eligible"])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_promotion_mode_rejects_every_focused_skip(self) -> None:
        archive = self._available_predecessor_or_skip()

        report = validate_checkpoint_e(
            ROOT,
            predecessor_archive=archive,
            run_fuzz=False,
            fuzz_case_count=0,
            run_predecessor_equivalence=False,
            mode="promotion",
        )

        self.assertFalse(report["passed"])
        self.assertFalse(report["promotion_eligible"])
        self.assertIn(
            "full-supported-subset audit was skipped",
            report["promotion_blockers"],
        )
        self.assertTrue(
            any(
                "exactly 64 generated cases" in blocker
                for blocker in report["promotion_blockers"]
            )
        )
        self.assertIn(
            "sealed predecessor equivalence was skipped",
            report["promotion_blockers"],
        )

    def test_required_release_fingerprint_fails_closed_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = audit_release_fingerprint(
                Path(temporary),
                required=True,
            )

        self.assertFalse(report["passed"])
        self.assertFalse(report["present"])
        self.assertIn("required release fingerprint", report["errors"][0])

    def test_unknown_validation_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_checkpoint_e(ROOT, mode="unknown")

    def test_historical_cli_reports_phase15a_as_non_checkpoint_tree(self) -> None:
        self._available_predecessor_or_skip()
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "--require-predecessor",
                    "--skip-fuzz",
                    "--skip-predecessor-equivalence",
                ]
            )
        report = json.loads(output.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["mode"], "focused")
        self.assertFalse(report["metadata_roadmap_feature_matrix"]["passed"])
        self.assertTrue(report["sealed_predecessor"]["passed"])
        self.assertFalse(report["promotion_eligible"])
        self.assertFalse(report["c_toolchain_invoked"])
        self.assertFalse(report["generated_c_compiled_or_executed"])

    def test_historical_cli_writes_the_same_fail_closed_report(self) -> None:
        self._available_predecessor_or_skip()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint-e.json"
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--require-predecessor",
                        "--skip-fuzz",
                        "--skip-predecessor-equivalence",
                        "--output",
                        str(path),
                    ]
                )
            printed = json.loads(output.getvalue())
            written = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertFalse(printed["passed"])
        self.assertEqual(written, printed)


if __name__ == "__main__":
    unittest.main()
