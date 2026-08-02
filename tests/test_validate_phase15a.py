from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import tools.validate_phase15a as validator


ROOT = Path(__file__).resolve().parents[1]


class _CapturedStdout:
    def __init__(self) -> None:
        self.buffer = BytesIO()


def _minimal_runtime_tree(root: Path) -> None:
    converter = root / "pycforge" / "converter"
    ide = root / "pycforge" / "ide"
    converter.mkdir(parents=True)
    ide.mkdir(parents=True)
    (converter / "__init__.py").write_text("", encoding="utf-8")
    (ide / "process_worker.py").write_text(
        "from pycforge.converter.facade import PythonToCConverter\n",
        encoding="utf-8",
    )
    (ide / "_worker_protocol_types.py").write_text(
        "class ByteConnection:\n"
        "    def send_bytes(self, buffer): ...\n"
        "    def recv_bytes(self, maxlength=None): ...\n"
        "    def close(self): ...\n",
        encoding="utf-8",
    )
    (ide / "transport.py").write_text(
        "def frames(connection, payload):\n"
        "    connection.send_bytes(payload)\n"
        "    connection.send_bytes(payload)\n"
        "    return connection.recv_bytes(100)\n",
        encoding="utf-8",
    )


class Phase15AValidatorTests(unittest.TestCase):
    def test_exact_phase_contracts_and_custody_constants_are_literal(self) -> None:
        self.assertEqual(
            validator.VALIDATION_SCHEMA,
            "pycforge.phase15a-validation-report/1",
        )
        self.assertEqual(validator.EXPECTED_PACKAGE_VERSION, "0.15.0")
        self.assertEqual(validator.EXPECTED_CONVERTER_CONTRACT, "0.14.3")
        self.assertEqual(
            validator.EXPECTED_WORKSPACE_CONTRACT,
            "pycforge-workspace/0.3",
        )
        self.assertEqual(
            validator.EXPECTED_WORKER_PROTOCOL,
            "pycforge.worker-protocol/0.1",
        )
        self.assertEqual(
            validator.EXPECTED_CONVERTER_SUBTREE_SHA256,
            "a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124",
        )
        self.assertFalse(validator.TOOLCHAIN_INVOKED)
        self.assertFalse(validator.GENERATED_C_EXECUTED)

    def test_successor_identities_fail_closed_while_converter_subtree_passes(self) -> None:
        identities = validator.audit_contract_identities(ROOT)
        subtree = validator.audit_frozen_converter_subtree(ROOT)

        self.assertFalse(identities["passed"])
        self.assertEqual(
            identities["errors"],
            [
                "project_package identity is '0.15.2', expected '0.15.0'",
                "module_package identity is '0.15.2', expected '0.15.0'",
                (
                    "workspace identity is 'pycforge-workspace/0.5', "
                    "expected 'pycforge-workspace/0.3'"
                ),
            ],
        )
        self.assertTrue(subtree["passed"], subtree["errors"])
        self.assertEqual(subtree["actual_sha256"], subtree["expected_sha256"])
        self.assertEqual(subtree["file_count"], 92)

    def test_converter_hash_changes_on_one_byte_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "pycforge" / "converter"
            shutil.copytree(ROOT / "pycforge" / "converter", destination)
            target = destination / "__init__.py"
            target.write_bytes(target.read_bytes() + b"\n# tampered\n")

            digest, count = validator.canonical_converter_subtree_hash(root)

        self.assertEqual(count, 92)
        self.assertNotEqual(
            digest,
            validator.EXPECTED_CONVERTER_SUBTREE_SHA256,
        )

    def test_current_runtime_is_byte_only_process_isolated_and_toolchain_free(
        self,
    ) -> None:
        audit = validator.scan_runtime_boundaries(ROOT)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(
            audit["converter_facade_authorities"],
            ["pycforge/ide/process_worker.py"],
        )
        self.assertEqual(
            audit["byte_connection_methods"],
            ["close", "recv_bytes", "send_bytes"],
        )
        self.assertGreaterEqual(audit["byte_transport_call_sites"], 3)
        self.assertFalse(audit["pickle_transport_allowed"])
        self.assertFalse(audit["gui_in_process_conversion_allowed"])

    def test_runtime_scan_rejects_gui_conversion_pickle_object_ipc_and_toolchain(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _minimal_runtime_tree(root)
            ide = root / "pycforge" / "ide"
            (ide / "gui_bad.py").write_text(
                "from pycforge.converter.facade import PythonToCConverter\n"
                "def convert_here():\n"
                "    return PythonToCConverter().convert('source')\n",
                encoding="utf-8",
            )
            (ide / "transport_bad.py").write_text(
                "import pickle\n"
                "import subprocess\n"
                "from multiprocessing import Queue\n"
                "def unsafe(connection):\n"
                "    connection.send({'object': True})\n"
                "    subprocess.run(['gcc', 'generated.c'])\n"
                "    Queue()\n"
                "    return eval('1')\n",
                encoding="utf-8",
            )

            audit = validator.scan_runtime_boundaries(root)

        joined = "\n".join(audit["errors"])
        self.assertFalse(audit["passed"])
        for text in (
            "GUI-side converter facade import",
            "GUI-side in-process convert call",
            "forbidden runtime import pickle",
            "forbidden runtime import subprocess",
            "object Connection.send is forbidden",
            "object IPC Queue is forbidden",
            "compiler/toolchain token 'gcc'",
            "forbidden dynamic call eval",
        ):
            with self.subTest(text=text):
                self.assertIn(text, joined)

    def test_optional_predecessor_absence_is_honest_and_required_absence_fails(
        self,
    ) -> None:
        optional = validator.audit_predecessor_archive(None, required=False)
        required = validator.audit_predecessor_archive(None, required=True)

        self.assertTrue(optional["passed"])
        self.assertEqual(optional["status"], "not-present-optional")
        self.assertFalse(optional["archive_authenticated"])
        self.assertFalse(required["passed"])
        self.assertEqual(required["status"], "missing-required")

    def test_explicit_tampered_predecessor_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / validator.PREDECESSOR_ARCHIVE_NAME
            archive.write_bytes(b"not the sealed archive")
            audit = validator.audit_predecessor_archive(
                archive,
                required=True,
            )

        self.assertFalse(audit["passed"])
        self.assertFalse(audit["archive_authenticated"])
        self.assertIn("size mismatch", "\n".join(audit["errors"]))
        self.assertIn("SHA-256 mismatch", "\n".join(audit["errors"]))

    def test_available_sealed_predecessor_authenticates_without_extraction(
        self,
    ) -> None:
        archive = validator.locate_predecessor_archive(ROOT)
        if archive is None:
            self.skipTest("optional sealed Checkpoint E archive is unavailable")

        audit = validator.audit_predecessor_archive(archive, required=True)

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertTrue(audit["archive_authenticated"])
        self.assertFalse(audit["archive_extracted"])
        self.assertEqual(
            audit["converter_subtree_sha256"],
            validator.EXPECTED_CONVERTER_SUBTREE_SHA256,
        )

    def test_direct_and_isolated_facades_are_exactly_equivalent(self) -> None:
        audit = validator.audit_direct_isolated_equivalence()

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(len(audit["cases"]), 2)
        self.assertTrue(all(case["equivalent"] for case in audit["cases"]))
        self.assertFalse(audit["generated_c_executed"])

    def test_maximum_fixtures_are_measured_bounded_and_off_caller_thread(
        self,
    ) -> None:
        audit = validator.audit_maximum_input_fixtures()

        self.assertTrue(audit["passed"], audit["errors"])
        fixtures = audit["fixtures"]
        self.assertEqual(
            fixtures["simultaneous_valid_syntax"]["source_lines"],
            100_000,
        )
        self.assertEqual(
            fixtures["simultaneous_valid_syntax"]["utf8_bytes"],
            999_999,
        )
        self.assertGreaterEqual(
            fixtures["near_token_ceiling"]["tokens"],
            249_900,
        )
        self.assertGreaterEqual(
            fixtures["near_ast_ceiling"]["ast_nodes"],
            99_900,
        )
        self.assertTrue(
            fixtures["exact_byte_ceiling"]["oversized_rejected"]
        )
        self.assertTrue(audit["revision_index_off_caller_thread"])
        self.assertEqual(audit["dense_search"]["utf8_bytes"], 950_000)
        self.assertEqual(audit["dense_search"]["total_matches"], 50_000)
        self.assertEqual(audit["dense_search"]["stored_ranges"], 5_000)
        self.assertLess(
            audit["measurements_seconds"]["revision_submit"],
            0.100,
        )
        self.assertLess(
            audit["measurements_seconds"]["dense_search_submit"],
            0.100,
        )
        self.assertFalse(audit["gui_event_loop_measured"])
        self.assertFalse(audit["visible_ui_measured"])

    def test_hundred_cycle_gate_reaps_every_started_worker(self) -> None:
        audit = validator.audit_hundred_cycle_supervision()

        self.assertTrue(audit["passed"], audit["errors"])
        self.assertEqual(audit["submitted_cycles"], 100)
        self.assertEqual(audit["canceled_cycles"], 100)
        self.assertEqual(audit["active_worker_cancel_cycles"], 10)
        self.assertGreaterEqual(audit["started_workers"], 10)
        self.assertEqual(audit["started_workers"], audit["reaped_workers"])
        self.assertEqual(audit["maximum_simultaneous_workers"], 1)
        self.assertIsNone(audit["active_pid_after_gate"])
        self.assertIsNone(audit["pending_generation_after_gate"])

    def test_quick_mode_is_deterministic_but_never_promotion_eligible(self) -> None:
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
        self.assertFalse(first["passed"])
        self.assertFalse(first["promotion_eligible"])
        identity_audit = first["audits"][0]
        self.assertEqual(
            identity_audit["errors"],
            [
                "project_package identity is '0.15.2', expected '0.15.0'",
                "module_package identity is '0.15.2', expected '0.15.0'",
                (
                    "workspace identity is 'pycforge-workspace/0.5', "
                    "expected 'pycforge-workspace/0.3'"
                ),
            ],
        )
        skipped = [
            audit
            for audit in first["audits"]
            if audit.get("status") == "skipped-by-mode"
        ]
        self.assertEqual(len(skipped), 3)

    def test_full_mode_promotion_flag_requires_every_full_audit(self) -> None:
        passed = {
            "audit": "stub",
            "passed": True,
            "errors": [],
        }
        with (
            patch.object(validator, "audit_contract_identities", return_value=passed),
            patch.object(
                validator,
                "audit_frozen_converter_subtree",
                return_value=passed,
            ),
            patch.object(
                validator,
                "audit_predecessor_archive",
                return_value=passed,
            ),
            patch.object(validator, "scan_runtime_boundaries", return_value=passed),
            patch.object(
                validator,
                "audit_direct_isolated_equivalence",
                return_value=passed,
            ),
            patch.object(
                validator,
                "audit_maximum_input_fixtures",
                return_value=passed,
            ),
            patch.object(
                validator,
                "audit_hundred_cycle_supervision",
                return_value=passed,
            ),
            patch.object(validator, "audit_platform_scope", return_value=passed),
            patch.object(validator, "audit_safety_scope", return_value=passed),
        ):
            report = validator.run_validation(
                root=ROOT,
                mode="full",
                search_predecessor=False,
            )
            canonical = validator.run_validation(
                root=ROOT,
                mode="promotion",
                search_predecessor=False,
            )

        self.assertEqual(report, canonical)
        self.assertEqual(report["mode"], "promotion")
        self.assertTrue(report["passed"])
        self.assertTrue(report["promotion_eligible"])
        self.assertTrue(report["phase_15a_gate_eligible"])
        self.assertFalse(report["visible_ui_promotion_eligible"])
        self.assertFalse(report["distribution_promotion_eligible"])

    def test_validator_modules_obey_release_custody_size_bounds(self) -> None:
        public = ROOT / "tools" / "validate_phase15a.py"
        helper = ROOT / "tools" / "_phase15a_runtime_validation.py"

        self.assertLess(len(public.read_text(encoding="utf-8").splitlines()), 1_000)
        self.assertLess(len(helper.read_text(encoding="utf-8").splitlines()), 600)

    def test_unexpected_audit_exception_becomes_structured_failure(self) -> None:
        with patch.object(
            validator,
            "audit_contract_identities",
            side_effect=RuntimeError("injected audit failure"),
        ):
            report = validator.run_validation(
                root=ROOT,
                mode="quick",
                search_predecessor=False,
            )

        self.assertFalse(report["passed"])
        self.assertFalse(report["promotion_eligible"])
        failed = report["audits"][0]
        self.assertEqual(failed["status"], "internal-error")
        self.assertIn("injected audit failure", failed["errors"][0])

    def test_platform_and_safety_scope_make_no_unearned_claim(self) -> None:
        platform = validator.audit_platform_scope()
        safety = validator.audit_safety_scope()

        self.assertTrue(platform["passed"])
        self.assertFalse(platform["real_pyqt_widgets_exercised"])
        self.assertFalse(platform["visible_windows_11_exercised"])
        self.assertFalse(platform["visible_linux_desktop_exercised"])
        self.assertFalse(platform["distribution_install_exercised"])
        self.assertTrue(platform["phase_15d_platform_gate_required"])
        self.assertTrue(safety["passed"])
        self.assertFalse(safety["toolchain_invoked"])
        self.assertFalse(safety["generated_c_executed"])

    def test_cli_emits_one_canonical_failure_for_the_successor_tree(self) -> None:
        captured = _CapturedStdout()
        with patch.object(validator.sys, "stdout", captured):
            exit_code = validator.main(
                [
                    "--mode",
                    "quick",
                    "--root",
                    str(ROOT),
                    "--no-predecessor-search",
                ]
            )

        payload = captured.buffer.getvalue()
        report = json.loads(payload)
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["schema"], validator.VALIDATION_SCHEMA)
        self.assertFalse(report["passed"])
        self.assertEqual(payload, validator._json_bytes(report))
        self.assertTrue(payload.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
