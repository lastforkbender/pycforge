from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.validate_phase13 import (
    EXPECTED_CONTRACTS,
    PREDECESSOR_CONVERTER_SHA256,
    PREDECESSOR_TREE_SHA256,
    archive_file_map,
    canonical_archive_subtree_hash,
    canonical_archive_tree_hash,
    canonical_release_tree_hash,
    converter_smoke_errors,
    current_contracts,
    exact_mapping_errors,
    locate_predecessor_archive,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase13ValidatorTests(unittest.TestCase):
    def test_historical_contracts_match_the_literal_phase13_release_contract(self) -> None:
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

    def test_predecessor_archive_authenticates_tree_and_converter_subtree(self) -> None:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("sealed predecessor archive is not beside this source tree")
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

    def test_release_tree_hash_excludes_only_declared_ephemera(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.txt").write_text("stable", encoding="utf-8")
            before = canonical_release_tree_hash(root)
            fingerprint = root / "transition/phase_13/release_fingerprint.json"
            fingerprint.parent.mkdir(parents=True)
            fingerprint.write_text("self reference", encoding="utf-8")
            cache = root / "pkg/__pycache__/module.pyc"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"cache")
            dist = root / "dist/release.whl"
            dist.parent.mkdir()
            dist.write_bytes(b"artifact")
            self.assertEqual(canonical_release_tree_hash(root), before)
            (root / "source.txt").write_text("changed", encoding="utf-8")
            self.assertNotEqual(canonical_release_tree_hash(root), before)

    def test_record_converter_smoke_closes_runtime_and_compatibility_checks(self) -> None:
        self.assertEqual(converter_smoke_errors(), [])


if __name__ == "__main__":
    unittest.main()
