from __future__ import annotations

from copy import deepcopy
import csv
from io import BytesIO
import io
from importlib.metadata import version as package_version
import json
import os
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import tools.build_phase15b_release as release_builder
from tools._phase15b_release_contract import scan_source_archive_bytes
from tools.build_phase15b_release import (
    ACTION_REGISTRY_VERSION,
    CONVERTER_CUSTODY_DOMAIN,
    CONVERTER_SUBTREE_SHA256,
    FINGERPRINT_DOMAIN,
    EXPECTED_PROJECT_CONFIGURATION,
    INTERNAL_VALIDATION_REPORT,
    PREDECESSOR_ARCHIVE_NAME,
    PREDECESSOR_ARCHIVE_SHA256,
    PREDECESSOR_ARCHIVE_SIZE,
    PREDECESSOR_TREE_FINGERPRINT,
    RELEASE_FINGERPRINT,
    REQUIRED_WHEEL_MEMBERS,
    SOURCE_ARCHIVE_ROOT,
    SOURCE_DATE_EPOCH,
    VALIDATION_SUBJECT_DOMAIN,
    VISUAL_SYSTEM_VERSION,
    ReleaseBuildError,
    _validate_promotion_report,
    _validate_project_configuration,
    _validate_transition_manifest,
    _record_digest,
    _publish_release_directory,
    canonical_gzip_bytes,
    hash_file_map,
    inspect_source_archive,
    inspect_wheel,
    normalized_source_archive_bytes,
    release_file_map,
    release_subtree_hash,
    release_tree_hash,
    safe_relative_path,
    strict_json_loads,
    validation_subject_hash,
)


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CANDIDATE_FILES = {"README.md": b"PyCForge\n"}


def _synthetic_wheel(
    path: Path,
    package_files: dict[str, bytes],
    *,
    metadata_extra: str = "",
    wheel_extra: str = "",
    entry_extra: str = "",
) -> None:
    dist_info = "pycforge-0.15.1.dist-info"
    members = dict(package_files)
    members[f"{dist_info}/METADATA"] = (
        "Metadata-Version: 2.4\n"
        "Name: pycforge\n"
        "Version: 0.15.1\n"
        "Summary: Deterministic bounded Python-to-C source transpiler\n"
        "Requires-Python: >=3.11\n"
        "Provides-Extra: workspace\n"
        'Requires-Dist: PyQt5<6,>=5.15; extra == "workspace"\n'
        f"{metadata_extra}\n"
    ).encode()
    members[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        f"Generator: setuptools ({package_version('setuptools')})\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
        f"{wheel_extra}\n"
    ).encode()
    members[f"{dist_info}/entry_points.txt"] = (
        "[console_scripts]\n"
        "pycforge = pycforge.laboratory.cli:main\n"
        "pycforge-workspace = pycforge.ide.qt:run\n"
        f"{entry_extra}"
    ).encode()
    members[f"{dist_info}/top_level.txt"] = b"pycforge\n"
    record_name = f"{dist_info}/RECORD"
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, payload in sorted(members.items()):
        writer.writerow((name, _record_digest(payload), len(payload)))
    writer.writerow((record_name, "", ""))
    members[record_name] = output.getvalue().encode()
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in sorted(members.items()):
            archive.writestr(name, payload)


