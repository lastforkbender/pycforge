from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import tools.validate_phase14 as validator
from tools.validate_phase14 import (
    EXPECTED_CONTRACTS,
    PREDECESSOR_CONVERTER_SHA256,
    PREDECESSOR_TREE_SHA256,
    TOOLCHAIN_INVOKED,
    accepted_numeric_errors,
    archive_file_map,
    canonical_archive_subtree_hash,
    canonical_archive_tree_hash,
    canonical_release_tree_hash,
    current_contracts,
    exact_mapping_errors,
    historical_phase13_errors,
    locate_predecessor_archive,
    reference_model_errors,
    rejection_smoke_errors,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase14ValidatorTests(unittest.TestCase):
    def test_active_contracts_match_the_literal_phase14a_contract(self) -> None:
        self.assertEqual(current_contracts(), EXPECTED_CONTRACTS)

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

    def test_numeric_acceptance_is_closed_and_fresh_process_deterministic(self) -> None:
        self.assertEqual(accepted_numeric_errors(ROOT), [])

    def test_numeric_rejections_publish_no_generated_c_or_helper_manifest(self) -> None:
        self.assertEqual(rejection_smoke_errors(), [])

    def test_reference_model_matches_python_at_all_bounded_sign_edges(self) -> None:
        self.assertEqual(reference_model_errors(), [])

    def test_exact_historical_phase13_witness_is_preserved(self) -> None:
        self.assertEqual(historical_phase13_errors(), [])

    def test_predecessor_archive_authenticates_tree_and_converter_subtree(self) -> None:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("sealed Phase 13 archive is not beside this source tree")
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

    def test_release_tree_hash_excludes_only_phase14_self_reference_and_ephemera(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("stable", encoding="utf-8")
            before = canonical_release_tree_hash(root)

            historical = root / "transition/phase_13/release_fingerprint.json"
            historical.parent.mkdir(parents=True)
            historical.write_text("historical identity", encoding="utf-8")
            with_historical = canonical_release_tree_hash(root)
            self.assertNotEqual(with_historical, before)

            fingerprint = root / "transition/phase_14/release_fingerprint.json"
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
                validator._fingerprint_errors(
                    root, draft, require_promoted=False
                ),
                [],
            )
            self.assertTrue(
                validator._fingerprint_errors(root, draft, require_promoted=True)
            )

    def test_validator_declares_and_uses_no_c_toolchain_path(self) -> None:
        self.assertIs(TOOLCHAIN_INVOKED, False)


if __name__ == "__main__":
    unittest.main()
