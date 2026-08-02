from __future__ import annotations

import gzip
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path, PurePosixPath

import tools.validate_phase14d as validator
from tools.validate_checkpoint_e import (
    SEALED_PREDECESSOR_ROOT as PHASE14D_ARCHIVE_ROOT,
    locate_predecessor_archive as locate_phase14d_archive,
)
from tools.validate_phase14d import (
    EXPECTED_CONTRACTS,
    EXPECTED_PHASE14C_CONTRACTS,
    PREDECESSOR_ARCHIVE_SHA256,
    PREDECESSOR_ARCHIVE_SIZE,
    PREDECESSOR_CONVERTER_SHA256,
    PREDECESSOR_FINGERPRINT,
    PREDECESSOR_TREE_SHA256,
    PREDECESSOR_WHEEL_SHA256,
    PREDECESSOR_WHEEL_SIZE,
    RELEASE_FINGERPRINT,
    TOOLCHAIN_INVOKED,
    accepted_keyword_only_errors,
    archive_file_map,
    bounded_profile_errors,
    cancellation_errors,
    canonical_archive_subtree_hash,
    canonical_archive_tree_hash,
    canonical_release_tree_hash,
    current_contracts,
    exact_mapping_errors,
    historical_phase14c_contracts,
    historical_phase14c_errors,
    independent_tamper_errors,
    locate_predecessor_archive,
    locate_predecessor_wheel,
    predecessor_errors,
    predecessor_wheel_errors,
    rejection_matrix_errors,
    source_archive_errors,
)


ROOT = Path(__file__).resolve().parents[1]
FIXED_EPOCH = 1_700_000_000


def write_normalized_source_archive(
    archive: Path,
    members: dict[str, bytes],
) -> None:
    raw = io.BytesIO()
    with tarfile.open(
        fileobj=raw,
        mode="w",
        format=tarfile.USTAR_FORMAT,
    ) as package:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = FIXED_EPOCH
            package.addfile(info, io.BytesIO(data))
    archive.write_bytes(validator.canonical_gzip_bytes(raw.getvalue()))