def _valid_promotion_report() -> dict[str, object]:
    policy = {
        "max_source_bytes": 1_000_000,
        "max_source_lines": 100_000,
        "max_diagnostics": 1_000,
        "max_trace_events": 10_000,
        "max_telemetry_events": 10_000,
        "max_tokens": 250_000,
        "max_ast_nodes": 100_000,
        "max_nesting_depth": 128,
        "max_source_documents": 64,
        "max_import_edges": 4_096,
    }
    audits = [
        {
            "audit": "validator-root-custody",
            "passed": True,
            "errors": [],
            "imported_candidate_exercised": True,
            "requested_root": str(ROOT.resolve()),
            "imported_root": str(ROOT.resolve()),
        },
        {
            "audit": "phase15b-contract-identities",
            "passed": True,
            "errors": [],
        },
        {
            "audit": "frozen-converter-subtree",
            "passed": True,
            "errors": [],
            "actual_sha256": CONVERTER_SUBTREE_SHA256,
            "file_count": 92,
        },
        {
            "audit": "phase15a-predecessor-authentication",
            "passed": True,
            "errors": [],
            "required": True,
            "archive_authenticated": True,
            "status": "authenticated",
            "archive_name": PREDECESSOR_ARCHIVE_NAME,
            "expected_size": PREDECESSOR_ARCHIVE_SIZE,
            "actual_size": PREDECESSOR_ARCHIVE_SIZE,
            "expected_sha256": PREDECESSOR_ARCHIVE_SHA256,
            "actual_sha256": PREDECESSOR_ARCHIVE_SHA256,
            "expected_tree_fingerprint": PREDECESSOR_TREE_FINGERPRINT,
            "actual_tree_fingerprint": PREDECESSOR_TREE_FINGERPRINT,
            "converter_subtree_sha256": CONVERTER_SUBTREE_SHA256,
            "archive_extracted": False,
        },
        {
            "audit": "retired-theme-vocabulary-custody",
            "passed": True,
            "errors": [],
            "path_match_count": 0,
            "content_match_count": 0,
        },
        {
            "audit": "declarative-action-and-menu-contract",
            "passed": True,
            "errors": [],
            "actions": 33,
            "generated_c_mutation_actions": 0,
            "qaction_constructor_owners": ["qt_actions.py"],
        },
        {
            "audit": "pycforge-visual-system",
            "passed": True,
            "errors": [],
            "svg_assets": 41,
            "high_dpi_attributes_before_application": True,
            "window_brand_mark": True,
        },
        {
            "audit": "phase15b-validation-subject",
            "passed": True,
            "errors": [],
            "domain": VALIDATION_SUBJECT_DOMAIN,
            "sha256": validation_subject_hash(
                SYNTHETIC_CANDIDATE_FILES
            )[0],
            "file_count": validation_subject_hash(
                SYNTHETIC_CANDIDATE_FILES
            )[1],
            "excluded": [
                INTERNAL_VALIDATION_REPORT,
                RELEASE_FINGERPRINT.as_posix(),
            ],
        },
        {
            "audit": "runtime-isolation-and-toolchain-boundary",
            "passed": True,
            "errors": [],
            "converter_facade_authorities": [
                "pycforge/ide/process_worker.py"
            ],
            "byte_connection_methods": [
                "close",
                "recv_bytes",
                "send_bytes",
            ],
            "byte_transport_call_sites": 3,
            "pickle_transport_allowed": False,
            "object_connection_transport_allowed": False,
            "subprocess_allowed": False,
            "toolchain_allowed": False,
            "gui_in_process_conversion_allowed": False,
        },
        {
            "audit": "direct-vs-isolated-equivalence",
            "passed": True,
            "errors": [],
            "cases": [
                {
                    "case": "single-module",
                    "equivalent": True,
                    "result_sha256": "1" * 64,
                },
                {
                    "case": "keyword-only",
                    "equivalent": True,
                    "result_sha256": "2" * 64,
                },
            ],
            "same_public_facade": True,
            "generated_c_executed": False,
        },
        {
            "audit": "bounded-maximum-input-fixtures",
            "passed": True,
            "errors": [],
            "policy": policy,
            "fixtures": {
                "simultaneous_valid_syntax": {
                    "utf8_bytes": 999_999,
                    "source_lines": 100_000,
                    "tokens": 0,
                    "ast_nodes": 1,
                },
                "exact_byte_ceiling": {
                    "utf8_bytes": 1_000_000,
                    "request_frame_bytes": 1_000_100,
                    "oversized_rejected": True,
                },
                "near_token_ceiling": {"tokens": 249_995},
                "near_ast_ceiling": {"ast_nodes": 99_995},
            },
            "dense_search": {
                "total_matches": 50_000,
                "stored_ranges": 5_000,
                "projection_cap": 5_000,
                "off_caller_thread": True,
            },
            "revision_index_off_caller_thread": True,
            "gui_event_loop_measured": False,
            "visible_ui_measured": False,
            "generated_c_executed": False,
        },
        {
            "audit": "hundred-edit-convert-cancel-cycles",
            "passed": True,
            "errors": [],
            "requested_cycles": 100,
            "submitted_cycles": 100,
            "canceled_cycles": 100,
            "active_worker_cancel_cycles": 10,
            "started_workers": 10,
            "reaped_workers": 10,
            "maximum_simultaneous_workers": 1,
            "active_pid_after_gate": None,
            "pending_generation_after_gate": None,
        },
        {
            "audit": "honest-platform-scope",
            "passed": True,
            "errors": [],
            "visible_windows_11_exercised": False,
            "visible_linux_desktop_exercised": False,
            "phase_15d_platform_gate_required": True,
        },
        {
            "audit": "source-transpiler-safety",
            "passed": True,
            "errors": [],
            "toolchain_invoked": False,
            "compiler_invoked": False,
            "linker_invoked": False,
            "loader_invoked": False,
            "foreign_function_invoked": False,
            "generated_c_compiled": False,
            "generated_c_linked": False,
            "generated_c_loaded": False,
            "generated_c_executed": False,
        },
    ]
    return {
        "schema": "pycforge.phase15b-validation-report/1",
        "mode": "promotion",
        "scope": "phase-15b-application-shell-current-host",
        "passed": True,
        "promotion_eligible": True,
        "promotion_scope": "phase-15b-milestone-only",
        "phase_15b_gate_eligible": True,
        "visible_ui_promotion_eligible": False,
        "distribution_promotion_eligible": False,
        "phase_15b_opened": True,
        "phase_15c_opened": False,
        "phase_15d_opened": False,
        "audits": audits,
    }


