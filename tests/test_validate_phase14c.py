from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath

import tools.validate_phase14c as validator
from tools.validate_phase14c import (
    EXPECTED_CONTRACTS,
    EXPECTED_PHASE14B_CONTRACTS,
    PREDECESSOR_CONVERTER_SHA256,
    PREDECESSOR_FINGERPRINT,
    PREDECESSOR_TREE_SHA256,
    RELEASE_FINGERPRINT,
    TOOLCHAIN_INVOKED,
    accepted_keyword_errors,
    archive_file_map,
    bounded_profile_errors,
    cancellation_errors,
    canonical_archive_subtree_hash,
    canonical_archive_tree_hash,
    canonical_release_tree_hash,
    current_contracts,
    exact_mapping_errors,
    historical_phase14b_errors,
    historical_phase14b_contracts,
    independent_tamper_errors,
    locate_predecessor_archive,
    locate_predecessor_wheel,
    predecessor_errors,
    predecessor_wheel_errors,
    rejection_matrix_errors,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase14CValidatorTests(unittest.TestCase):
    def test_frozen_contract_check_refuses_the_successor_active_contracts(self) -> None:
        current = current_contracts()
        self.assertEqual(current["conversion_plan"], "conversion-plan/0.14.3")
        self.assertEqual(current["c_ir"], "c-ir/0.14.3")
        self.assertEqual(current["generated_c"], "generated-c/0.14.3")
        self.assertEqual(
            current["rule_set"],
            "phase14-required-keyword-only-calls-v0.14.3",
        )
        errors = exact_mapping_errors(
            current,
            EXPECTED_CONTRACTS,
            "active tree versus frozen Phase 14C contracts",
        )
        self.assertEqual(len(errors), 7)
        self.assertTrue(all("0.14.3" in item for item in errors))

    def test_validator_names_exact_active_and_historical_identities(self) -> None:
        source = (ROOT / "tools/validate_phase14c.py").read_text(encoding="utf-8")
        for identity in (
            '"phase14-direct-keyword-calls-v0.14.2"',
            '"c-renderer-v0.14.2"',
            '"fact-table/0.14.2"',
            '"conversion-plan/0.14.2"',
            '"c-ir/0.14.2"',
            '"generated-c/0.14.2"',
            '"phase14-conditional-regions-v0.14.1"',
            '"c-renderer-v0.14.1"',
        ):
            self.assertIn(identity, source)
        self.assertIn("fingerprint_to_omit=PREDECESSOR_FINGERPRINT", source)

    def test_historical_contracts_match_literal_phase14b_identities(self) -> None:
        self.assertEqual(
            historical_phase14b_contracts(), EXPECTED_PHASE14B_CONTRACTS
        )

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

    def test_frozen_keyword_witness_refuses_the_successor_envelope(self) -> None:
        self.assertEqual(
            accepted_keyword_errors(ROOT, fresh_process=False),
            [
                "Phase 14C keyword request fingerprint changed",
                "Phase 14C keyword artifact fingerprint changed",
                "accepted witness does not publish exact active Phase 14C identities",
            ],
        )

    def test_frozen_rejection_matrix_detects_successor_keyword_only_support(self) -> None:
        self.assertEqual(
            rejection_matrix_errors(),
            [
                "keyword-only-target did not reject atomically with exactly "
                "PYC2911"
            ],
        )

    def test_mixed_and_cross_module_profiles_remain_bounded_and_exact(self) -> None:
        self.assertEqual(bounded_profile_errors(), [])

    def test_independent_reconstruction_rejects_tampering(self) -> None:
        self.assertEqual(independent_tamper_errors(), [])

    def test_cancellation_retires_output_and_interrupts_validation(self) -> None:
        self.assertEqual(cancellation_errors(), [])

    def test_historical_phase14b_envelope_stays_exact_but_active_alias_is_successor(self) -> None:
        self.assertEqual(
            historical_phase14b_errors(),
            ["active no-keyword output changed explicit Phase 14B compatibility"],
        )

    def test_opening_packet_authenticates_the_sealed_predecessor(self) -> None:
        missing = [
            name
            for name in sorted(validator._opening_required_files())
            if not (ROOT / name).is_file()
        ]
        self.assertEqual(missing, [])
        baseline = json.loads(
            (ROOT / "transition/phase_14c/baseline_fingerprint.json").read_text(
                encoding="utf-8"
            )
        )
        predecessor = baseline["predecessor"]
        self.assertEqual(predecessor["canonical_release_tree_sha256"], PREDECESSOR_TREE_SHA256)
        self.assertEqual(
            predecessor["converter_subtree_sha256"], PREDECESSOR_CONVERTER_SHA256
        )
        self.assertEqual(
            predecessor["release_fingerprint_file"], PREDECESSOR_FINGERPRINT.as_posix()
        )

    def test_promoted_required_files_name_the_actual_keyword_audit_test(self) -> None:
        required = validator._promoted_required_files({})
        self.assertIn("tests/test_phase14c_keyword_audits.py", required)
        self.assertNotIn("tests/test_phase14c_audits.py", required)

    def test_predecessor_archive_authenticates_with_explicit_14b_omission(self) -> None:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("sealed Phase 14B archive is not beside this source tree")
        self.assertEqual(predecessor_errors(archive), [])
        self.assertEqual(
            canonical_archive_tree_hash(
                archive, fingerprint_to_omit=PREDECESSOR_FINGERPRINT
            ),
            PREDECESSOR_TREE_SHA256,
        )
        self.assertEqual(
            canonical_archive_subtree_hash(archive, "pycforge/converter"),
            PREDECESSOR_CONVERTER_SHA256,
        )

    def test_predecessor_wheel_authenticates_exactly(self) -> None:
        wheel = locate_predecessor_wheel(ROOT)
        if wheel is None:
            self.skipTest("sealed Phase 14B wheel is not beside this source tree")
        self.assertEqual(predecessor_wheel_errors(wheel), [])

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

    def test_release_tree_hash_excludes_only_phase14c_self_reference_and_ephemera(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("stable", encoding="utf-8")
            before = canonical_release_tree_hash(root)

            historical = root / PREDECESSOR_FINGERPRINT
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

    def test_source_archive_hash_can_exclude_14c_not_14b_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "candidate.tar.gz"
            members = {
                "release/source.txt": b"stable",
                "release/transition/phase_14b/release_fingerprint.json": b"history",
                "release/transition/phase_14c/release_fingerprint.json": b"self",
            }
            with tarfile.open(archive, "w:gz") as package:
                for name, data in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    package.addfile(info, io.BytesIO(data))
            files = archive_file_map(
                archive,
                fingerprint_to_omit=PurePosixPath(
                    "transition/phase_14c/release_fingerprint.json"
                ),
            )
            self.assertIn("transition/phase_14b/release_fingerprint.json", files)
            self.assertNotIn("transition/phase_14c/release_fingerprint.json", files)

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
