from __future__ import annotations

import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        from PyQt5 import QtCore, QtWidgets
        from pycforge.ide.qt import MainWindow, QT_AVAILABLE
    except ModuleNotFoundError as exc:
        print(json.dumps({"passed": False, "error": f"missing dependency: {exc.name}"}))
        return 2
    if not QT_AVAILABLE:
        print(json.dumps({"passed": False, "error": "PyQt5 workspace unavailable"}))
        return 3

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        checks = {
            "python_editor_visible_by_default": not window.source.isHidden(),
            "generated_c_hidden_by_default": window.output.isHidden(),
            "generated_c_read_only": window.output.isReadOnly(),
            "details_hidden_by_default": window.tabs.isHidden(),
            "inline_progress_widget": isinstance(window.progress, QtWidgets.QProgressBar),
            "toggle_labels": (
                window.toggle_c_button.text() == "Show C"
                and window.toggle_details_button.text() == "Show Details"
            ),
        }

        source = (
            "def identity(value: int) -> int:\n"
            "    return value\n\n"
            "def use(value: int) -> int:\n"
            "    return identity(value)\n"
        )
        window.source.setPlainText(source)
        app.processEvents()
        window.convert()
        deadline = time.monotonic() + 10.0
        while window.controller.snapshot.state.value == "converting":
            app.processEvents(QtCore.QEventLoop.AllEvents, 25)
            if time.monotonic() >= deadline:
                checks["conversion_completed"] = False
                break
            time.sleep(0.005)
        for _ in range(10):
            app.processEvents(QtCore.QEventLoop.AllEvents, 25)
            time.sleep(0.002)
        checks["conversion_completed"] = (
            window.controller.snapshot.state.value == "converted"
            and window.controller.snapshot.generated_c is not None
            and "int64_t identity" in window.output.toPlainText()
        )
        checks["fast_progress_finished_hidden"] = window.progress.isHidden()
        checks["conversion_did_not_reveal_c"] = window.output.isHidden()

        retained = window.output.toPlainText()
        window.toggle_c_button.setChecked(True)
        window.toggle_details_button.setChecked(True)
        app.processEvents()
        checks["explicit_toggles_reveal_views"] = (
            not window.output.isHidden()
            and not window.tabs.isHidden()
            and window.toggle_c_button.text() == "Hide C"
            and window.toggle_details_button.text() == "Hide Details"
        )
        window.toggle_c_button.setChecked(False)
        window.toggle_details_button.setChecked(False)
        app.processEvents()
        checks["hiding_c_retains_output"] = (
            window.output.isHidden() and window.output.toPlainText() == retained
        )
        checks["non_modal"] = not any(
            isinstance(widget, QtWidgets.QDialog)
            for widget in app.topLevelWidgets()
            if widget is not window
        )

        passed = all(checks.values())
        report = {
            "schema_version": "pycforge.qt-smoke/0.10",
            "pyqt_version": QtCore.PYQT_VERSION_STR,
            "qt_version": QtCore.QT_VERSION_STR,
            "platform": QtWidgets.QApplication.platformName(),
            "checks": checks,
            "generated_c_compiled_or_executed": False,
            "passed": passed,
        }
        print(json.dumps(report, sort_keys=True, indent=2))
        return 0 if passed else 4
    finally:
        window.close()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