class Phase15BReleasePackagingTests(unittest.TestCase):
    def test_release_contract_identities_are_exact(self) -> None:
        self.assertEqual(
            ACTION_REGISTRY_VERSION,
            "pycforge.action-registry/0.1",
        )
        self.assertEqual(
            VISUAL_SYSTEM_VERSION,
            "pycforge.visual-system/0.1",
        )

    def test_safe_relative_paths_fail_closed(self) -> None:
        for value in ("", "/absolute", "../escape", "a/../b", r"a\b"):
            with self.subTest(value=value):
                with self.assertRaises(ReleaseBuildError):
                    safe_relative_path(value)

    def test_release_snapshot_is_descriptor_bound_filtered_and_sorted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / ".pytest_cache").mkdir()
            (root / "zeta.txt").write_bytes(b"zeta")
            (root / "nested" / "alpha.txt").write_bytes(b"alpha")
            (root / ".pytest_cache" / "ignored.txt").write_bytes(
                b"ignored"
            )
            (root / "ignored.pyc").write_bytes(b"ignored")

            real_open = os.open
            regular_opens: list[tuple[object, int, int | None]] = []

            def tracked_open(
                path: object,
                flags: int,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> int:
                descriptor = real_open(
                    path,
                    flags,
                    mode,
                    dir_fd=dir_fd,
                )
                if stat.S_ISREG(os.fstat(descriptor).st_mode):
                    regular_opens.append((path, flags, dir_fd))
                return descriptor

            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("path-based read used"),
            ), patch.object(
                release_builder.os,
                "open",
                side_effect=tracked_open,
            ):
                files = release_file_map(root)

            self.assertEqual(
                files,
                {
                    "nested/alpha.txt": b"alpha",
                    "zeta.txt": b"zeta",
                },
            )
            self.assertEqual(list(files), sorted(files))
            self.assertEqual(len(regular_opens), 2)
            for path, flags, directory_fd in regular_opens:
                self.assertIsNotNone(directory_fd)
                self.assertFalse(Path(path).is_absolute())
                self.assertTrue(flags & os.O_NOFOLLOW)

    def test_release_snapshot_rejects_file_and_directory_symlinks(
        self,
    ) -> None:
        for kind in ("file", "directory"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    if kind == "file":
                        target = root / "target.txt"
                        target.write_bytes(b"target")
                    else:
                        target = root / "target"
                        target.mkdir()
                        (target / "file.txt").write_bytes(b"target")
                    (root / "alias").symlink_to(
                        target,
                        target_is_directory=kind == "directory",
                    )
                    with self.assertRaisesRegex(
                        ReleaseBuildError,
                        "symlink",
                    ):
                        release_file_map(root)

    def test_release_snapshot_rejects_special_files(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "regular.txt").write_bytes(b"regular")
            os.mkfifo(root / "pipe")
            with self.assertRaisesRegex(
                ReleaseBuildError,
                "non-regular file",
            ):
                release_file_map(root)

    def test_release_snapshot_enforces_per_file_and_total_bounds(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_bytes(b"1234")
            with patch.object(
                release_builder,
                "MAX_RELEASE_SNAPSHOT_FILE_BYTES",
                3,
            ):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "per-file byte limit",
                ):
                    release_file_map(root)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.txt").write_bytes(b"123")
            (root / "second.txt").write_bytes(b"456")
            with patch.object(
                release_builder,
                "MAX_RELEASE_SNAPSHOT_FILE_BYTES",
                10,
            ), patch.object(
                release_builder,
                "MAX_RELEASE_SNAPSHOT_TOTAL_BYTES",
                5,
            ):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "total byte limit",
                ):
                    release_file_map(root)

    def test_release_snapshot_detects_growth_during_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "candidate.txt"
            target.write_bytes(b"alpha")
            real_read = os.read
            changed = False

            def racing_read(descriptor: int, size: int) -> bytes:
                nonlocal changed
                if not changed:
                    changed = True
                    target.write_bytes(b"expanded")
                return real_read(descriptor, size)

            with patch.object(
                release_builder.os,
                "read",
                side_effect=racing_read,
            ):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "changed while snapshotting",
                ):
                    release_file_map(root)

    def test_release_snapshot_binds_lookup_to_opened_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidate.txt").write_bytes(b"candidate")
            real_fstat = os.fstat
            changed = False

            def mismatched_fstat(descriptor: int) -> os.stat_result:
                nonlocal changed
                value = real_fstat(descriptor)
                if stat.S_ISREG(value.st_mode) and not changed:
                    changed = True
                    fields = list(value)
                    fields[1] = value.st_ino + 1
                    return os.stat_result(fields)
                return value

            with patch.object(
                release_builder.os,
                "fstat",
                side_effect=mismatched_fstat,
            ):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "changed before snapshot read",
                ):
                    release_file_map(root)

    def test_strict_json_rejects_duplicates_nonfinite_and_reformatting(
        self,
    ) -> None:
        for payload in (
            b'{"key":1,"key":2}\n',
            b'{"value":NaN}\n',
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "not strict JSON",
                ):
                    strict_json_loads(
                        payload,
                        label="candidate",
                        canonical=False,
                    )
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "not canonical JSON",
        ):
            strict_json_loads(
                b'{ "key": 1 }\n',
                label="candidate",
                canonical=True,
            )

    def test_release_directory_publication_is_complete_and_no_clobber(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            stage = parent / "stage"
            output = parent / "release"
            stage.mkdir()
            (stage / "artifact.txt").write_bytes(b"complete")

            _publish_release_directory(stage, output)

            self.assertFalse(stage.exists())
            self.assertEqual(
                (output / "artifact.txt").read_bytes(),
                b"complete",
            )
            self.assertFalse(
                (parent / ".release.publish.lock").exists()
            )

            second_stage = parent / "second-stage"
            second_stage.mkdir()
            (second_stage / "artifact.txt").write_bytes(b"replacement")
            with self.assertRaisesRegex(
                ReleaseBuildError,
                "appeared during the build",
            ):
                _publish_release_directory(second_stage, output)
            self.assertTrue(second_stage.exists())
            self.assertEqual(
                (output / "artifact.txt").read_bytes(),
                b"complete",
            )

    def test_release_publication_failure_leaves_no_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            stage = parent / "stage"
            output = parent / "release"
            stage.mkdir()
            (stage / "artifact.txt").write_bytes(b"complete")
            with patch.object(
                os,
                "rename",
                side_effect=OSError("injected publication failure"),
            ):
                with self.assertRaisesRegex(
                    ReleaseBuildError,
                    "cannot publish release directory atomically",
                ):
                    _publish_release_directory(stage, output)
            self.assertFalse(output.exists())
            self.assertTrue(stage.exists())
            self.assertFalse(
                (parent / ".release.publish.lock").exists()
            )

    def test_source_archive_is_normalized_clean_and_order_independent(
        self,
    ) -> None:
        files = {
            "README.md": b"PyCForge Phase 15B\n",
            "pycforge/_version.py": b'__version__ = "0.15.1"\n',
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
        self.assertTrue(scan_source_archive_bytes(first).passed)

    def test_source_archive_inspection_rejects_noncanonical_metadata(
        self,
    ) -> None:
        files = {"README.md": b"PyCForge\n"}
        raw = BytesIO()
        with tarfile.open(
            fileobj=raw,
            mode="w",
            format=tarfile.USTAR_FORMAT,
        ) as archive:
            payload = files["README.md"]
            info = tarfile.TarInfo(
                f"{SOURCE_ARCHIVE_ROOT}/README.md"
            )
            info.size = len(payload)
            info.mode = 0o600
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = SOURCE_DATE_EPOCH
            archive.addfile(info, BytesIO(payload))
        candidate = canonical_gzip_bytes(raw.getvalue())

        with self.assertRaisesRegex(
            ReleaseBuildError,
            "normalized release encoding",
        ):
            inspect_source_archive(candidate, files)

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

    def test_converter_subtree_matches_frozen_custody(self) -> None:
        digest, count = release_subtree_hash(
            ROOT,
            "pycforge/converter",
            domain=CONVERTER_CUSTODY_DOMAIN,
        )
        self.assertEqual(digest, CONVERTER_SUBTREE_SHA256)
        self.assertEqual(count, 92)

    def test_wheel_rejects_undeclared_binary_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "candidate.whl"
            with ZipFile(wheel, "w", compression=ZIP_DEFLATED) as archive:
                for name in sorted(REQUIRED_WHEEL_MEMBERS):
                    archive.writestr(name, b"# source\n")
                archive.writestr(
                    "pycforge/opaque_payload.bin",
                    b"\x7fELF\x00payload",
                )
            with self.assertRaisesRegex(
                ReleaseBuildError,
                "exact source map",
            ):
                inspect_wheel(
                    wheel,
                    expected_package_files={
                        name: b"# source\n"
                        for name in REQUIRED_WHEEL_MEMBERS
                    },
                )

    def test_wheel_rejects_modified_source_under_an_exact_name(self) -> None:
        expected = {
            name: b"# source\n" for name in REQUIRED_WHEEL_MEMBERS
        }
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "candidate.whl"
            with ZipFile(wheel, "w", compression=ZIP_DEFLATED) as archive:
                for name, payload in sorted(expected.items()):
                    if name == "pycforge/ide/qt.py":
                        payload = (
                            b"import subprocess\n"
                            b"subprocess.run(['cc', 'output.c'])\n"
                        )
                    archive.writestr(name, payload)
            with self.assertRaisesRegex(
                ReleaseBuildError,
                "bytes differ from the audited source map",
            ):
                inspect_wheel(
                    wheel,
                    expected_package_files=expected,
                )

    def test_wheel_metadata_and_entry_points_are_exact(self) -> None:
        package_files = {
            name: b"# source\n" for name in REQUIRED_WHEEL_MEMBERS
        }
        package_files.update(
            {
                f"pycforge/ide/resources/icons/test-{index:02d}.svg": (
                    b'<svg viewBox="0 0 24 24"><path/></svg>\n'
                )
                for index in range(41)
            }
        )
        cases = (
            (
                {"metadata_extra": "Requires-Dist: unapproved"},
                "dependency inventory",
            ),
            (
                {"wheel_extra": "Tag: cp312-cp312-linux_x86_64"},
                "tag inventory",
            ),
            (
                {"entry_extra": "\n[unapproved]\ncommand = module:main\n"},
                "entry-point groups",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.whl"
            _synthetic_wheel(baseline, package_files)
            report = inspect_wheel(
                baseline,
                expected_package_files=package_files,
            )
            self.assertTrue(report["package_bytes_exact"])
            for index, (mutation, message) in enumerate(cases):
                candidate = root / f"candidate-{index}.whl"
                _synthetic_wheel(candidate, package_files, **mutation)
                with self.subTest(mutation=mutation):
                    with self.assertRaisesRegex(ReleaseBuildError, message):
                        inspect_wheel(
                            candidate,
                            expected_package_files=package_files,
                        )

    def test_promotion_records_require_exact_boolean_types(self) -> None:
        invalid_report = {
            "schema": "pycforge.phase15b-validation-report/1",
            "mode": "promotion",
            "scope": "phase-15b-application-shell-current-host",
            "passed": "false",
            "promotion_eligible": "false",
            "promotion_scope": "phase-15b-milestone-only",
            "phase_15b_gate_eligible": "false",
            "visible_ui_promotion_eligible": False,
            "distribution_promotion_eligible": False,
            "phase_15b_opened": True,
            "phase_15c_opened": False,
            "phase_15d_opened": False,
            "audits": [{"passed": True}],
        }
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "promotion validation is not exact",
        ):
            _validate_promotion_report(
                invalid_report,
                candidate_files=SYNTHETIC_CANDIDATE_FILES,
                candidate_root=ROOT,
            )

        incomplete_audits = {
            **invalid_report,
            "passed": True,
            "promotion_eligible": True,
            "phase_15b_gate_eligible": True,
            "audits": [{"passed": True, "errors": []}],
        }
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "audit inventory is not exact",
        ):
            _validate_promotion_report(
                incomplete_audits,
                candidate_files=SYNTHETIC_CANDIDATE_FILES,
                candidate_root=ROOT,
            )

        invalid_manifest = json.loads(
            (ROOT / "transition/phase_15b/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        invalid_manifest["status"] = "promoted"
        invalid_manifest["scope_status"] = "sealed"
        invalid_manifest["promotion"].update(
            {
                "phase_15b_implemented": True,
                "phase_15b_validated": "true",
                "phase_15b_promoted": True,
                "phase_15b_sealed": True,
                "release_fingerprint_assigned": True,
                "packaging_validated": True,
            }
        )
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "promotion flags are not exact",
        ):
            _validate_transition_manifest(invalid_manifest)

    def test_promotion_runtime_evidence_cannot_be_empty(self) -> None:
        report = _valid_promotion_report()
        _validate_promotion_report(
            report,
            candidate_files=SYNTHETIC_CANDIDATE_FILES,
            candidate_root=ROOT,
        )
        expected_messages = {
            "runtime-isolation-and-toolchain-boundary": "runtime-isolation",
            "direct-vs-isolated-equivalence": "direct-isolated",
            "bounded-maximum-input-fixtures": "maximum-input",
            "hundred-edit-convert-cancel-cycles": "stress-cycle",
        }
        for audit_name, message in expected_messages.items():
            candidate = deepcopy(report)
            audits = candidate["audits"]
            assert isinstance(audits, list)
            audit = next(
                item for item in audits if item["audit"] == audit_name
            )
            audit.clear()
            audit.update(
                {"audit": audit_name, "passed": True, "errors": []}
            )
            with self.subTest(audit=audit_name):
                with self.assertRaisesRegex(ReleaseBuildError, message):
                    _validate_promotion_report(
                        candidate,
                        candidate_files=SYNTHETIC_CANDIDATE_FILES,
                        candidate_root=ROOT,
                    )

    def test_promotion_evidence_is_bound_to_exact_candidate(self) -> None:
        report = _valid_promotion_report()
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "validation subject is not bound",
        ):
            _validate_promotion_report(
                report,
                candidate_files={"README.md": b"changed\n"},
                candidate_root=ROOT,
            )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ReleaseBuildError,
                "validator root custody",
            ):
                _validate_promotion_report(
                    report,
                    candidate_files=SYNTHETIC_CANDIDATE_FILES,
                    candidate_root=Path(directory),
                )
        candidate = deepcopy(report)
        audits = candidate["audits"]
        assert isinstance(audits, list)
        predecessor = next(
            item
            for item in audits
            if item["audit"] == "phase15a-predecessor-authentication"
        )
        predecessor["actual_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "predecessor is not authenticated",
        ):
            _validate_promotion_report(
                candidate,
                candidate_files=SYNTHETIC_CANDIDATE_FILES,
                candidate_root=ROOT,
            )

    def test_project_configuration_rejects_custom_build_backend(self) -> None:
        configuration = {
            **EXPECTED_PROJECT_CONFIGURATION,
            "build-system": {
                "requires": ["custom-backend"],
                "build-backend": "custom_backend",
            },
        }
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "configuration is not exact",
        ):
            _validate_project_configuration(
                configuration,
                {"pyproject.toml": b""},
            )
        with self.assertRaisesRegex(
            ReleaseBuildError,
            "executable build file",
        ):
            _validate_project_configuration(
                EXPECTED_PROJECT_CONFIGURATION,
                {"setup.py": b"raise SystemExit\n"},
            )


if __name__ == "__main__":
    unittest.main()
