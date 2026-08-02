from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tools.validate_phase15c as validator


ROOT = Path(__file__).resolve().parents[1]
_RETIRED = bytes.fromhex("7370616365706f7274")


def _promoted_performance_evidence() -> dict[str, object]:
    record = json.loads(
        (ROOT / validator.PERFORMANCE_EVIDENCE).read_text(encoding="utf-8")
    )
    measurement = record["measurement_scope"]
    for key in (
        "real_qapplication_exercised",
        "real_pyqt_widgets_exercised",
        "offscreen_pyqt_widgets_exercised",
        "gui_event_loop_timing_recorded",
    ):
        measurement[key] = True
    record["status"] = "supporting-offscreen-runtime-evidence-passed"
    record["promotion_eligible"] = True
    record["offscreen_runtime"] = {
        "python_version": "3.12.13",
        "pyqt_version": "5.15.11",
        "qt_build_version": "5.15.14",
        "qt_runtime_version": "5.15.19",
        "qpa_platform": "offscreen",
        "qapplication_instances": 1,
        "workspace_test_cases": 18,
        "workspace_test_failures": 0,
        "workspace_test_errors": 0,
        "workspace_test_skips": 0,
        "event_loop": {
            "large_source_characters": 250_113,
            "large_source_minimum_characters": 250_000,
            "first_turn_seconds": 0.0103,
            "first_turn_limit_seconds": 1.0,
            "timer_interval_seconds": 0.01,
            "timer_ticks_while_waiting": 110,
            "within_limit": True,
        },
        "large_file": {
            "window_construction_seconds": 0.054,
            "window_construction_limit_seconds": 8.0,
            "transpilation_seconds": 1.201,
            "transpilation_limit_seconds": 30.0,
            "large_file_mode": True,
            "syntax_highlighter_detached": True,
            "shared_buffer_preserved": True,
        },
        "shutdown": {
            "new_pycforge_threads_after_close": 0,
            "worker_leaks": 0,
        },
    }
    return record


def _write_performance_evidence(
    root: Path,
    record: dict[str, object],
) -> None:
    path = root / validator.PERFORMANCE_EVIDENCE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")


