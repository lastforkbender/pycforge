from __future__ import annotations

import tempfile
import tarfile
import unittest
from pathlib import Path

from pycforge import __version__
from tools.validate_pycforge_workspace_0_12_2 import (
    EXPECTED_ACTION_LABELS,
    EXPECTED_CONTRACT_IDENTITIES,
    EXPECTED_ICON_FILES,
    RELEASE_VERSION,
    WORKSPACE_CONTRACT,
    canonical_archive_tree_hash,
    canonical_subtree_hash,
    check_action_surface,
    check_exact_mapping,
    check_execution_boundary,
    check_resource_inventory,
    check_version_metadata,
    current_contract_identities,
    extract_action_labels,
    validate_tree,
)


ROOT = Path(__file__).resolve().parents[1]
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'


class PyCForgeValidatorPureTests(unittest.TestCase):
    def test_exact_contract_comparison_is_closed_and_deterministic(self) -> None:
        self.assertEqual(
            check_exact_mapping(
                EXPECTED_CONTRACT_IDENTITIES,
                EXPECTED_CONTRACT_IDENTITIES,
                label="contracts",
            ),
            (),
        )
        actual = current_contract_identities()
        active_errors = check_exact_mapping(
            actual,
            EXPECTED_CONTRACT_IDENTITIES,
            label="contracts",
        )
        self.assertEqual(active_errors, tuple(sorted(active_errors)))
        self.assertTrue(any("c_ir" in item and "0.14" in item for item in active_errors))
        changed = dict(actual)
        changed["unexpected"] = True
        errors = check_exact_mapping(
            changed,
            EXPECTED_CONTRACT_IDENTITIES,
            label="contracts",
        )
        self.assertEqual(errors, tuple(sorted(errors)))
        self.assertTrue(any("c_ir" in item and "0.14" in item for item in errors))
        self.assertTrue(any("unexpected key 'unexpected'" in item for item in errors))

    def test_action_surface_rejects_added_execution_controls(self) -> None:
        source = "def actions(self):\n" + "".join(
            f"    self._action({label!r}, 'icon', callback)\n"
            for label in sorted(EXPECTED_ACTION_LABELS)
        )
        self.assertEqual(set(extract_action_labels(source)), EXPECTED_ACTION_LABELS)
        self.assertEqual(check_action_surface(source), ())

        errors = check_action_surface(
            source + "    self._action('Run', 'icon', callback)\n"
        )
        self.assertTrue(any("unexpected key 'Run'" in item for item in errors))
        self.assertTrue(any("forbidden execution control 'run'" in item for item in errors))

    def test_execution_boundary_rejects_process_and_dynamic_execution(self) -> None:
        safe = {"safe.py": "from pathlib import Path\ndef show():\n    return Path('x')\n"}
        self.assertEqual(check_execution_boundary(safe), ())
        unsafe = {
            "process.py": "import subprocess\nsubprocess.run(['cc'])\n",
            "dynamic.py": "def f(text):\n    return eval(text)\n",
            "qt.py": "from PyQt5.QtCore import QProcess\n",
        }
        errors = check_execution_boundary(unsafe)
        self.assertTrue(any("subprocess" in item for item in errors))
        self.assertTrue(any("eval" in item for item in errors))
        self.assertTrue(any("QProcess" in item for item in errors))

    def test_resource_inventory_is_vector_only_and_closed(self) -> None:
        resources = {f"icons/{name}": SVG for name in EXPECTED_ICON_FILES}
        self.assertEqual(check_resource_inventory(resources), ())

        raster = dict(resources)
        raster["splash.png"] = b"not-a-real-image"
        self.assertTrue(
            any("forbidden raster asset" in item for item in check_resource_inventory(raster))
        )
        embedded = dict(resources)
        embedded["icons/open.svg"] = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            b'<image href="data:image/png;base64,AAAA"/></svg>'
        )
        errors = check_resource_inventory(embedded)
        self.assertTrue(any("forbidden SVG element 'image'" in item for item in errors))
        self.assertTrue(any("raster" in item or "asset reference" in item for item in errors))

    def test_version_metadata_check_detects_independent_drift(self) -> None:
        values = {
            "imported_version": RELEASE_VERSION,
            "pyproject_version": RELEASE_VERSION,
            "package_metadata": f"Metadata-Version: 2.1\nVersion: {RELEASE_VERSION}\n",
            "readme": "# PyCForge 0.12.2 — Phase 12 PyCForge Workspace\n",
            "current_state": (
                "Current release: `0.12.2` / Phase 12 PyCForge workspace\n"
                f"`{WORKSPACE_CONTRACT}`\n"
            ),
            "workspace_spec": (
                f"# PyCForge Workspace — `{WORKSPACE_CONTRACT}`\n"
                "Status: active in PyCForge 0.12.2\n"
            ),
        }
        self.assertEqual(check_version_metadata(**values), ())
        values["pyproject_version"] = "0.12.0"
        self.assertEqual(
            check_version_metadata(**values),
            ("pyproject version is '0.12.0'",),
        )

    def test_subtree_hash_uses_relative_paths_and_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            for root in (first, second):
                (root / "nested").mkdir()
                (root / "a.py").write_text("alpha", encoding="utf-8")
                (root / "nested/b.py").write_text("beta", encoding="utf-8")
                (root / "__pycache__").mkdir()
                (root / "__pycache__/ignored.pyc").write_bytes(b"nondeterministic")
            self.assertEqual(canonical_subtree_hash(first), canonical_subtree_hash(second))
            (second / "nested/b.py").write_text("changed", encoding="utf-8")
            self.assertNotEqual(canonical_subtree_hash(first), canonical_subtree_hash(second))

    def test_archive_tree_hash_matches_extracted_release_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            root.mkdir()
            (root / "nested").mkdir()
            (root / "a.py").write_text("alpha", encoding="utf-8")
            (root / "nested/b.py").write_text("beta", encoding="utf-8")
            archive = Path(directory) / "release.tar.gz"
            with tarfile.open(archive, mode="w:gz") as package:
                package.add(root, arcname="release")
            self.assertEqual(
                canonical_archive_tree_hash(archive),
                canonical_subtree_hash(root),
            )

    def test_sealed_0122_validator_refuses_the_active_phase14_tree(self) -> None:
        errors = validate_tree(ROOT, converter_smoke=False)
        self.assertEqual(errors, validate_tree(ROOT, converter_smoke=False))
        self.assertTrue(any(__version__ in item for item in errors))
        self.assertTrue(any("contract" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
