from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import tools.validate_phase15b as validator


ROOT = Path(__file__).resolve().parents[1]


class Phase15BValidatorTests(unittest.TestCase):
    def test_exact_phase_contracts_are_literal(self) -> None:
        self.assertEqual(
            validator.VALIDATION_SCHEMA,
            "pycforge.phase15b-validation-report/1",
        )
        self.assertEqual(validator.EXPECTED_PACKAGE_VERSION, "0.15.1")
        self.assertEqual(validator.EXPECTED_CONVERTER_CONTRACT, "0.14.3")
        self.assertEqual(
            validator.EXPECTED_WORKSPACE_CONTRACT,
            "pycforge-workspace/0.4",
        )
        self.assertEqual(
            validator.EXPECTED_ACTION_REGISTRY,
            "pycforge.action-registry/0.1",
        )
        self.assertEqual(
            validator.EXPECTED_VISUAL_SYSTEM,
            "pycforge.visual-system/0.1",
        )
        self.assertEqual(validator.EXPECTED_SETTINGS_SCHEMA, 1)

    def test_phase15c_identities_fail_closed_while_converter_custody_passes(
        self,
    ) -> None:
        root_custody = validator.audit_validator_root(ROOT)
        identities = validator.audit_contract_identities(ROOT)
        converter = validator.audit_frozen_converter_subtree(ROOT)

        self.assertTrue(root_custody["passed"], root_custody["errors"])
        self.assertFalse(identities["passed"])
        self.assertEqual(
            identities["errors"],
            [
                "project_package identity is '0.15.2', expected '0.15.1'",
                "module_package identity is '0.15.2', expected '0.15.1'",
                (
                    "workspace identity is 'pycforge-workspace/0.5', "
                    "expected 'pycforge-workspace/0.4'"
                ),
                (
                    "action_registry identity is "
                    "'pycforge.action-registry/0.2', expected "
                    "'pycforge.action-registry/0.1'"
                ),
                (
                    "visual_system identity is "
                    "'pycforge.visual-system/0.2', expected "
                    "'pycforge.visual-system/0.1'"
                ),
            ],
        )
        self.assertTrue(converter["passed"], converter["errors"])
        self.assertEqual(converter["file_count"], 92)

    def test_alternate_root_cannot_claim_imported_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = validator.audit_validator_root(Path(directory))

        self.assertFalse(audit["passed"])
        self.assertFalse(audit["imported_candidate_exercised"])

    def test_validation_subject_hashes_the_exact_candidate_map(self) -> None:
        from tools.build_phase15b_release import (
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT,
            VALIDATION_SUBJECT_DOMAIN,
            hash_file_map,
            release_file_map,
        )

        candidate = release_file_map(ROOT)
        excluded = [
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT.as_posix(),
        ]
        for path in excluded:
            candidate.pop(path, None)
        expected = hash_file_map(
            candidate,
            domain=VALIDATION_SUBJECT_DOMAIN,
        )

        audit = validator.audit_validation_subject(ROOT)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(audit["domain"], VALIDATION_SUBJECT_DOMAIN)
        self.assertEqual(audit["sha256"], expected)
        self.assertEqual(audit["file_count"], len(candidate))
        self.assertEqual(audit["excluded"], excluded)
        self.assertNotIn("release_file_map", validator.__dict__)
        self.assertNotIn("hash_file_map", validator.__dict__)

    def test_validation_subject_excludes_both_self_outputs(self) -> None:
        from tools.build_phase15b_release import (
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT,
            VALIDATION_SUBJECT_DOMAIN,
            hash_file_map,
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / INTERNAL_VALIDATION_REPORT
            fingerprint = root / RELEASE_FINGERPRINT
            report.parent.mkdir(parents=True)
            fingerprint.parent.mkdir(parents=True)
            report.write_bytes(b"validation report")
            fingerprint.write_bytes(b"release fingerprint")
            (root / "candidate.txt").write_bytes(b"candidate bytes")

            audit = validator.audit_validation_subject(root)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(audit["file_count"], 1)
        self.assertEqual(
            audit["sha256"],
            hash_file_map(
                {"candidate.txt": b"candidate bytes"},
                domain=VALIDATION_SUBJECT_DOMAIN,
            ),
        )
        self.assertEqual(
            audit["excluded"],
            [
                INTERNAL_VALIDATION_REPORT,
                RELEASE_FINGERPRINT.as_posix(),
            ],
        )

    def test_validation_subject_hash_failure_fails_closed(self) -> None:
        import tools.build_phase15b_release as builder

        with patch.object(
            builder,
            "release_file_map",
            side_effect=OSError("candidate unavailable"),
        ):
            audit = validator.audit_validation_subject(ROOT)

        self.assertIs(audit["passed"], False)
        self.assertIsNone(audit["sha256"])
        self.assertIsNone(audit["file_count"])
        self.assertIn(
            "cannot establish validation-subject custody",
            "\n".join(audit["errors"]),
        )

    def test_validation_subject_runs_in_every_mode_and_gates_report(self) -> None:
        failed = {
            "audit": "phase15b-validation-subject",
            "passed": False,
            "errors": ["subject unavailable"],
        }

        def safe(name, _function, *_args, **_kwargs):
            if name == "phase15b-validation-subject":
                return failed
            return {"audit": name, "passed": True, "errors": []}

        for mode in ("quick", "full", "promotion"):
            with self.subTest(mode=mode), patch.object(
                validator,
                "_safe_audit",
                side_effect=safe,
            ):
                report = validator.run_validation(
                    root=ROOT,
                    mode=mode,
                    search_predecessor=False,
                )

            names = [audit["audit"] for audit in report["audits"]]
            self.assertEqual(
                names.count("phase15b-validation-subject"),
                1,
            )
            self.assertIs(report["passed"], False)
            self.assertIs(report["phase_15b_gate_eligible"], False)

    def test_malformed_audit_passed_values_fail_closed(self) -> None:
        for value in ("false", 1, None, []):
            with self.subTest(value=value):
                audit = validator._safe_audit(
                    "typed-audit",
                    lambda value=value: {
                        "audit": "typed-audit",
                        "passed": value,
                        "errors": [],
                    },
                )
                self.assertIs(audit["passed"], False)
                self.assertEqual(audit["status"], "internal-error")

        failed = {
            "audit": "typed-audit",
            "passed": False,
            "errors": ["expected failure"],
        }
        self.assertIs(
            validator._safe_audit(
                "typed-audit",
                lambda: failed,
            ),
            failed,
        )

        malformed = {
            "audit": "typed-audit",
            "passed": "false",
            "errors": [],
        }
        with patch.object(
            validator,
            "_safe_audit",
            return_value=malformed,
        ):
            report = validator.run_validation(
                root=ROOT,
                mode="quick",
                search_predecessor=False,
            )
        self.assertIs(report["passed"], False)

    def test_phase15c_action_menu_inventory_fails_closed_with_actual_counts(
        self,
    ) -> None:
        audit = validator.audit_action_and_menu_contract(ROOT)

        self.assertFalse(audit["passed"])
        self.assertEqual(
            audit["errors"],
            [
                "action inventory contains 48 entries",
                "context inventory contains 11 entries",
                "main-menu surface order differs",
            ],
        )
        self.assertEqual(audit["actions"], 48)
        self.assertEqual(len(audit["context_surfaces"]), 11)
        self.assertEqual(
            audit["main_menus"],
            [
                "menu.file",
                "menu.edit",
                "menu.view",
                "menu.navigate",
                "menu.conversion",
            ],
        )
        self.assertEqual(len(audit["main_menus"]), 5)
        self.assertEqual(
            audit["generated_c_context_actions"],
            ["edit.copy", "edit.select_all", "search.find"],
        )
        self.assertEqual(audit["generated_c_mutation_actions"], 0)
        self.assertEqual(
            audit["qaction_constructor_owners"],
            ["qt_actions.py"],
        )

    def test_phase15c_visual_inventory_fails_closed_with_actual_counts(
        self,
    ) -> None:
        audit = validator.audit_visual_system(ROOT)

        self.assertFalse(audit["passed"])
        self.assertEqual(
            audit["errors"],
            ["icon catalogue contains 55 entries"],
        )
        self.assertEqual(audit["svg_assets"], 55)
        self.assertEqual(audit["catalogue_entries"], 55)
        self.assertTrue(audit["vector_only"])
        self.assertEqual(audit["missing_menu_state_selectors"], [])
        self.assertTrue(audit["high_dpi_attributes_before_application"])
        self.assertTrue(audit["window_brand_mark"])

    def test_vocabulary_scan_fails_closed_with_sanitized_feedback(self) -> None:
        retired = bytes.fromhex("7370616365706f7274")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "current.txt").write_bytes(retired)
            audit = validator.audit_vocabulary_custody(root)

        self.assertFalse(audit["passed"])
        message = "\n".join(audit["errors"])
        self.assertIn("retired-theme vocabulary", message)
        self.assertNotIn(retired.decode("ascii"), message)

    def test_predecessor_absence_is_optional_unless_explicitly_required(
        self,
    ) -> None:
        optional = validator.audit_predecessor_archive(None, required=False)
        required = validator.audit_predecessor_archive(None, required=True)

        self.assertTrue(optional["passed"])
        self.assertFalse(optional["archive_authenticated"])
        self.assertFalse(required["passed"])

    def test_available_phase15a_predecessor_authenticates_without_extraction(
        self,
    ) -> None:
        archive = validator.locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("optional sealed Phase 15A archive is unavailable")

        audit = validator.audit_predecessor_archive(archive, required=True)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["archive_authenticated"])
        self.assertFalse(audit["archive_extracted"])
        self.assertEqual(
            audit["actual_tree_fingerprint"],
            validator.PREDECESSOR_TREE_FINGERPRINT,
        )

    def test_predecessor_wrong_size_fails_before_read_or_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.PREDECESSOR_ARCHIVE_NAME
            archive.write_bytes(b"x")
            with (
                patch.object(
                    Path,
                    "read_bytes",
                    side_effect=AssertionError(
                        "wrong-size archive must not be read"
                    ),
                ) as read_bytes,
                patch.object(
                    validator.tarfile,
                    "open",
                    side_effect=AssertionError(
                        "wrong-size archive must not be parsed"
                    ),
                ) as tar_open,
            ):
                audit = validator.audit_predecessor_archive(
                    archive,
                    required=True,
                )

        self.assertFalse(audit["passed"])
        self.assertEqual(audit["actual_size"], 1)
        self.assertIsNone(audit["actual_sha256"])
        read_bytes.assert_not_called()
        tar_open.assert_not_called()

    def test_predecessor_wrong_name_fails_before_read_or_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "wrong-predecessor.tar.gz"
            archive.write_bytes(
                b"\x00" * validator.PREDECESSOR_ARCHIVE_SIZE
            )
            with (
                patch.object(
                    Path,
                    "read_bytes",
                    side_effect=AssertionError(
                        "wrong-name archive must not be read"
                    ),
                ) as read_bytes,
                patch.object(
                    validator.tarfile,
                    "open",
                    side_effect=AssertionError(
                        "wrong-name archive must not be parsed"
                    ),
                ) as tar_open,
            ):
                audit = validator.audit_predecessor_archive(
                    archive,
                    required=True,
                )

        self.assertFalse(audit["passed"])
        self.assertEqual(
            audit["actual_size"],
            validator.PREDECESSOR_ARCHIVE_SIZE,
        )
        self.assertIsNone(audit["actual_sha256"])
        read_bytes.assert_not_called()
        tar_open.assert_not_called()

    def test_predecessor_wrong_digest_fails_before_tar_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.PREDECESSOR_ARCHIVE_NAME
            archive.write_bytes(
                b"\x00" * validator.PREDECESSOR_ARCHIVE_SIZE
            )
            with patch.object(
                validator.tarfile,
                "open",
                side_effect=AssertionError(
                    "unauthenticated archive must not be parsed"
                ),
            ) as tar_open:
                audit = validator.audit_predecessor_archive(
                    archive,
                    required=True,
                )

        self.assertFalse(audit["passed"])
        self.assertEqual(
            audit["actual_size"],
            validator.PREDECESSOR_ARCHIVE_SIZE,
        )
        self.assertNotEqual(
            audit["actual_sha256"],
            validator.PREDECESSOR_ARCHIVE_SHA256,
        )
        tar_open.assert_not_called()

    def test_promotion_mode_requires_predecessor_authentication(self) -> None:
        passed = {"audit": "stub", "passed": True, "errors": []}
        predecessor_audit = Mock(return_value=passed)
        stubbed = (
            "audit_validator_root",
            "audit_validation_subject",
            "audit_contract_identities",
            "audit_frozen_converter_subtree",
            "audit_vocabulary_custody",
            "audit_action_and_menu_contract",
            "audit_visual_system",
            "scan_runtime_boundaries",
            "audit_direct_isolated_equivalence",
            "audit_maximum_input_fixtures",
            "audit_hundred_cycle_supervision",
            "audit_platform_scope",
            "audit_safety_scope",
        )
        with ExitStack() as stack:
            for name in stubbed:
                stack.enter_context(
                    patch.object(validator, name, return_value=passed)
                )
            stack.enter_context(
                patch.object(
                    validator,
                    "audit_predecessor_archive",
                    predecessor_audit,
                )
            )
            report = validator.run_validation(
                root=ROOT,
                mode="promotion",
                search_predecessor=False,
            )

        self.assertTrue(report["passed"])
        self.assertTrue(
            predecessor_audit.call_args.kwargs["required"]
        )


if __name__ == "__main__":
    unittest.main()