class Phase15CValidatorTests(unittest.TestCase):
    def test_exact_phase_contracts_and_custody_are_literal(self) -> None:
        self.assertEqual(
            validator.VALIDATION_SCHEMA,
            "pycforge.phase15c-validation-report/1",
        )
        self.assertEqual(validator.EXPECTED_PACKAGE_VERSION, "0.15.2")
        self.assertEqual(validator.EXPECTED_CONVERTER_CONTRACT, "0.14.3")
        self.assertEqual(
            validator.EXPECTED_WORKSPACE_CONTRACT,
            "pycforge-workspace/0.5",
        )
        self.assertEqual(
            validator.EXPECTED_ACTION_REGISTRY,
            "pycforge.action-registry/0.2",
        )
        self.assertEqual(
            validator.EXPECTED_VISUAL_SYSTEM,
            "pycforge.visual-system/0.2",
        )
        self.assertEqual(validator.EXPECTED_ACTION_COUNT, 48)
        self.assertEqual(validator.EXPECTED_CONTEXT_COUNT, 11)
        self.assertEqual(validator.EXPECTED_MAIN_MENU_COUNT, 5)
        self.assertEqual(validator.EXPECTED_ICON_COUNT, 55)
        self.assertEqual(
            validator.PREDECESSOR_ARCHIVE_NAME,
            "pycforge_phase_15b_v0_15_1.tar.gz",
        )
        self.assertEqual(validator.PREDECESSOR_ARCHIVE_SIZE, 1_544_352)

    def test_current_identities_and_frozen_converter_pass(self) -> None:
        identities = validator.audit_contract_identities(ROOT)
        converter = validator.audit_frozen_converter_subtree(ROOT)

        self.assertTrue(identities["passed"], identities["errors"])
        self.assertTrue(converter["passed"], converter["errors"])
        self.assertEqual(converter["file_count"], 92)
        self.assertEqual(
            converter["actual_sha256"],
            validator.EXPECTED_CONVERTER_SUBTREE_SHA256,
        )

    def test_alternate_root_cannot_claim_imported_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = validator.audit_validator_root(Path(directory))

        self.assertFalse(audit["passed"])
        self.assertFalse(audit["imported_candidate_exercised"])

    def test_validation_subject_hashes_exact_candidate_and_excludes_self(
        self,
    ) -> None:
        from tools.build_phase15c_release import (
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
        for name in excluded:
            candidate.pop(name, None)
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

    def test_validation_subject_hash_failure_fails_closed(self) -> None:
        import tools.build_phase15c_release as builder

        with patch.object(
            builder,
            "release_file_map",
            side_effect=OSError("candidate unavailable"),
        ):
            audit = validator.audit_validation_subject(ROOT)

        self.assertFalse(audit["passed"])
        self.assertIsNone(audit["sha256"])
        self.assertIn(
            "cannot establish validation-subject custody",
            "\n".join(audit["errors"]),
        )

    def test_action_visual_and_workspace_inventories_are_exact(self) -> None:
        actions = validator.audit_action_and_menu_contract(ROOT)
        visual = validator.audit_visual_system(ROOT)
        workspace = validator.audit_workspace_completeness(ROOT)

        self.assertTrue(actions["passed"], actions["errors"])
        self.assertEqual(actions["actions"], 48)
        self.assertEqual(actions["context_surfaces"], 11)
        self.assertEqual(actions["main_menu_surfaces"], 5)
        self.assertEqual(
            actions["generated_c_context_actions"],
            ["edit.copy", "edit.select_all", "search.find"],
        )
        self.assertEqual(actions["generated_c_mutation_actions"], 0)
        self.assertTrue(visual["passed"], visual["errors"])
        self.assertEqual(visual["svg_assets"], 55)
        self.assertTrue(workspace["passed"], workspace["errors"])
        self.assertEqual(workspace["source_document_limit"], 64)
        self.assertEqual(workspace["source_pane_limit"], 2)
        self.assertEqual(workspace["search_match_limit"], 5_000)
        self.assertEqual(workspace["structure_symbol_limit"], 4_096)
        self.assertEqual(workspace["command_palette_limit"], 50)
        self.assertEqual(workspace["history_entry_limit"], 64)
        self.assertTrue(workspace["latest_wins_observers"])
        self.assertTrue(workspace["pending_sync_invalidates_observers"])
        self.assertTrue(workspace["generated_c_read_only"])
        self.assertTrue(workspace["generated_c_explicit_save_only"])

    def test_workspace_audit_fails_closed_on_bound_drift(self) -> None:
        path = ROOT / "pycforge" / "ide" / "workspace_search.py"
        original = validator._literal_assignment

        def drift(candidate: Path, name: str):
            if candidate == path and name == "MAX_BUNDLE_MATCHES":
                return 5_001
            return original(candidate, name)

        with patch.object(validator, "_literal_assignment", side_effect=drift):
            audit = validator.audit_workspace_completeness(ROOT)

        self.assertFalse(audit["passed"])
        self.assertIn(
            "search_match_limit is 5001, expected 5000",
            audit["errors"],
        )

    def test_vocabulary_scan_is_sanitized_and_ignores_ephemera(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "current.txt").write_bytes(_RETIRED)
            audit = validator.audit_vocabulary_custody(root)

        self.assertFalse(audit["passed"])
        self.assertEqual(audit["content_match_count"], 1)
        self.assertNotIn(
            _RETIRED.decode("ascii"),
            repr(audit).casefold(),
        )

    def test_predecessor_absence_is_optional_unless_required(self) -> None:
        optional = validator.audit_predecessor_archive(None, required=False)
        required = validator.audit_predecessor_archive(None, required=True)

        self.assertTrue(optional["passed"])
        self.assertEqual(optional["status"], "not-present-optional")
        self.assertFalse(required["passed"])
        self.assertEqual(required["status"], "missing-required")

    def test_current_performance_evidence_is_authenticated_in_quick_mode(
        self,
    ) -> None:
        audit = validator.audit_platform_scope(
            ROOT,
            require_runtime_evidence=False,
        )

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["evidence_authenticated"])
        self.assertRegex(audit["evidence_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(audit["real_qapplication_exercised"])
        self.assertTrue(audit["real_pyqt_widgets_exercised"])
        self.assertTrue(audit["offscreen_pyqt_widgets_exercised"])
        self.assertTrue(audit["gui_event_loop_timing_recorded"])
        self.assertFalse(audit["visible_windows_11_exercised"])
        self.assertFalse(audit["visible_linux_desktop_exercised"])
        self.assertTrue(audit["phase_15d_platform_gate_required"])

    def test_candidate_performance_evidence_is_accepted_in_quick_mode(
        self,
    ) -> None:
        record = _promoted_performance_evidence()
        del record["offscreen_runtime"]
        measurement = record["measurement_scope"]
        for key in (
            "real_qapplication_exercised",
            "real_pyqt_widgets_exercised",
            "offscreen_pyqt_widgets_exercised",
            "gui_event_loop_timing_recorded",
        ):
            measurement[key] = False
        record["status"] = "supporting-headless-and-static-contracts-passed"
        record["promotion_eligible"] = False
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_performance_evidence(root, record)
            audit = validator.audit_platform_scope(
                root,
                require_runtime_evidence=False,
            )

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["evidence_authenticated"])
        self.assertFalse(audit["real_qapplication_exercised"])
        self.assertFalse(audit["real_pyqt_widgets_exercised"])
        self.assertFalse(audit["offscreen_pyqt_widgets_exercised"])
        self.assertFalse(audit["gui_event_loop_timing_recorded"])

    def test_promotion_performance_evidence_fails_closed_when_missing_or_false(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = validator.audit_platform_scope(
                Path(directory),
                require_runtime_evidence=True,
            )
        self.assertFalse(missing["passed"])
        self.assertFalse(missing["evidence_authenticated"])
        self.assertIn(
            "performance evidence is unavailable or invalid",
            "\n".join(missing["errors"]),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = _promoted_performance_evidence()
            record["measurement_scope"]["real_pyqt_widgets_exercised"] = False
            _write_performance_evidence(root, record)
            contradictory = validator.audit_platform_scope(
                root,
                require_runtime_evidence=True,
            )
        self.assertFalse(contradictory["passed"])
        self.assertFalse(contradictory["evidence_authenticated"])
        self.assertIn(
            "recorded QApplication/widget evidence is incomplete",
            contradictory["errors"],
        )

    def test_promotion_authenticates_recorded_offscreen_runtime_and_timing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_performance_evidence(
                root,
                _promoted_performance_evidence(),
            )
            audit = validator.audit_platform_scope(
                root,
                require_runtime_evidence=True,
            )

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["evidence_authenticated"])
        self.assertTrue(audit["real_qapplication_exercised"])
        self.assertTrue(audit["real_pyqt_widgets_exercised"])
        self.assertTrue(audit["offscreen_pyqt_widgets_exercised"])
        self.assertTrue(audit["gui_event_loop_timing_recorded"])
        self.assertFalse(audit["visible_windows_11_exercised"])
        self.assertFalse(audit["visible_linux_desktop_exercised"])
        self.assertFalse(audit["display_scaling_matrix_exercised"])
        self.assertFalse(audit["assistive_technology_exercised"])
        self.assertTrue(audit["phase_15d_platform_gate_required"])

    def test_available_phase15b_predecessor_authenticates_without_extraction(
        self,
    ) -> None:
        path = validator.locate_predecessor_archive(ROOT)
        if path is None:
            self.skipTest("authenticated Phase 15B predecessor is unavailable")

        audit = validator.audit_predecessor_archive(path, required=True)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["archive_authenticated"])
        self.assertFalse(audit["archive_extracted"])
        self.assertEqual(
            audit["actual_sha256"],
            validator.PREDECESSOR_ARCHIVE_SHA256,
        )
        self.assertEqual(
            audit["actual_tree_fingerprint"],
            validator.PREDECESSOR_TREE_FINGERPRINT,
        )
        self.assertEqual(
            audit["converter_subtree_sha256"],
            validator.EXPECTED_CONVERTER_SUBTREE_SHA256,
        )

    def test_wrong_predecessor_name_size_and_digest_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong_name = root / "wrong.tar.gz"
            wrong_name.write_bytes(b"x" * validator.PREDECESSOR_ARCHIVE_SIZE)
            audit = validator.audit_predecessor_archive(
                wrong_name,
                required=True,
            )
            self.assertFalse(audit["passed"])
            self.assertIn("filename differs", "\n".join(audit["errors"]))

            wrong_size = root / validator.PREDECESSOR_ARCHIVE_NAME
            wrong_size.write_bytes(b"short")
            audit = validator.audit_predecessor_archive(
                wrong_size,
                required=True,
            )
            self.assertFalse(audit["passed"])
            self.assertIn("size mismatch", "\n".join(audit["errors"]))

            wrong_size.write_bytes(
                b"x" * validator.PREDECESSOR_ARCHIVE_SIZE
            )
            with patch.object(
                validator.tarfile,
                "open",
                side_effect=AssertionError("tar parse must not run"),
            ):
                audit = validator.audit_predecessor_archive(
                    wrong_size,
                    required=True,
                )
            self.assertFalse(audit["passed"])
            self.assertIn("SHA-256 mismatch", "\n".join(audit["errors"]))

    def test_quick_mode_is_deterministic_but_not_promotion_eligible(
        self,
    ) -> None:
        first = validator.run_validation(
            root=ROOT,
            mode="quick",
            search_predecessor=False,
        )
        second = validator.run_validation(
            root=ROOT,
            mode="quick",
            search_predecessor=False,
        )

        self.assertEqual(first, second)
        self.assertTrue(first["passed"])
        self.assertFalse(first["promotion_eligible"])
        self.assertEqual(first["scope"], "phase-15c-workspace-current-host")
        self.assertEqual(
            first["promotion_scope"],
            "phase-15c-milestone-only",
        )
        self.assertTrue(first["phase_15b_opened"])
        self.assertTrue(first["phase_15c_opened"])
        self.assertFalse(first["phase_15d_opened"])
        self.assertEqual(len(first["audits"]), 15)

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
                self.assertFalse(audit["passed"])
                self.assertEqual(audit["status"], "internal-error")

    def test_promotion_mode_requires_predecessor_authentication(self) -> None:
        def safe(name, _function, *_args, **_kwargs):
            passed = name != "phase15b-predecessor-authentication"
            return {
                "audit": name,
                "passed": passed,
                "errors": [] if passed else ["predecessor absent"],
            }

        with patch.object(validator, "_safe_audit", side_effect=safe):
            report = validator.run_validation(
                root=ROOT,
                mode="promotion",
                search_predecessor=False,
            )

        self.assertFalse(report["passed"])
        self.assertFalse(report["phase_15c_gate_eligible"])
        self.assertFalse(report["promotion_eligible"])

    def test_json_rendering_is_canonical_and_newline_terminated(self) -> None:
        value = {"z": False, "a": [2, 1]}
        self.assertEqual(
            validator._json_bytes(value),
            b'{"a":[2,1],"z":false}\n',
        )


if __name__ == "__main__":
    unittest.main()
