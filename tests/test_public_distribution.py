from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from pycforge.laboratory import cli
import tools.verify_public_distribution as distribution_verifier


ROOT = Path(__file__).resolve().parents[1]


class PublicDistributionTests(unittest.TestCase):
    def test_pyqt5_is_a_required_base_dependency(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["dependencies"], ["PyQt5>=5.15.11,<6"])
        self.assertNotIn("optional-dependencies", project)
        self.assertEqual(project["license"], "GPL-3.0-only")
        self.assertEqual(project["license-files"], ["LICENSE"])

    def test_desktop_entry_point_is_a_gui_script(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(
            project["gui-scripts"],
            {"pycforge-workspace": "pycforge.ide.qt:run"},
        )
        self.assertEqual(
            project["scripts"],
            {"pycforge": "pycforge.laboratory.cli:main"},
        )

    def test_readme_install_and_cli_examples_match_the_parser(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python -m pip install pycforge", readme)
        self.assertIn("pycforge-workspace", readme)
        self.assertIn("PyQt5 and the desktop application as required", readme)
        self.assertIn("pycforge convert input.py --output generated.c", readme)
        self.assertIn("pycforge --format json convert input.py", readme)
        self.assertNotIn(".[workspace]", readme)
        self.assertNotIn("optional desktop", readme.lower())
        distribution_verifier._verify_public_readme(readme.encode("utf-8"))
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["convert", "input.py"]).command, "convert")
        self.assertEqual(
            parser.parse_args(["--format", "json", "convert", "input.py"]).format,
            "json",
        )

    def test_repository_only_commands_are_hidden_from_an_installed_wheel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(cli, "ROOT", Path(directory)):
                parser = cli.build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        self.assertEqual(
            set(subparsers.choices),
            {"convert", "inspect", "validate", "diff"},
        )

    def test_public_sdist_manifest_excludes_repository_evidence(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for value in (
            "docs",
            "evidence",
            "fixtures",
            "schemas",
            "specifications",
            "tests",
            "tools",
            "transition",
        ):
            self.assertNotIn(f"recursive-include {value}", manifest)
            self.assertIn(f"prune {value}", manifest)
        self.assertIn("exclude PyCForge_*.txt", manifest)
        self.assertIn("include LICENSE", manifest)
        self.assertIn("include RELEASE_NOTES.md", manifest)

    def test_distribution_directory_is_a_closed_two_file_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "pycforge-0.15.2-py3-none-any.whl"
            sdist = root / "pycforge-0.15.2.tar.gz"
            wheel.write_bytes(b"wheel")
            sdist.write_bytes(b"sdist")
            with (
                patch.object(
                    distribution_verifier, "verify_wheel", return_value={}
                ),
                patch.object(
                    distribution_verifier, "verify_sdist", return_value={}
                ),
            ):
                distribution_verifier.verify_directory(root)
                (root / "unexpected.txt").write_bytes(b"unexpected")
                with self.assertRaises(
                    distribution_verifier.DistributionVerificationError
                ):
                    distribution_verifier.verify_directory(root)

    def test_distribution_directory_rejects_a_non_exact_wheel_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pycforge-0.15.2-cp312-cp312-linux_x86_64.whl").write_bytes(
                b"wheel"
            )
            (root / "pycforge-0.15.2.tar.gz").write_bytes(b"sdist")
            with self.assertRaises(
                distribution_verifier.DistributionVerificationError
            ):
                distribution_verifier.verify_directory(root)

    def test_wheel_record_requires_exact_sha256_coverage(self) -> None:
        record_name = "pycforge-0.15.2.dist-info/RECORD"
        payload = b"release-payload"
        members = {
            "pycforge/__init__.py": payload,
            record_name: b"",
        }
        members[record_name] = (
            "pycforge/__init__.py,"
            + distribution_verifier._record_digest(payload)
            + f",{len(payload)}\n{record_name},,\n"
        ).encode("utf-8")
        distribution_verifier._verify_record(members, record_name)
        members[record_name] = members[record_name].replace(b"sha256=", b"sha256=x")
        with self.assertRaises(
            distribution_verifier.DistributionVerificationError
        ):
            distribution_verifier._verify_record(members, record_name)

    def test_release_workflow_tests_and_never_clobbers_assets(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -m pytest -q", workflow)
        self.assertIn("SOURCE_DATE_EPOCH", workflow)
        self.assertIn("tools/normalize_sdist.py", workflow)
        self.assertIn("cmp \"$release_file\"", workflow)
        self.assertNotIn("--clobber", workflow)


if __name__ == "__main__":
    unittest.main()
