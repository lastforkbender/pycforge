from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tarfile
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from tools._phase15c_release_contract import (
    assert_clean_scan,
    scan_named_bytes,
    scan_release_tree,
    scan_source_archive_bytes,
    scan_wheel,
)


_RETIRED = bytes.fromhex("7370616365706f7274")


class Phase15CReleaseContractTests(unittest.TestCase):
    def test_named_byte_scan_is_case_insensitive_and_sanitized(self) -> None:
        clean = scan_named_bytes((("docs/current.txt", b"PyCForge"),))
        self.assertTrue(clean.passed)
        self.assertEqual(clean.regular_files_scanned, 1)

        path_hit = scan_named_bytes(
            ((f"tests/{_RETIRED.decode('ascii')}.txt", b"clean"),)
        )
        self.assertFalse(path_hit.passed)
        self.assertEqual(len(path_hit.path_matches), 1)
        self.assertNotIn(
            _RETIRED.decode("ascii"),
            repr(path_hit.to_report()).casefold(),
        )

        content_hit = scan_named_bytes(
            (("tests/clean.txt", _RETIRED.upper()),)
        )
        self.assertFalse(content_hit.passed)
        self.assertEqual(len(content_hit.content_matches), 1)

    def test_release_tree_scans_paths_contents_and_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pycforge").mkdir()
            (root / "pycforge" / "clean.py").write_bytes(b"PyCForge")
            self.assertTrue(scan_release_tree(root).passed)
            (root / "pycforge" / "cache.bin").write_bytes(
                b"\x00" + _RETIRED + b"\xff"
            )
            report = scan_release_tree(root)
        self.assertFalse(report.passed)
        self.assertEqual(report.content_matches, ("pycforge/cache.bin",))

    def test_release_tree_ignores_ephemeral_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "tests" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "compiled.pyc").write_bytes(_RETIRED)
            (root / "candidate.whl").write_bytes(_RETIRED)
            (root / "current.py").write_bytes(b"PyCForge")

            report = scan_release_tree(root)

        self.assertTrue(report.passed)
        self.assertEqual(report.regular_files_scanned, 1)

    def test_source_archive_and_wheel_scans_cover_names_and_bytes(self) -> None:
        tar_buffer = BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as archive:
            payload = b"PyCForge"
            info = tarfile.TarInfo("release/current.txt")
            info.size = len(payload)
            archive.addfile(info, BytesIO(payload))
        self.assertTrue(scan_source_archive_bytes(tar_buffer.getvalue()).passed)

        with tempfile.TemporaryDirectory() as temporary:
            wheel = Path(temporary) / "clean.whl"
            with ZipFile(wheel, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("pycforge/current.py", b"PyCForge")
            self.assertTrue(scan_wheel(wheel).passed)
            with ZipFile(wheel, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("pycforge/current.py", _RETIRED)
            self.assertFalse(scan_wheel(wheel).passed)

    def test_clean_assertion_uses_sanitized_feedback(self) -> None:
        scan = scan_named_bytes((("current.txt", _RETIRED),))
        with self.assertRaisesRegex(
            ValueError, r"retired-theme vocabulary"
        ) as captured:
            assert_clean_scan(scan, label="candidate")
        self.assertNotIn(_RETIRED.decode("ascii"), str(captured.exception))


if __name__ == "__main__":
    unittest.main()
