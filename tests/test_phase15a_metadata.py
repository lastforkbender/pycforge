from __future__ import annotations

import json
from pathlib import Path
import tomllib
import unittest

from pycforge import __version__
from pycforge.converter.contracts.versions import CONVERTER_CONTRACT_VERSION
from pycforge.ide import WORKSPACE_CONTRACT_VERSION
from pycforge.ide.worker_protocol import PROTOCOL_SCHEMA
from tools.build_phase15a_release import (
    CONVERTER_CUSTODY_DOMAIN,
    CONVERTER_SUBTREE_SHA256,
    release_subtree_hash,
)
from tools.validate_phase15a import scan_runtime_boundaries


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "transition" / "phase_15a"
EVIDENCE = ROOT / "evidence" / "phase_15a"


class Phase15AMetadataTests(unittest.TestCase):
    def test_active_package_workspace_protocol_and_converter_identities(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(project["project"]["version"], "0.15.2")
        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(CONVERTER_CONTRACT_VERSION, "0.14.3")
        self.assertEqual(WORKSPACE_CONTRACT_VERSION, "pycforge-workspace/0.5")
        self.assertEqual(PROTOCOL_SCHEMA, "pycforge.worker-protocol/0.1")

    def test_current_docs_name_phase15c_and_preserve_transpiler_boundary(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        current = (ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
        for text in (readme, current):
            self.assertIn("PyCForge", text)
            self.assertIn("Phase 15A", text)
            self.assertIn("source transpiler", text)
            self.assertIn("pycforge.worker-protocol/0.1", text)
        self.assertIn("0.15.2", readme)
        self.assertIn("pycforge-workspace/0.5", readme)
        self.assertIn("pycforge.action-registry/0.2", readme)
        self.assertIn("pycforge.visual-system/0.2", readme)
        self.assertIn("Phase 15B", readme)
        self.assertIn("Phase 15C", readme)
        self.assertIn("Phase 15D", readme)
        self.assertIn("unopened", readme.casefold())

    def test_transition_and_evidence_inventory_is_complete(self) -> None:
        required = (
            PHASE / "entry_criteria.md",
            PHASE / "responsiveness_and_isolation_decision.md",
            PHASE / "rollback_conditions.md",
            PHASE / "gate_evidence.md",
            PHASE / "manifest.json",
            PHASE / "release_fingerprint.json",
            EVIDENCE / "validation_report.json",
            EVIDENCE / "performance_evidence.json",
            EVIDENCE / "release_report.json",
            ROOT / "PyCForge_Phase_15A_v0_15_0_Project_Handoff.txt",
            ROOT / "tools" / "validate_phase15a.py",
            ROOT / "tools" / "build_phase15a_release.py",
        )
        missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
        self.assertEqual(missing, [])

    def test_manifest_is_exactly_phase15a_and_platform_honest(self) -> None:
        manifest = json.loads((PHASE / "manifest.json").read_bytes())
        self.assertEqual(
            manifest["schema"],
            "pycforge.phase15a-manifest/0.15.0",
        )
        self.assertEqual(manifest["tests"]["discovered"], 670)
        self.assertEqual(manifest["tests"]["passed"], 652)
        self.assertEqual(manifest["tests"]["skipped"], 18)
        self.assertEqual(manifest["tests"]["failed"], 0)
        self.assertTrue(manifest["promotion"]["phase_15a_promoted"])
        self.assertFalse(manifest["platform_evidence"]["visible_pyqt"])
        self.assertEqual(manifest["phase_15b"]["status"], "not-opened")
        self.assertEqual(manifest["phase_15c"]["status"], "not-opened")
        self.assertEqual(manifest["phase_15d"]["status"], "not-opened")

    def test_converter_subtree_is_byte_frozen(self) -> None:
        digest, count = release_subtree_hash(
            ROOT,
            "pycforge/converter",
            domain=CONVERTER_CUSTODY_DOMAIN,
        )
        self.assertEqual(digest, CONVERTER_SUBTREE_SHA256)
        self.assertEqual(count, 92)

    def test_active_ide_modules_and_runtime_authority_are_bounded(self) -> None:
        modules = tuple((ROOT / "pycforge" / "ide").glob("*.py"))
        self.assertTrue(modules)
        for path in modules:
            with self.subTest(path=path.name):
                self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 1000)
        new_helpers = (
            "_worker_protocol_types.py",
            "_worker_protocol_json.py",
            "_worker_request_data.py",
            "_worker_request_codec.py",
            "_worker_result_data.py",
            "_worker_event_codec.py",
            "controller_conversion.py",
            "controller_io.py",
            "editor_lexical.py",
            "editor_sidebars.py",
            "editor_syntax.py",
            "io_service.py",
            "positions.py",
            "process_worker.py",
            "qt_close.py",
            "qt_contract.py",
            "qt_documents.py",
            "qt_projection.py",
            "qt_shell.py",
            "qt_state.py",
            "revisions.py",
            "search_service.py",
            "supervisor.py",
            "worker_protocol.py",
        )
        for name in new_helpers:
            path = ROOT / "pycforge" / "ide" / name
            with self.subTest(helper=name):
                self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 600)
        audit = scan_runtime_boundaries(ROOT)
        self.assertTrue(audit["passed"], audit["errors"])


if __name__ == "__main__":
    unittest.main()