class Phase14DValidatorTests(unittest.TestCase):
    def test_active_contracts_match_literal_phase14d_contract(self) -> None:
        self.assertEqual(current_contracts(), EXPECTED_CONTRACTS)

    def test_validator_names_exact_active_and_historical_identities(self) -> None:
        source = (ROOT / "tools/validate_phase14d.py").read_text(encoding="utf-8")
        for identity in (
            '"phase14-required-keyword-only-calls-v0.14.3"',
            '"c-renderer-v0.14.3"',
            '"fact-table/0.14.3"',
            '"conversion-plan/0.14.3"',
            '"c-ir/0.14.3"',
            '"generated-c/0.14.3"',
            '"phase14-direct-keyword-calls-v0.14.2"',
            '"c-renderer-v0.14.2"',
        ):
            self.assertIn(identity, source)
        self.assertIn("fingerprint_to_omit=PREDECESSOR_FINGERPRINT", source)

    def test_historical_contracts_match_literal_phase14c_identities(self) -> None:
        self.assertEqual(
            historical_phase14c_contracts(),
            EXPECTED_PHASE14C_CONTRACTS,
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

    def test_keyword_only_acceptance_is_closed_and_deterministic(self) -> None:
        self.assertEqual(accepted_keyword_only_errors(ROOT), [])

    def test_rejection_matrix_preserves_specific_primary_diagnostics(self) -> None:
        self.assertEqual(rejection_matrix_errors(), [])

    def test_cross_module_profile_remains_bounded_and_exact(self) -> None:
        self.assertEqual(bounded_profile_errors(), [])

    def test_independent_reconstruction_rejects_tampering(self) -> None:
        self.assertEqual(independent_tamper_errors(), [])

    def test_cancellation_retires_output_and_interrupts_validation(self) -> None:
        self.assertEqual(cancellation_errors(), [])

    def test_explicit_historical_phase14c_behavior_is_exact(self) -> None:
        self.assertEqual(historical_phase14c_errors(), [])

    def test_opening_files_name_only_new_phase14d_verification_and_runtime(self) -> None:
        required = validator._opening_required_files()
        self.assertIn("tools/validate_phase14d.py", required)
        self.assertIn("tests/test_phase14d_keyword_only_contracts.py", required)
        self.assertIn("tests/test_phase14d_cumulative_eligibility.py", required)
        self.assertNotIn("tools/validate_phase14c.py", required)
        missing = [name for name in sorted(required) if not (ROOT / name).is_file()]
        self.assertEqual(missing, [])

    def test_promoted_files_cannot_be_omitted_by_the_manifest(self) -> None:
        canonical = {
            "README.md",
            "CURRENT_STATE.md",
            "CHANGELOG.md",
            "PyCForge_Phase_14D_v0_14_3_Project_Handoff.txt",
            "specifications/phase14d_required_keyword_only_calls.md",
            "transition/phase_14d/baseline_fingerprint.json",
            "transition/phase_14d/entry_criteria.md",
            "transition/phase_14d/required_keyword_only_calls_decision.md",
            "transition/phase_14d/breadth_and_change_budgets.md",
            "transition/phase_14d/rollback_conditions.md",
            "transition/phase_14d/opening_evidence.md",
            "transition/phase_14d/gate_evidence.md",
            "transition/phase_14d/manifest.json",
            "transition/phase_14d/release_fingerprint.json",
            "evidence/phase_14d/conversion_debt.json",
            "evidence/phase_14d/entry_report.json",
            "evidence/phase_14d/release_report.json",
            "pycforge/converter/keyword_only_calls/__init__.py",
            "pycforge/converter/keyword_only_calls/analysis.py",
            "pycforge/converter/keyword_only_calls/lowering.py",
            "pycforge/converter/keyword_only_calls/model.py",
            "pycforge/converter/keyword_only_calls/validation.py",
            "pycforge/laboratory/keyword_only_audit.py",
            "tests/test_phase14d_keyword_only_contracts.py",
            "tests/test_phase14d_keyword_only_analysis.py",
            "tests/test_phase14d_keyword_only_lowering.py",
            "tests/test_phase14d_keyword_only_hardening.py",
            "tests/test_phase14d_cumulative_eligibility.py",
            "tests/test_validate_phase14d.py",
            "tools/validate_phase14d.py",
        }
        self.assertTrue(
            canonical.issubset(
                validator._promoted_required_files(
                    {"required_contract_files": []}
                )
            )
        )
        self.assertTrue(
            validator._manifest_required_file_errors(
                {"required_contract_files": []}
            )
        )
        for omitted in sorted(canonical):
            with self.subTest(omitted=omitted):
                declared = sorted(canonical - {omitted})
                self.assertIn(
                    omitted,
                    validator._promoted_required_files(
                        {"required_contract_files": declared}
                    ),
                )
                errors = validator._manifest_required_file_errors(
                    {"required_contract_files": declared}
                )
                self.assertEqual(len(errors), 1)
                self.assertIn(omitted, errors[0])

    def test_predecessor_constants_match_pause_resume_custody(self) -> None:
        self.assertEqual(PREDECESSOR_ARCHIVE_SIZE, 1_181_034)
        self.assertEqual(
            PREDECESSOR_ARCHIVE_SHA256,
            "1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8",
        )
        self.assertEqual(
            PREDECESSOR_TREE_SHA256,
            "be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4",
        )
        self.assertEqual(
            PREDECESSOR_CONVERTER_SHA256,
            "ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b",
        )
        self.assertEqual(PREDECESSOR_WHEEL_SIZE, 309_077)
        self.assertEqual(
            PREDECESSOR_WHEEL_SHA256,
            "6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5",
        )
        expected_transitions = {
            "sealed_phase14a_transition_subtree_sha256": (
                "transition/phase_14",
                "cb92282a063d72c22b6db41cd2c0d2da8b7bdb8cb3c5a3290530744a22d6fe8a",
            ),
            "sealed_phase14b_transition_subtree_sha256": (
                "transition/phase_14b",
                "caddcbe153d005da9d67c14e182ecb6c6bde0e6e7a161dd50807a78aed7cd9e8",
            ),
            "sealed_phase14c_transition_subtree_sha256": (
                "transition/phase_14c",
                "95e5528fc7dca898a7d6883aed101d3a4c5fca5ef53988960307c50f610d04c5",
            ),
        }
        self.assertEqual(
            validator.SEALED_TRANSITION_SUBTREE_IDENTITIES,
            expected_transitions,
        )
        fingerprint = json.loads(
            (ROOT / RELEASE_FINGERPRINT).read_text(encoding="utf-8")
        )
        self.assertEqual(
            validator._sealed_transition_subtree_errors(ROOT, fingerprint),
            [],
        )
        forged = dict(fingerprint)
        forged["sealed_phase14b_transition_subtree_sha256"] = "0" * 64
        self.assertTrue(
            any(
                "sealed_phase14b_transition_subtree_sha256" in error
                for error in validator._sealed_transition_subtree_errors(
                    ROOT,
                    forged,
                )
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            copied_root = Path(directory)
            for prefix, _digest in expected_transitions.values():
                source = ROOT / prefix
                destination = copied_root / prefix
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, destination)
            changed = copied_root / "transition/phase_14c/manifest.json"
            changed.write_bytes(changed.read_bytes() + b"\n")
            self.assertTrue(
                any(
                    "transition/phase_14c" in error
                    for error in validator._sealed_transition_subtree_errors(
                        copied_root,
                        fingerprint,
                    )
                )
            )

    def test_available_predecessor_archive_authenticates_exactly(self) -> None:
        archive = locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("sealed Phase 14C archive is not beside the release tree")
        self.assertEqual(predecessor_errors(archive), [])
        self.assertEqual(
            canonical_archive_tree_hash(
                archive,
                fingerprint_to_omit=PREDECESSOR_FINGERPRINT,
            ),
            PREDECESSOR_TREE_SHA256,
        )
        self.assertEqual(
            canonical_archive_subtree_hash(archive, "pycforge/converter"),
            PREDECESSOR_CONVERTER_SHA256,
        )

    def test_available_predecessor_wheel_authenticates_exactly(self) -> None:
        wheel = locate_predecessor_wheel(ROOT)
        if wheel is None:
            self.skipTest("sealed Phase 14C wheel is not beside the release tree")
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

    def test_release_tree_hash_excludes_only_phase14d_self_and_ephemera(self) -> None:
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

    def test_source_archive_can_exclude_14d_but_not_14c_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "candidate.tar.gz"
            members = {
                "release/source.txt": b"stable",
                "release/transition/phase_14c/release_fingerprint.json": b"history",
                "release/transition/phase_14d/release_fingerprint.json": b"self",
            }
            with tarfile.open(archive, "w:gz") as package:
                for name, data in members.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    package.addfile(info, io.BytesIO(data))
            files = archive_file_map(
                archive,
                fingerprint_to_omit=PurePosixPath(
                    "transition/phase_14d/release_fingerprint.json"
                ),
            )
            self.assertIn("transition/phase_14c/release_fingerprint.json", files)
            self.assertNotIn("transition/phase_14d/release_fingerprint.json", files)

    def test_source_archive_rejects_a_forged_embedded_fingerprint(self) -> None:
        source_files = {"source.txt": b"stable release content"}
        fingerprint = {
            "algorithm": "sha256",
            "domain": validator.FINGERPRINT_DOMAIN,
            "status": "promoted",
            "value": validator._hash_file_map(source_files),
            "artifacts": {
                "source_archive": {
                    "filename": validator.SOURCE_ARCHIVE_NAME,
                    "fixed_epoch": FIXED_EPOCH,
                    "normalized_builds_compared": 2,
                    "normalized_builds_byte_identical": True,
                    "size_recorded_externally": True,
                    "sha256_recorded_externally": True,
                }
            },
        }
        root_bytes = (
            json.dumps(fingerprint, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        forged = dict(fingerprint)
        forged["status"] = "forged-stale-copy"
        forged_bytes = (
            json.dumps(forged, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.SOURCE_ARCHIVE_NAME
            members = {
                "release/source.txt": source_files["source.txt"],
                (
                    "release/"
                    + RELEASE_FINGERPRINT.as_posix()
                ): forged_bytes,
            }
            write_normalized_source_archive(archive, members)
            errors = source_archive_errors(
                archive,
                fingerprint,
                fingerprint_bytes=root_bytes,
            )
        self.assertIn(
            "source archive embedded Phase 14D release fingerprint "
            "does not match the supplied root fingerprint",
            errors,
        )
        self.assertIn(
            "source archive embedded Phase 14D release fingerprint bytes "
            "do not match the root fingerprint file",
            errors,
        )
        self.assertNotIn("source archive release tree hash mismatch", errors)

    def test_source_archive_requires_exact_root_fingerprint_bytes(self) -> None:
        source_files = {"source.txt": b"stable release content"}
        fingerprint = {
            "value": validator._hash_file_map(source_files),
            "artifacts": {
                "source_archive": {
                    "filename": validator.SOURCE_ARCHIVE_NAME,
                    "fixed_epoch": FIXED_EPOCH,
                    "normalized_builds_compared": 2,
                    "normalized_builds_byte_identical": True,
                    "size_recorded_externally": True,
                    "sha256_recorded_externally": True,
                }
            },
        }
        embedded_bytes = json.dumps(
            fingerprint,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        root_bytes = (
            json.dumps(fingerprint, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.SOURCE_ARCHIVE_NAME
            write_normalized_source_archive(
                archive,
                {
                    "release/source.txt": source_files["source.txt"],
                    (
                        "release/"
                        + RELEASE_FINGERPRINT.as_posix()
                    ): embedded_bytes,
                },
            )
            errors = source_archive_errors(
                archive,
                fingerprint,
                fingerprint_bytes=root_bytes,
            )
        self.assertEqual(
            errors,
            [
                "source archive embedded Phase 14D release fingerprint bytes "
                "do not match the root fingerprint file"
            ],
        )

    def test_source_archive_rejects_noncanonical_gzip_and_ephemera(self) -> None:
        source_files = {"source.txt": b"stable release content"}
        fingerprint = {
            "value": validator._hash_file_map(source_files),
            "artifacts": {
                "source_archive": {
                    "filename": validator.SOURCE_ARCHIVE_NAME,
                    "fixed_epoch": FIXED_EPOCH,
                    "normalized_builds_compared": 2,
                    "normalized_builds_byte_identical": True,
                    "size_recorded_externally": True,
                    "sha256_recorded_externally": True,
                }
            },
        }
        fingerprint_bytes = (
            json.dumps(fingerprint, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.SOURCE_ARCHIVE_NAME
            write_normalized_source_archive(
                archive,
                {
                    "release/source.txt": source_files["source.txt"],
                    (
                        "release/"
                        + RELEASE_FINGERPRINT.as_posix()
                    ): fingerprint_bytes,
                },
            )
            canonical_bytes = archive.read_bytes()
            raw_tar = gzip.decompress(canonical_bytes)

            archive.write_bytes(
                canonical_bytes
                + gzip.compress(b"second gzip member", compresslevel=6, mtime=0)
            )
            errors = source_archive_errors(
                archive,
                fingerprint,
                fingerprint_bytes=fingerprint_bytes,
            )
        self.assertIn(
            "source archive contains concatenated or trailing gzip data",
            errors,
        )
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.SOURCE_ARCHIVE_NAME
            noncanonical = bytearray(
                gzip.compress(raw_tar, compresslevel=9, mtime=0)
            )
            noncanonical[8] = 0
            self.assertEqual(
                bytes(noncanonical[:10]),
                bytes.fromhex("1f8b0800000000000003"),
            )
            self.assertNotEqual(bytes(noncanonical), canonical_bytes)
            archive.write_bytes(noncanonical)
            errors = source_archive_errors(
                archive,
                fingerprint,
                fingerprint_bytes=fingerprint_bytes,
            )
            self.assertIn(
                "source archive bytes are not canonical level-6 gzip",
                errors,
            )
            self.assertNotIn(
                "source archive gzip header is not normalized with -n",
                errors,
            )

            write_normalized_source_archive(
                archive,
                {
                    "release/source.txt": source_files["source.txt"],
                    (
                        "release/"
                        + RELEASE_FINGERPRINT.as_posix()
                    ): fingerprint_bytes,
                    "release/pkg/__pycache__/payload.pyc": b"ephemera",
                },
            )
            errors = source_archive_errors(
                archive,
                fingerprint,
                fingerprint_bytes=fingerprint_bytes,
            )
            self.assertTrue(
                any(
                    "forbidden release ephemera" in error
                    and "__pycache__/payload.pyc" in error
                    for error in errors
                )
            )
            self.assertNotIn("source archive release tree hash mismatch", errors)

    def test_preseal_mode_allows_unassigned_tree_only_before_promotion(self) -> None:
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
                    root,
                    draft,
                    require_promoted=False,
                ),
                [],
            )
            self.assertTrue(
                validator._fingerprint_errors(
                    root,
                    draft,
                    require_promoted=True,
                )
            )
        self.assertEqual(
            validator._exact_release_test_count_errors(
                dict(validator.EXPECTED_RELEASE_TEST_COUNTS),
                validator.EXPECTED_RELEASE_TEST_COUNTS,
                "release tests",
            ),
            [],
        )
        one_test = {
            "discovered": 1,
            "passed": 1,
            "skipped": 0,
            "failed": 0,
            "phase14d_discovered": 1,
            "phase14d_passed": 1,
            "phase14d_failed": 0,
        }
        self.assertTrue(
            validator._exact_release_test_count_errors(
                one_test,
                validator.EXPECTED_RELEASE_TEST_COUNTS,
                "release tests",
            )
        )
        one_test_manifest = {
            "required_tests": 1,
            "discovered_tests": 1,
            "passed_tests": 1,
            "skipped_tests": 0,
            "failed_tests": 0,
            "phase14d_tests": 1,
            "phase14d_tests_passed": 1,
            "phase14d_tests_failed": 0,
        }
        self.assertTrue(
            validator._exact_release_test_count_errors(
                one_test_manifest,
                validator.EXPECTED_MANIFEST_TEST_COUNTS,
                "manifest tests",
            )
        )
        valid_transcript = (
            "Ran 539 tests in 1.000s\n\n"
            "OK (skipped=15)"
        )
        self.assertEqual(
            validator._unittest_count_errors(
                valid_transcript,
                phase14d_discovered=65,
            ),
            [],
        )
        self.assertTrue(
            validator._unittest_count_errors(
                "Ran 1 test in 0.001s\n\nOK (skipped=0)",
                phase14d_discovered=1,
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "transition/phase_0/baseline_fingerprint.json"
            baseline.parent.mkdir(parents=True)
            baseline.write_bytes(b"sealed-phase-0")

            def mutate_baseline(*_args, **_kwargs):
                baseline.write_bytes(b"test-side-effect")
                return validator.subprocess.CompletedProcess(
                    args=("python", "-m", "unittest"),
                    returncode=0,
                    stdout="",
                    stderr="Ran 539 tests in 1.000s\n\nOK (skipped=15)\n",
                )

            with (
                patch.object(
                    validator,
                    "_phase14d_discovered_count",
                    return_value=(65, None),
                ),
                patch.object(
                    validator.subprocess,
                    "run",
                    side_effect=mutate_baseline,
                ),
            ):
                self.assertIsNone(validator._run_tests(root))
            self.assertEqual(baseline.read_bytes(), b"sealed-phase-0")
        phase14d_discovered, discovery_error = (
            validator._phase14d_discovered_count(ROOT)
        )
        self.assertIsNone(discovery_error)
        self.assertIsInstance(phase14d_discovered, int)
        self.assertGreater(phase14d_discovered, 0)
        promoted = json.loads(
            (ROOT / RELEASE_FINGERPRINT).read_text(encoding="utf-8")
        )
        promoted["value"] = canonical_release_tree_hash(ROOT)
        promoted["tests"] = {
            **promoted["tests"],
            **one_test,
        }
        self.assertTrue(
            any(
                "release fingerprint tests discovered is 1, expected 539"
                in error
                for error in validator._fingerprint_errors(
                    ROOT,
                    promoted,
                    require_promoted=True,
                )
            )
        )

    def test_sealed_phase14d_tree_passes_its_own_authenticated_validator(self) -> None:
        archive = locate_phase14d_archive(ROOT)
        if archive is None:
            self.skipTest(
                "sealed Phase 14D archive is not beside the Checkpoint E tree"
            )
        with tempfile.TemporaryDirectory() as directory:
            extraction = Path(directory)
            with tarfile.open(archive, mode="r:gz") as package:
                package.extractall(extraction, filter="data")
            sealed_root = extraction / PHASE14D_ARCHIVE_ROOT
            completed = validator.subprocess.run(
                [
                    sys.executable,
                    "tools/validate_phase14d.py",
                    "--source-archive",
                    str(archive),
                    "--require-source-archive",
                ],
                cwd=sealed_root,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )
        self.assertIn(
            "PyCForge Phase 14D validation passed",
            completed.stdout,
        )
        self.assertIn(
            "This validator invoked no C compiler",
            completed.stdout,
        )

    def test_validator_declares_and_uses_no_c_toolchain_path(self) -> None:
        self.assertIs(TOOLCHAIN_INVOKED, False)


if __name__ == "__main__":
    unittest.main()
