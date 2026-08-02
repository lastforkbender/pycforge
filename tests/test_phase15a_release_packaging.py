from __future__ import annotations

from pathlib import Path
import unittest

from tools.build_phase15a_release import (
    CONVERTER_CUSTODY_DOMAIN,
    CONVERTER_SUBTREE_SHA256,
    FINGERPRINT_DOMAIN,
    RELEASE_FINGERPRINT,
    SOURCE_ARCHIVE_ROOT,
    ReleaseBuildError,
    hash_file_map,
    inspect_source_archive,
    normalized_source_archive_bytes,
    release_file_map,
    release_subtree_hash,
    release_tree_hash,
    safe_relative_path,
)


ROOT = Path(__file__).resolve().parents[1]


class Phase15AReleasePackagingTests(unittest.TestCase):
    def test_safe_relative_paths_fail_closed(self) -> None:
        for value in ("", "/absolute", "../escape", "a/../b", r"a\b"):
            with self.subTest(value=value):
                with self.assertRaises(ReleaseBuildError):
                    safe_relative_path(value)

    def test_source_archive_is_normalized_and_order_independent(self) -> None:
        files = {
            "README.md": b"phase 15a\n",
            "pycforge/_version.py": b'__version__ = "0.15.0"\n',
        }
        first = normalized_source_archive_bytes(files)
        second = normalized_source_archive_bytes(
            dict(reversed(tuple(files.items())))
        )
        self.assertEqual(first, second)
        report = inspect_source_archive(first, files)
        self.assertEqual(report["archive_root"], SOURCE_ARCHIVE_ROOT)
        self.assertTrue(report["regular_files_only"])
        self.assertTrue(report["canonical_gzip"])

    def test_release_tree_hash_is_self_excluding(self) -> None:
        files = release_file_map(ROOT)
        expected = dict(files)
        expected.pop(RELEASE_FINGERPRINT.as_posix(), None)
        digest, count = release_tree_hash(ROOT)
        self.assertEqual(count, len(expected))
        self.assertEqual(
            digest,
            hash_file_map(expected, domain=FINGERPRINT_DOMAIN),
        )

    def test_converter_subtree_matches_checkpoint_e_custody(self) -> None:
        digest, count = release_subtree_hash(
            ROOT,
            "pycforge/converter",
            domain=CONVERTER_CUSTODY_DOMAIN,
        )
        self.assertEqual(digest, CONVERTER_SUBTREE_SHA256)
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
