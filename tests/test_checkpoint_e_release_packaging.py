from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zipfile

import tools.build_checkpoint_e_release as release


def synthetic_wheel(
    destination: Path,
    *,
    corrupt_record: bool = False,
    include_native: bool = False,
) -> dict[str, bytes]:
    members: dict[str, bytes] = {
        name: f"# {name}\n".encode("utf-8")
        for name in release.REQUIRED_WHEEL_MEMBERS
    }
    for asset_name in release.EXPECTED_SVG_ASSET_NAMES:
        members[asset_name] = b"<svg xmlns=\"http://www.w3.org/2000/svg\"/>\n"
    metadata_name = "pycforge-0.14.4.dist-info/METADATA"
    wheel_metadata_name = "pycforge-0.14.4.dist-info/WHEEL"
    entry_points_name = "pycforge-0.14.4.dist-info/entry_points.txt"
    record_name = "pycforge-0.14.4.dist-info/RECORD"
    members[metadata_name] = (
        b"Metadata-Version: 2.1\n"
        b"Name: pycforge\n"
        b"Version: 0.14.4\n"
        b"Requires-Python: >=3.11\n\n"
    )
    members[wheel_metadata_name] = (
        b"Wheel-Version: 1.0\n"
        b"Generator: checkpoint-e-test\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n\n"
    )
    members[entry_points_name] = (
        b"[console_scripts]\n"
        b"pycforge = pycforge.laboratory.cli:main\n"
        b"pycforge-workspace = pycforge.ide.qt:run\n"
    )
    if include_native:
        members["pycforge/native.so"] = b"not-native-test-data"

    rows = []
    for name, data in sorted(members.items()):
        digest = release._record_digest(data)
        if corrupt_record and name == "pycforge/__init__.py":
            digest = "sha256=" + ("A" * 43)
        rows.append((name, digest, str(len(data))))
    rows.append((record_name, "", ""))
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    members[record_name] = output.getvalue().encode("utf-8")

    with zipfile.ZipFile(destination, "w") as package:
        for name, data in sorted(members.items()):
            package.writestr(name, data)
    return {
        name: members[name] for name in release.EXPECTED_SVG_ASSET_NAMES
    }


def custom_tar(
    members: list[tuple[str, bytes, bytes]],
    *,
    mtime: int = release.SOURCE_DATE_EPOCH,
) -> bytes:
    """Build a canonical-gzip USTAR with explicit tar member types."""

    raw = io.BytesIO()
    with tarfile.open(
        fileobj=raw,
        mode="w",
        format=tarfile.USTAR_FORMAT,
    ) as package:
        for name, data, member_type in members:
            info = tarfile.TarInfo(name)
            info.size = len(data) if member_type == tarfile.REGTYPE else 0
            info.type = member_type
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = mtime
            package.addfile(
                info,
                io.BytesIO(data) if member_type == tarfile.REGTYPE else None,
            )
    return release.canonical_gzip_bytes(raw.getvalue())


