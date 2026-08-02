from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tools.smoke_pycforge_workspace_0_12_2 import (  # noqa: E402
    GENERATED_C_OPERATIONS,
    RELEASE_VERSION,
    REQUIRED_CHECKS,
    RUNTIME_FIELDS,
    SAFETY_STATEMENT,
    SCHEMA_VERSION,
    WORKSPACE_CONTRACT,
    build_report,
    main,
    render_report,
    run_widget_smoke,
)


ROOT = Path(__file__).resolve().parents[1]
PYQT5_AVAILABLE = importlib.util.find_spec("PyQt5") is not None


class PyCForgeWidgetSmokeReportTests(unittest.TestCase):
    def complete_checks(self) -> dict[str, bool]:
        return {name: True for name in REQUIRED_CHECKS}

    def runtime(self) -> dict[str, object]:
        return {
            "pyqt_version": "5.15.11",
            "qt_version": "5.15.14",
            "platform": "offscreen",
            "device_pixel_ratio": 1.0,
            "logical_dpi": 96.0,
            "logical_scale_factor": 1.0,
            "qt_scale_factor": "automatic",
        }

    def test_report_contract_is_closed_complete_and_explicitly_non_executing(self) -> None:
        report = build_report(runtime=self.runtime(), checks=self.complete_checks())

        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["release_version"], RELEASE_VERSION)
        self.assertEqual(report["workspace_contract"], WORKSPACE_CONTRACT)
        self.assertEqual(tuple(report["runtime"]), RUNTIME_FIELDS)
        self.assertEqual(tuple(report["checks"]), REQUIRED_CHECKS)
        self.assertEqual(report["generated_c_operations"], GENERATED_C_OPERATIONS)
        self.assertEqual(
            report["generated_c_safety_statement"],
            SAFETY_STATEMENT,
        )
        self.assertEqual(
            SAFETY_STATEMENT,
            "Generated C was not compiled, linked, loaded, or executed.",
        )
        self.assertTrue(report["passed"])

    def test_missing_or_failed_checks_cannot_produce_a_passing_report(self) -> None:
        missing = build_report(runtime=self.runtime(), checks={})
        self.assertFalse(missing["passed"])
        self.assertEqual(set(missing["checks"]), set(REQUIRED_CHECKS))
        self.assertFalse(any(missing["checks"].values()))

        failed_checks = self.complete_checks()
        failed_checks["atomic_linked_c_save"] = False
        failed = build_report(runtime=self.runtime(), checks=failed_checks)
        self.assertFalse(failed["passed"])

        errored = build_report(
            runtime=self.runtime(),
            checks=self.complete_checks(),
            error="PyQt5 is required",
        )
        self.assertFalse(errored["passed"])

    def test_screenshot_is_an_optional_but_enforced_report_check(self) -> None:
        without = build_report(
            runtime=self.runtime(),
            checks=self.complete_checks(),
        )
        self.assertNotIn("screenshot_written", without["checks"])
        self.assertTrue(without["passed"])

        requested = build_report(
            runtime=self.runtime(),
            checks=self.complete_checks(),
            screenshot_requested=True,
        )
        self.assertIn("screenshot_written", requested["checks"])
        self.assertFalse(requested["passed"])

        successful = self.complete_checks()
        successful["screenshot_written"] = True
        requested = build_report(
            runtime=self.runtime(),
            checks=successful,
            screenshot_requested=True,
        )
        self.assertTrue(requested["passed"])

    def test_json_rendering_is_deterministic_and_newline_terminated(self) -> None:
        report = build_report(runtime=self.runtime(), checks=self.complete_checks())
        first = render_report(report)
        second = render_report(report)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertEqual(json.loads(first), report)
        key_lines = [
            line.strip()
            for line in first.splitlines()
            if line.startswith('  "')
        ]
        self.assertEqual(key_lines, sorted(key_lines))

    def test_cli_atomically_writes_exactly_the_printed_report(self) -> None:
        report = build_report(runtime=self.runtime(), checks=self.complete_checks())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "report.json"
            stdout = StringIO()
            with patch(
                "tools.smoke_pycforge_workspace_0_12_2.run_widget_smoke",
                return_value=report,
            ), redirect_stdout(stdout):
                status = main(["--output", str(output)])
            self.assertEqual(status, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), stdout.getvalue())
            self.assertEqual(json.loads(stdout.getvalue()), report)
            self.assertFalse(tuple(output.parent.glob(".report.json.*.tmp")))

    def test_cli_returns_nonzero_when_any_check_fails(self) -> None:
        checks = self.complete_checks()
        checks["mapping_navigation"] = False
        report = build_report(runtime=self.runtime(), checks=checks)
        stdout = StringIO()
        with patch(
            "tools.smoke_pycforge_workspace_0_12_2.run_widget_smoke",
            return_value=report,
        ), redirect_stdout(stdout):
            status = main([])
        self.assertEqual(status, 2)
        self.assertFalse(json.loads(stdout.getvalue())["passed"])

    @unittest.skipIf(PYQT5_AVAILABLE, "PyQt5 is installed in this environment")
    def test_missing_pyqt5_fails_honestly_with_structured_json(self) -> None:
        report = run_widget_smoke()
        self.assertFalse(report["passed"])
        self.assertIn("PyQt5 is required", report["error"])
        self.assertFalse(any(report["generated_c_operations"].values()))


@unittest.skipUnless(PYQT5_AVAILABLE, "real PyQt5 widgets are unavailable")
class PyCForgeActualWidgetSmokeTests(unittest.TestCase):
    def test_actual_offscreen_runner_writes_report_and_optional_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "widget-smoke.json"
            screenshot_path = root / "widget-smoke.png"
            environment = dict(os.environ)
            environment["QT_QPA_PLATFORM"] = "offscreen"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/smoke_pycforge_workspace_0_12_2.py"),
                    "--output",
                    str(report_path),
                    "--screenshot",
                    str(screenshot_path),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
            self.assertNotIn("Traceback (most recent call last)", completed.stderr)
            self.assertEqual(completed.returncode, 0, completed.stdout)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(completed.stdout), report)
            self.assertTrue(report["passed"])
            self.assertEqual(report["runtime"]["platform"], "offscreen")
            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(report["generated_c_operations"], GENERATED_C_OPERATIONS)
            self.assertTrue(screenshot_path.is_file())
            self.assertGreater(screenshot_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
