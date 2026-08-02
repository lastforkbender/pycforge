from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath

import tools.validate_phase14b as validator
from tools.validate_phase14b import (
    EXPECTED_CONTRACTS,
    PREDECESSOR_CONVERTER_SHA256,
    PREDECESSOR_TREE_SHA256,
    RELEASE_FINGERPRINT,
    TOOLCHAIN_INVOKED,
    accepted_conditional_errors,
    archive_file_map,
    canonical_archive_subtree_hash,
    canonical_archive_tree_hash,
    canonical_release_tree_hash,
    current_contracts,
    dangerous_rejection_errors,
    exact_mapping_errors,
    historical_phase14a_errors,
    locate_predecessor_archive,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase14BValidatorTests(unittest.TestCase):
    def test_sealed_contracts_match_the_literal_phase14b_contract(self) -> None:
        self.assertEqual(current_contracts(), EXPECTED_CONTRACTS)

    def test_validator_never_derives_sealed_identities_from_active_defaults(self) -> None:
        source = (ROOT / "tools/validate_phase14b.py").read_text(encoding="utf-8")
        for forbidden_import in (
            "    DEFAULT_RULE_SET,",
            "    DEFAULT_RENDERER,",
            "    CONDITIONAL_FACT_SCHEMA,",
            "    CONVERSION_PLAN_SCHEMA,",
            "    C_IR_SCHEMA,",
            "    GENERATED_C_SCHEMA,",
            "    CONVERSION_SUMMARY_SCHEMA,",
            "    DECISION_TRACE_SCHEMA,",
        ):
            self.assertNotIn(forbidden_import, source)
        for required in (
            "PHASE14B_RULE_SET",
            "PHASE14B_RENDERER",
            "PHASE14B_CONDITIONAL_FACT_SCHEMA",
            "PHASE14B_CONVERSION_PLAN_SCHEMA",
            "PHASE14B_C_IR_SCHEMA",
            "PHASE14B_GENERATED_C_SCHEMA",
            "PHASE14B_CONVERSION_SUMMARY_SCHEMA",
            "PHASE14B_DECISION_TRACE_SCHEMA",
        ):
            self.assertIn(required, source)

    def test_exact_mapping_check_reports_missing_extra_and_changed_keys(self) -> None:
        errors = exact_mapping_errors(
            {"kept": 2, "extra": 3},
            {"kept": 1, "missing": 4},
            "contract",
        )
        self.assertEqual(
            errors,
            [
                "contract: unexpected key 'extra'",
                "contract: 'kept' is 2, expected 1",
                "contract: missing key 'missing'",
            ],
        )

    def test_conditional_acceptance_is_closed_and_fresh_process_deterministic(self) -> None:
        self.assertEqual(accepted_conditional_errors(ROOT), [])

    def test_explicit_historical_phase14a_behavior_is_exact(self) -> None:
        self.assertEqual(historical_phase14a_errors(), [])

    def test_runtime_heavy_neighboring_families_remain_atomically_rejected(self) -> None:
        self.assertEqual(dangerous_rejection_errors(), [])

    def test_successor_tree_preserves_the_sealed_opening_packet_and_transition(self) -> None:
        missing = [
            name
            for name in sorted(validator._opening_required_files())
            if not (ROOT / name).is_file()
        ]
        self.assertEqual(missing, [])
        report = validator.audit_transition(ROOT, "phase_14b")
        self.assertIs(report.get("passed"), True)

    def test_predecessor_archive_authenticates_tree_and_converter_subtree(self) -> None:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("sealed Phase 14A archive is not beside this source tree")
        self.assertEqual(canonical_archive_tree_hash(archive), PREDECESSOR_TREE_SHA256)
        self.assertEqual(
            canonical_archive_subtree_hash(archive, "pycforge/converter"),
            PREDECESSOR_CONVERTER_SHA256,
        )

    def test_archive_reader_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "unsafe.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                info = tarfile.TarInfo("release/../escape.txt")
                data = b"unsafe"
                info.size = len(data)
                package.addfile(info, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "unsafe archive member"):
                archive_file_map(archive)

    def test_release_tree_hash_excludes_only_phase14b_self_reference_and_ephemera(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("stable", encoding="utf-8")
            before = canonical_release_tree_hash(root)

            historical = root / "transition/phase_14/release_fingerprint.json"
            historical.parent.mkdir(parents=True)
            historical.write_text("historical identity", encoding="utf-8")
            with_historical = canonical_release_tree_hash(root)
            self.assertNotEqual(with_historical, before)

            fingerprint = root / RELEASE_FINGERPRINT
            fingerprint.parent.mkdir(parents=True, exist_ok=True)
            fingerprint.write_text("self reference", encoding="utf-8")
            cache = root / "pkg/__pycache__/module.pyc"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"cache")
            dist = root / "dist/release.whl"
            dist.parent.mkdir()
            dist.write_bytes(b"artifact")
            self.assertEqual(canonical_release_tree_hash(root), with_historical)

            historical.write_text("changed history", encoding="utf-8")
            self.assertNotEqual(canonical_release_tree_hash(root), with_historical)

    def test_source_archive_hash_can_exclude_14b_self_reference_not_phase14_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "candidate.tar.gz"
            members = {
                "release/source.txt": b"stable",
                "release/transition/phase_14/release_fingerprint.json": b"history",
                "release/transition/phase_14b/release_fingerprint.json": b"self",
            }
            with tarfile.open(archive, "w:gz") as package:
                for name, data in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    package.addfile(info, io.BytesIO(data))
            files = archive_file_map(
                archive,
                fingerprint_to_omit=PurePosixPath(
                    "transition/phase_14b/release_fingerprint.json"
                ),
            )
            self.assertIn("transition/phase_14/release_fingerprint.json", files)
            self.assertNotIn("transition/phase_14b/release_fingerprint.json", files)

    def test_preseal_mode_allows_an_unassigned_tree_value_only_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("candidate", encoding="utf-8")
            draft = {
                "algorithm": "sha256",
                "domain": validator.FINGERPRINT_DOMAIN,
                "status": "draft",
                "value": "PENDING",
            }
            self.assertEqual(
                validator._fingerprint_errors(root, draft, require_promoted=False),
                [],
            )
            self.assertTrue(
                validator._fingerprint_errors(root, draft, require_promoted=True)
            )

    def test_validator_declares_and_uses_no_c_toolchain_path(self) -> None:
        self.assertIs(TOOLCHAIN_INVOKED, False)


if __name__ == "__main__":
    unittest.main()