class CheckpointEReleasePackagingTests(unittest.TestCase):
    def test_release_identities_are_exact_and_source_only(self) -> None:
        self.assertEqual(release.RELEASE_VERSION, "0.14.4")
        self.assertEqual(release.CONVERTER_CONTRACT_VERSION, "0.14.3")
        self.assertEqual(release.SOURCE_DATE_EPOCH, 1_700_000_000)
        self.assertEqual(
            release.SOURCE_ARCHIVE_NAME,
            "pycforge_checkpoint_e_v0_14_4.tar.gz",
        )
        self.assertEqual(
            release.SOURCE_ARCHIVE_ROOT,
            "pycforge_checkpoint_e_v0_14_4",
        )
        self.assertEqual(
            release.WHEEL_NAME,
            "pycforge-0.14.4-py3-none-any.whl",
        )
        self.assertEqual(
            release.HANDOFF_NAME,
            "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt",
        )
        self.assertFalse(release.TOOLCHAIN_INVOKED)
        self.assertFalse(release.GENERATED_C_COMPILED_OR_EXECUTED)

    def test_release_ephemera_filter_is_exact_and_keeps_egg_info_custody(self) -> None:
        forbidden = (
            ".ruff_cache/item",
            ".pytest_cache/item",
            "__pycache__/item.py",
            "build/lib/item.py",
            "dist/item.py",
            "pycforge/module.pyc",
            "pycforge/module.pyo",
            "pycforge-0.14.4.dist-info/METADATA",
            release.SOURCE_ARCHIVE_NAME,
            release.WHEEL_NAME,
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertTrue(release.is_release_ephemera(name))
        retained = (
            "pycforge/__init__.py",
            "pycforge.egg-info/PKG-INFO",
            "transition/checkpoint_e/release_fingerprint.json",
        )
        for name in retained:
            with self.subTest(name=name):
                self.assertFalse(release.is_release_ephemera(name))

    def test_safe_relative_path_rejects_traversal_and_ambiguous_names(self) -> None:
        for name in (
            "",
            "/absolute",
            "../escape",
            "path/../escape",
            "./relative",
            "windows\\escape",
            "nul\x00byte",
        ):
            with self.subTest(name=name):
                with self.assertRaises(release.ReleaseBuildError):
                    release.safe_relative_path(name)
        self.assertEqual(
            release.safe_relative_path(
                "pycforge/converter/facade.py"
            ).as_posix(),
            Path("pycforge/converter/facade.py").as_posix(),
        )

    def test_release_file_map_excludes_caches_but_retains_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "pycforge").mkdir()
            (root / "pycforge/__init__.py").write_text(
                "# retained\n",
                encoding="utf-8",
            )
            (root / "pycforge/__pycache__").mkdir()
            (root / "pycforge/__pycache__/module.pyc").write_bytes(b"cache")
            (root / ".ruff_cache").mkdir()
            (root / ".ruff_cache/item").write_bytes(b"cache")
            (root / "build").mkdir()
            (root / "build/item").write_bytes(b"build")
            (root / "pycforge.egg-info").mkdir()
            (root / "pycforge.egg-info/PKG-INFO").write_text(
                "Version: 0.14.4\n",
                encoding="utf-8",
            )
            self.assertEqual(
                release.release_file_map(root),
                {
                    "pycforge/__init__.py": b"# retained\n",
                    "pycforge.egg-info/PKG-INFO": b"Version: 0.14.4\n",
                },
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_release_file_map_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "real.py").write_text("# real\n", encoding="utf-8")
            os.symlink(root / "real.py", root / "linked.py")
            with self.assertRaisesRegex(
                release.ReleaseBuildError,
                "symbolic link",
            ):
                release.release_file_map(root)

    def test_tree_hash_is_domain_separated_and_self_excluding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "transition/checkpoint_e").mkdir(parents=True)
            fingerprint = root / release.RELEASE_FINGERPRINT
            fingerprint.write_text('{"value":"opening"}\n', encoding="utf-8")
            (root / "payload.txt").write_text("one\n", encoding="utf-8")
            first, first_count = release.release_tree_hash(root)
            fingerprint.write_text('{"value":"changed"}\n', encoding="utf-8")
            second, second_count = release.release_tree_hash(root)
            self.assertEqual((first, first_count), (second, second_count))
            self.assertEqual(first_count, 1)

            (root / "payload.txt").write_text("two\n", encoding="utf-8")
            third, third_count = release.release_tree_hash(root)
            self.assertNotEqual(first, third)
            self.assertEqual(third_count, 1)
            plain = release.hash_file_map({"payload.txt": b"one\n"})
            self.assertNotEqual(first, plain)

    def test_subtree_hash_uses_paths_relative_to_the_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            (root / "one").mkdir()
            (root / "one/a.txt").write_bytes(b"a")
            (root / "one/b.txt").write_bytes(b"b")
            digest, count = release.release_subtree_hash(root, "one")
            self.assertEqual(count, 2)
            expected = release.hash_file_map(
                {"a.txt": b"a", "b.txt": b"b"},
                domain=release.FINGERPRINT_DOMAIN + ":subtree:one",
            )
            self.assertEqual(digest, expected)
            with self.assertRaises(release.ReleaseBuildError):
                release.release_subtree_hash(root, "missing")

    def test_normalized_archive_is_order_independent_and_exact(self) -> None:
        files = {
            "README.md": b"# PyCForge\n",
            "pycforge/__init__.py": b'__version__ = "0.14.4"\n',
            "pycforge.egg-info/PKG-INFO": b"Version: 0.14.4\n",
        }
        first = release.normalized_source_archive_bytes(files)
        second = release.normalized_source_archive_bytes(
            dict(reversed(list(files.items())))
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first[:10],
            b"\x1f\x8b\x08\x00" + struct.pack("<I", 0) + b"\x00\x03",
        )
        report = release.inspect_source_archive_bytes(
            first,
            expected_files=files,
        )
        self.assertEqual(report["archive_root"], release.SOURCE_ARCHIVE_ROOT)
        self.assertEqual(report["member_count"], len(files))
        self.assertEqual(report["regular_file_count"], len(files))
        self.assertTrue(report["normalized_ustar"])
        self.assertTrue(report["canonical_gzip"])
        self.assertTrue(report["regular_files_only"])

    def test_archive_builder_rejects_ephemera_and_unsafe_paths(self) -> None:
        for files in (
            {"build/item.py": b"bad"},
            {"pycforge/module.pyc": b"bad"},
            {"../escape": b"bad"},
        ):
            with self.subTest(files=files):
                with self.assertRaises(release.ReleaseBuildError):
                    release.normalized_source_archive_bytes(files)

    def test_archive_inspector_rejects_tamper_and_nonregular_members(self) -> None:
        canonical = release.normalized_source_archive_bytes(
            {"payload.txt": b"payload"}
        )
        tampered = bytearray(canonical)
        tampered[-9] ^= 0x01
        with self.assertRaises(release.ReleaseBuildError):
            release.inspect_source_archive_bytes(bytes(tampered))

        symlink_archive = custom_tar(
            [
                (
                    f"{release.SOURCE_ARCHIVE_ROOT}/linked",
                    b"",
                    tarfile.SYMTYPE,
                )
            ]
        )
        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "non-regular",
        ):
            release.inspect_source_archive_bytes(symlink_archive)

    def test_archive_inspector_rejects_non_normalized_member_time(self) -> None:
        archive = custom_tar(
            [
                (
                    f"{release.SOURCE_ARCHIVE_ROOT}/payload.txt",
                    b"payload",
                    tarfile.REGTYPE,
                )
            ],
            mtime=release.SOURCE_DATE_EPOCH + 1,
        )
        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "metadata is not normalized",
        ):
            release.inspect_source_archive_bytes(archive)

    def test_synthetic_wheel_metadata_record_assets_and_native_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            wheel = Path(temp_name) / release.WHEEL_NAME
            assets = synthetic_wheel(wheel)
            report = release.inspect_wheel(wheel, expected_assets=assets)
            self.assertEqual(report["metadata_version"], "0.14.4")
            self.assertEqual(report["tag"], "py3-none-any")
            self.assertEqual(report["svg_assets"], 17)
            self.assertEqual(report["requires_python"], ">=3.11")
            self.assertEqual(
                report["console_scripts"],
                release.EXPECTED_CONSOLE_SCRIPTS,
            )
            self.assertEqual(report["native_member_count"], 0)
            self.assertTrue(report["record_validated"])

    def test_wheel_inspector_rejects_record_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            wheel = Path(temp_name) / release.WHEEL_NAME
            synthetic_wheel(wheel, corrupt_record=True)
            with self.assertRaisesRegex(
                release.ReleaseBuildError,
                "RECORD digest or size mismatch",
            ):
                release.inspect_wheel(wheel)

    def test_wheel_inspector_rejects_native_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            wheel = Path(temp_name) / release.WHEEL_NAME
            synthetic_wheel(wheel, include_native=True)
            with self.assertRaisesRegex(
                release.ReleaseBuildError,
                "native members",
            ):
                release.inspect_wheel(wheel)

    def test_final_fingerprint_is_required_and_declared_tamper_fails(self) -> None:
        tree_sha256 = "1" * 64
        missing = release._fingerprint_state({}, tree_sha256=tree_sha256)
        self.assertFalse(missing["present"])
        self.assertTrue(missing["self_excluded_from_tree_hash"])
        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "requires an assigned",
        ):
            release._fingerprint_state(
                {},
                tree_sha256=tree_sha256,
                required=True,
            )

        valid = release._fingerprint_state(
            {
                release.RELEASE_FINGERPRINT.as_posix(): json.dumps(
                    {
                        "algorithm": "sha256",
                        "domain": release.FINGERPRINT_DOMAIN,
                        "value": tree_sha256,
                        "status": "promoted",
                        "scope_status": "sealed",
                        "file_count": 7,
                    }
                ).encode("utf-8")
            },
            tree_sha256=tree_sha256,
            tree_file_count=7,
            required=True,
        )
        self.assertTrue(valid["present"])
        self.assertTrue(valid["declarations_match"])

        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "does not match",
        ):
            release._fingerprint_state(
                {
                    release.RELEASE_FINGERPRINT.as_posix(): json.dumps(
                        {
                            "algorithm": "sha256",
                            "domain": release.FINGERPRINT_DOMAIN,
                            "value": "2" * 64,
                            "status": "promoted",
                            "scope_status": "sealed",
                            "file_count": 7,
                        }
                    ).encode("utf-8")
                },
                tree_sha256=tree_sha256,
                tree_file_count=7,
                required=True,
            )

        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "domain",
        ):
            release._fingerprint_state(
                {
                    release.RELEASE_FINGERPRINT.as_posix(): b"{}\n",
                },
                tree_sha256=tree_sha256,
                tree_file_count=7,
                required=True,
            )

    def test_final_promotion_evidence_is_complete_and_fail_closed(self) -> None:
        validation = {
            "schema": "pycforge.checkpoint-e-validation-report/1",
            "mode": "promotion",
            "passed": True,
            "promotion_eligible": True,
            "promotion_blockers": [],
            "executable_feature_matrix": {
                "passed": True,
                "coverage_complete": True,
                "matrix_witness_count": 69,
                "unlisted_default_witness_count": 1,
            },
            "full_supported_subset": {
                "passed": True,
                "fixed_case_count": 16,
                "generated_case_count": 64,
                "case_count": 80,
                "generated_missing_families": [],
            },
            "sealed_predecessor_equivalence": {
                "passed": True,
                "promotion_eligible": True,
                "case_count": 80,
                "matched_case_count": 80,
                "mismatched_case_count": 0,
                "exact_result_json_byte_equivalence": True,
            },
        }
        files = {
            release.HANDOFF_NAME: b"x" * 256,
            release.RELEASE_FINGERPRINT.as_posix(): b"{}\n",
            "transition/checkpoint_e/manifest.json": json.dumps(
                {
                    "schema_version": (
                        "pycforge.checkpoint-e-manifest/0.14.4"
                    ),
                    "version": "0.14.4",
                    "status": "promoted",
                    "scope_status": "sealed",
                }
            ).encode("utf-8"),
            "evidence/checkpoint_e/release_report.json": json.dumps(
                {
                    "schema_version": (
                        "pycforge.checkpoint-e-release-report/0.14.4"
                    ),
                    "release_version": "0.14.4",
                    "status": "promoted",
                    "scope_status": "sealed",
                }
            ).encode("utf-8"),
            "evidence/checkpoint_e/full_subset_validation.json": json.dumps(
                validation
            ).encode("utf-8"),
        }

        report = release._verify_promotion_evidence(files)

        self.assertTrue(report["passed"])
        self.assertEqual(report["matrix_witnesses"], 69)
        self.assertEqual(report["promotion_cases"], 80)
        self.assertEqual(report["predecessor_exact_matches"], 80)

        validation["full_supported_subset"]["generated_case_count"] = 63
        files["evidence/checkpoint_e/full_subset_validation.json"] = json.dumps(
            validation
        ).encode("utf-8")
        with self.assertRaisesRegex(
            release.ReleaseBuildError,
            "16\\+64",
        ):
            release._verify_promotion_evidence(files)

    def test_output_directory_must_be_outside_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            with self.assertRaisesRegex(
                release.ReleaseBuildError,
                "outside the source tree",
            ):
                release._ensure_output_is_outside_source(
                    root,
                    root / "release-output",
                )
            release._ensure_output_is_outside_source(
                root,
                root.parent / f"{root.name}-external",
            )


if __name__ == "__main__":
    unittest.main()
