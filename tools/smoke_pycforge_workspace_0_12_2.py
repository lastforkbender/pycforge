"""Actual-widget release smoke for the PyCForge 0.12.2 PyCForge workspace.

This runner deliberately exercises the optional PyQt5 surface in an offscreen
``QApplication``.  It converts source to C only through the frozen converter
facade.  It never compiles, links, loads, or executes the generated C.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge.converter.io.atomic_writer import AtomicWriter  # noqa: E402


RELEASE_VERSION = "0.12.2"
WORKSPACE_CONTRACT = "pycforge-workspace/0.1"
SCHEMA_VERSION = "pycforge.workspace-widget-smoke/0.12.2"
SAFETY_STATEMENT = (
    "Generated C was not compiled, linked, loaded, or executed."
)
GENERATED_C_OPERATIONS = {
    "compiled": False,
    "executed": False,
    "linked": False,
    "loaded": False,
}
RUNTIME_FIELDS = (
    "pyqt_version",
    "qt_version",
    "platform",
    "device_pixel_ratio",
    "logical_dpi",
    "logical_scale_factor",
    "qt_scale_factor",
)
REQUIRED_CHECKS = (
    "actual_qapplication_and_main_window",
    "offscreen_platform",
    "runtime_scale_reported",
    "default_workspace_and_read_only_c",
    "accessibility_metadata",
    "icon_only_controls_have_tooltips",
    "two_module_navigation",
    "bundle_reorder",
    "primary_document_selection",
    "ctrl_f_opens_find",
    "ctrl_h_opens_replace",
    "find_case_and_whole_word_modes",
    "emoji_replacement_navigation",
    "conversion_completed",
    "structured_details_projected",
    "mapping_navigation",
    "atomic_linked_c_save",
    "stale_output_blocks_save",
    "changed_back_source_blocks_save",
    "stale_recovery_conversion",
    "pending_identity_committed_before_save_c",
    "identity_change_blocks_save",
    "final_recovery_conversion_and_save",
    "responsive_splitter_layout",
    "toolbar_save_c_visible",
    "linked_destination_discoverable",
    "no_unexpected_modal_dialogs",
    "generated_c_not_compiled_linked_loaded_or_executed",
)


APP_SOURCE = (
    "from lib import increment\n\n"
    "# x X xylophone x\n"
    "def run(value: int) -> int:\n"
    "    return increment(value)\n"
)
LIB_SOURCE = (
    "def increment(value: int) -> int:\n"
    "    return value + 1\n"
)


def _empty_runtime() -> dict[str, object | None]:
    return {key: None for key in RUNTIME_FIELDS}


def build_report(
    *,
    runtime: Mapping[str, object] | None = None,
    checks: Mapping[str, object] | None = None,
    error: str | None = None,
    screenshot_requested: bool = False,
) -> dict[str, object]:
    """Build the closed, deterministic JSON-compatible report contract."""

    supplied_runtime = dict(runtime or {})
    normalized_runtime = {
        key: supplied_runtime.get(key)
        for key in RUNTIME_FIELDS
    }
    supplied_checks = dict(checks or {})
    normalized_checks = {
        key: bool(supplied_checks.get(key, False))
        for key in REQUIRED_CHECKS
    }
    if screenshot_requested:
        normalized_checks["screenshot_written"] = bool(
            supplied_checks.get("screenshot_written", False)
        )
    passed = bool(
        error is None
        and normalized_checks
        and all(normalized_checks.values())
        and not any(GENERATED_C_OPERATIONS.values())
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "release_version": RELEASE_VERSION,
        "workspace_contract": WORKSPACE_CONTRACT,
        "runtime": normalized_runtime,
        "checks": normalized_checks,
        "generated_c_operations": dict(GENERATED_C_OPERATIONS),
        "generated_c_safety_statement": SAFETY_STATEMENT,
        "screenshot_requested": bool(screenshot_requested),
        "error": error,
        "passed": passed,
    }


def render_report(report: Mapping[str, object]) -> str:
    """Serialize a report with stable key order, indentation, and newline."""

    return json.dumps(
        dict(report),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def _dependency_failure(error: str, *, screenshot_requested: bool) -> dict[str, object]:
    return build_report(
        runtime=_empty_runtime(),
        error=error,
        screenshot_requested=screenshot_requested,
    )


def _wait_until(app: Any, QtCore: Any, predicate: Any, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QtCore.QEventLoop.AllEvents, 25)
        if predicate():
            for _ in range(4):
                app.processEvents(QtCore.QEventLoop.AllEvents, 25)
            return True
        time.sleep(0.004)
    app.processEvents(QtCore.QEventLoop.AllEvents, 25)
    return bool(predicate())


def _pump(app: Any, QtCore: Any, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents(QtCore.QEventLoop.AllEvents, 25)


def _runtime_report(app: Any, window: Any, QtCore: Any) -> dict[str, object]:
    screen = window.screen() or app.primaryScreen()
    device_pixel_ratio = float(window.devicePixelRatioF())
    logical_dpi = float(screen.logicalDotsPerInch()) if screen is not None else 0.0
    return {
        "pyqt_version": str(QtCore.PYQT_VERSION_STR),
        "qt_version": str(QtCore.QT_VERSION_STR),
        "platform": str(app.platformName()),
        "device_pixel_ratio": round(device_pixel_ratio, 4),
        "logical_dpi": round(logical_dpi, 4),
        "logical_scale_factor": round(logical_dpi / 96.0, 4),
        "qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", "automatic"),
    }


def _set_identity(window: Any, app: Any, QtCore: Any, module_id: str, logical_name: str) -> None:
    window.navigator.module_edit.setText(module_id)
    window.navigator.logical_edit.setText(logical_name)
    window.navigator.logical_edit.editingFinished.emit()
    _pump(app, QtCore)


def _select_document_row(window: Any, app: Any, QtCore: Any, document_id: str) -> bool:
    from PyQt5.QtCore import Qt

    for row in range(window.navigator.documents.count()):
        item = window.navigator.documents.item(row)
        if str(item.data(Qt.UserRole)) == document_id:
            window.navigator.documents.setCurrentRow(row)
            _pump(app, QtCore)
            return True
    return False


def _convert_and_wait(window: Any, app: Any, QtCore: Any) -> bool:
    window.convert()
    completed = _wait_until(
        app,
        QtCore,
        lambda: window.controller.snapshot.state.value != "converting",
    )
    snapshot = window.controller.snapshot
    return bool(
        completed
        and snapshot.state.value
        in {"converted", "warning", "approximation", "observer-incomplete"}
        and snapshot.generated_c
        and snapshot.can_save_c
    )


def _save_c_and_wait(
    window: Any,
    destination: Path,
    app: Any,
    QtCore: Any,
) -> bool:
    expected = (window.controller.snapshot.generated_c or "").encode("utf-8")
    started = window.save_c()
    completed = _wait_until(
        app,
        QtCore,
        lambda: (
            destination.is_file()
            and destination.read_bytes() == expected
        ),
    )
    return bool(started and completed)


def _replace_editor_text(editor: Any, text: str) -> None:
    from PyQt5.QtGui import QTextCursor

    cursor = editor.textCursor()
    cursor.select(QTextCursor.Document)
    cursor.insertText(text)
    editor.setTextCursor(cursor)


def run_widget_smoke(screenshot: Path | str | None = None) -> dict[str, object]:
    """Run the real offscreen widget smoke and return its deterministic report."""

    screenshot_path = None if screenshot is None else Path(screenshot)
    screenshot_requested = screenshot_path is not None
    # This is an actual-widget smoke, not a static/headless substitute.  Force
    # the platform before importing any Qt module in the standalone process.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    try:
        from PyQt5 import QtCore, QtWidgets
        from PyQt5.QtCore import Qt
        from PyQt5.QtTest import QTest
        from pycforge.ide.qt import (
            MainWindow,
            QT_AVAILABLE,
            mapping_character_range,
            python_offset_to_qt_position,
        )
        from pycforge.ide.theme import apply_pycforge_theme
    except (ImportError, ModuleNotFoundError) as exc:
        name = getattr(exc, "name", None) or exc.__class__.__name__
        return _dependency_failure(
            f"PyQt5 is required for the actual-widget smoke; missing dependency: {name}",
            screenshot_requested=screenshot_requested,
        )

    if not QT_AVAILABLE:
        return _dependency_failure(
            "PyQt5 is required for the actual-widget smoke; workspace widgets are unavailable",
            screenshot_requested=screenshot_requested,
        )

    checks: dict[str, bool] = {
        "generated_c_not_compiled_linked_loaded_or_executed": True,
    }
    runtime = _empty_runtime()
    error: str | None = None
    app = None
    window = None
    dialog_observer = None

    with tempfile.TemporaryDirectory(prefix="pycforge-workspace-smoke-") as directory:
        temporary_root = Path(directory)
        runtime_root = temporary_root / "runtime"
        runtime_root.mkdir(mode=0o700)
        os.environ["XDG_RUNTIME_DIR"] = str(runtime_root)
        settings_root = temporary_root / "settings"
        settings_root.mkdir()
        # Keep the default/read-only-state checks independent of local user
        # settings.  Both formats are redirected because NativeFormat is an INI
        # backend on some platforms but not all.
        QtCore.QSettings.setPath(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            str(settings_root),
        )
        QtCore.QSettings.setPath(
            QtCore.QSettings.NativeFormat,
            QtCore.QSettings.UserScope,
            str(settings_root),
        )
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)

        if QtWidgets.QApplication.instance() is None:
            QtWidgets.QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QtWidgets.QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
            ["pycforge-workspace-0.12.2-widget-smoke"]
        )
        app.setApplicationName("PyCForge PyCForge Widget Smoke")
        app.setOrganizationName("PyCForge")
        apply_pycforge_theme(app)

        class _DialogObserver(QtCore.QObject):
            def __init__(self) -> None:
                super().__init__()
                self.shown: list[str] = []

            def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
                if (
                    event.type() == QtCore.QEvent.Show
                    and isinstance(watched, QtWidgets.QDialog)
                ):
                    self.shown.append(watched.windowTitle() or watched.objectName())
                return False

        dialog_observer = _DialogObserver()
        app.installEventFilter(dialog_observer)

        try:
            window = MainWindow()
            window.resize(1280, 800)
            window.show()
            _pump(app, QtCore, 8)
            runtime = _runtime_report(app, window, QtCore)

            checks["actual_qapplication_and_main_window"] = bool(
                isinstance(app, QtWidgets.QApplication)
                and isinstance(window, QtWidgets.QMainWindow)
                and window.metaObject().className() == "MainWindow"
            )
            checks["offscreen_platform"] = runtime["platform"] == "offscreen"
            checks["runtime_scale_reported"] = bool(
                isinstance(runtime["device_pixel_ratio"], float)
                and runtime["device_pixel_ratio"] > 0
                and isinstance(runtime["logical_dpi"], float)
                and runtime["logical_dpi"] > 0
                and isinstance(runtime["logical_scale_factor"], float)
                and runtime["logical_scale_factor"] > 0
            )
            checks["default_workspace_and_read_only_c"] = bool(
                window.source.isVisible()
                and window.output.isReadOnly()
                and not window.output_panel.isVisible()
                and not window.tabs.isVisible()
                and window.output.toPlainText() == ""
                and window.controller.snapshot.state.value == "empty"
            )

            named_widgets = (
                window.source,
                window.output,
                window.tabs,
                window.progress,
                window.navigator.documents,
                window.navigator.filter_edit,
                window.navigator.module_edit,
                window.navigator.logical_edit,
                window.navigator.primary_check,
                window.find_bar,
                window.find_bar.find_edit,
                window.find_bar.replace_edit,
                window.diags.tree,
                window.mappings.tree,
                window.summary.tree,
                window.trace.tree,
                window.telemetry.tree,
                window.source._quantum_rail,
                window.output._quantum_rail,
            )
            checks["accessibility_metadata"] = all(
                widget.accessibleName().strip() for widget in named_widgets
            ) and all(
                button.accessibleName().strip()
                for button in (
                    window.navigator.add_button,
                    window.navigator.remove_button,
                    window.navigator.move_up_button,
                    window.navigator.move_down_button,
                    window.toast.close_button,
                )
            )
            icon_only_buttons = (
                window.navigator.add_button,
                window.navigator.remove_button,
            )
            checks["icon_only_controls_have_tooltips"] = all(
                button.toolButtonStyle() == Qt.ToolButtonIconOnly
                and not button.icon().isNull()
                and bool(button.toolTip().strip())
                and bool(button.accessibleName().strip())
                for button in icon_only_buttons
            )

            # Build and manipulate a two-document SourceBundle through the
            # actual navigator/editor wiring.
            window.source.setPlainText(APP_SOURCE)
            _set_identity(window, app, QtCore, "app", "app.py")
            main_id = window.controller.snapshot.active_document_id
            window.navigator.add_button.click()
            _pump(app, QtCore)
            companion_id = window.controller.snapshot.active_document_id
            window.source.setPlainText(LIB_SOURCE)
            _set_identity(window, app, QtCore, "lib", "lib.py")

            selected_main = _select_document_row(window, app, QtCore, main_id)
            main_visible = window.source.toPlainText() == APP_SOURCE
            selected_companion = _select_document_row(
                window, app, QtCore, companion_id
            )
            companion_visible = window.source.toPlainText() == LIB_SOURCE
            checks["two_module_navigation"] = bool(
                len(window.controller.snapshot.documents) == 2
                and selected_main
                and main_visible
                and selected_companion
                and companion_visible
            )

            # The active companion starts second.  Operate the reorder button
            # by keyboard, make it primary, then restore the app as primary and
            # first in presentation order.
            window.navigator.move_up_button.setFocus()
            QTest.keyClick(window.navigator.move_up_button, Qt.Key_Space)
            _pump(app, QtCore)
            moved_ids = tuple(
                item.document_id for item in window.controller.snapshot.documents
            )
            checks["bundle_reorder"] = moved_ids == (companion_id, main_id)

            window.navigator.primary_check.setFocus()
            QTest.keyClick(window.navigator.primary_check, Qt.Key_Space)
            _pump(app, QtCore)
            companion_was_primary = (
                window.controller.snapshot.primary_document.document_id == companion_id
            )
            _select_document_row(window, app, QtCore, main_id)
            window.navigator.primary_check.setFocus()
            QTest.keyClick(window.navigator.primary_check, Qt.Key_Space)
            _pump(app, QtCore)
            main_is_primary = (
                window.controller.snapshot.primary_document.document_id == main_id
            )
            window.navigator.move_up_button.setFocus()
            QTest.keyClick(window.navigator.move_up_button, Qt.Key_Space)
            _pump(app, QtCore)
            restored_ids = tuple(
                item.document_id for item in window.controller.snapshot.documents
            )
            checks["primary_document_selection"] = bool(
                companion_was_primary
                and main_is_primary
                and restored_ids == (main_id, companion_id)
            )

            # Keyboard find/replace, including the UTF-16 edge case where the
            # replacement contains an astral character immediately before the
            # search token.  Correct navigation must skip the inserted token.
            window.source.setFocus()
            QTest.keyClick(window.source, Qt.Key_F, Qt.ControlModifier)
            _pump(app, QtCore)
            checks["ctrl_f_opens_find"] = bool(
                window.find_bar.isVisible()
                and window.find_bar.editor is window.source
                and not window.find_bar.replace_edit.isVisible()
            )
            window.find_bar.find_edit.setFocus()
            QTest.keyClick(window.find_bar.find_edit, Qt.Key_H, Qt.ControlModifier)
            _pump(app, QtCore)
            checks["ctrl_h_opens_replace"] = bool(
                window.find_bar.isVisible()
                and window.find_bar.replace_edit.isVisible()
                and window.find_bar.editor is window.source
            )
            if not window.find_bar.replace_edit.isVisible():
                # Keep collecting independent checks when the shortcut itself
                # is the failure under investigation.
                window.find_bar.open_find(True)
                _pump(app, QtCore)

            window.find_bar.find_edit.setText("x")
            default_settled = _wait_until(
                app,
                QtCore,
                lambda: (
                    window.find_bar.match_count == 4
                    and not window.find_bar._search_pending
                ),
            )
            default_matches = window.find_bar.match_count
            window.find_bar.whole_word.setChecked(True)
            whole_word_settled = _wait_until(
                app,
                QtCore,
                lambda: (
                    window.find_bar.match_count == 3
                    and not window.find_bar._search_pending
                ),
            )
            whole_word_matches = window.find_bar.match_count
            window.find_bar.match_case.setChecked(True)
            case_settled = _wait_until(
                app,
                QtCore,
                lambda: (
                    window.find_bar.match_count == 2
                    and not window.find_bar._search_pending
                ),
            )
            case_matches = window.find_bar.match_count
            checks["find_case_and_whole_word_modes"] = bool(
                default_settled
                and whole_word_settled
                and case_settled
                and default_matches == 4
                and whole_word_matches == 3
                and case_matches == 2
            )
            window.find_bar.replace_edit.setText("\U0001f680x")
            replaced = window.find_bar.replace_current()
            replacement_settled = _wait_until(
                app,
                QtCore,
                lambda: (
                    window.find_bar.match_count == 2
                    and not window.find_bar._search_pending
                ),
            )
            if replacement_settled:
                window.find_bar._select_active_match()
            replaced_text = window.source.toPlainText()
            cursor = window.source.textCursor()
            last_x = replaced_text.rfind("x")
            expected_last_x = python_offset_to_qt_position(replaced_text, last_x)
            rocket_index = replaced_text.find("\U0001f680")
            inserted_x = python_offset_to_qt_position(
                replaced_text,
                max(0, rocket_index),
            ) + 2 if rocket_index >= 0 else -1
            checks["emoji_replacement_navigation"] = bool(
                replaced
                and replacement_settled
                and "\U0001f680x" in replaced_text
                and window.find_bar.match_count == 2
                and cursor.selectedText() == "x"
                and cursor.selectionStart() == expected_last_x
                and cursor.selectionStart() != inserted_x
            )
            window.find_bar.close_bar()
            _pump(app, QtCore)

            checks["conversion_completed"] = _convert_and_wait(
                window, app, QtCore
            )
            converted = window.controller.snapshot
            checks["conversion_completed"] = bool(
                checks["conversion_completed"]
                and len(converted.documents) == 2
                and converted.primary_document.module_id == "app"
                and "increment" in (converted.generated_c or "")
                and "run" in (converted.generated_c or "")
            )

            window.show_details_action.trigger()
            details_settled = _wait_until(
                app,
                QtCore,
                lambda: (
                    window.tabs.isVisible()
                    and window.mappings.tree.topLevelItemCount()
                    == min(
                        len(converted.mappings),
                        window.mappings.DISPLAY_LIMIT,
                    )
                ),
            )
            checks["structured_details_projected"] = bool(
                details_settled
                and window.tabs.isVisible()
                and window.diags.tree.topLevelItemCount()
                == len(converted.diagnostics)
                and window.summary.tree.topLevelItemCount() > 0
                and window.trace.tree.topLevelItemCount() > 0
                and window.telemetry.tree.topLevelItemCount() > 0
                and window.mappings.tree.topLevelItemCount()
                == min(len(converted.mappings), window.mappings.DISPLAY_LIMIT)
                and len(converted.mappings) > 0
            )

            mapping_item = window.mappings.tree.topLevelItem(0)
            mapping_ok = mapping_item is not None
            if mapping_item is not None:
                index_ready = _wait_until(
                    app,
                    QtCore,
                    lambda: (
                        window.controller.result_output_index
                        is not None
                    ),
                )
                window.show_c_action.trigger()
                output_ready = _wait_until(
                    app,
                    QtCore,
                    lambda: (
                        window.output.toPlainText()
                        == (converted.generated_c or "")
                    ),
                )
                mapping = mapping_item.data(0, Qt.UserRole)
                output_text = window.output.toPlainText()
                start, end = mapping_character_range(mapping, output_text)
                expected_start = python_offset_to_qt_position(output_text, start)
                expected_end = python_offset_to_qt_position(output_text, end)
                window.mappings.tree.itemActivated.emit(mapping_item, 0)
                _pump(app, QtCore, 8)
                output_cursor = window.output.textCursor()
                mapping_ok = bool(
                    index_ready
                    and output_ready
                    and window.output_panel.isVisible()
                    and window.output.isVisible()
                    and output_cursor.selectionStart() == expected_start
                    and output_cursor.selectionEnd() == expected_end
                    and window.statusBar().currentMessage().startswith("Mapping")
                )
            checks["mapping_navigation"] = mapping_ok

            # Link a destination without invoking a file chooser, then exercise
            # the MainWindow Save C path and verify atomic replacement custody.
            linked_c = temporary_root / "linked-result.c"
            linked_c.write_text("last-known-good\n", encoding="utf-8")
            window.controller.link_generated_c(linked_c)
            _pump(app, QtCore)
            first_saved = _save_c_and_wait(
                window,
                linked_c,
                app,
                QtCore,
            )
            first_bytes = linked_c.read_bytes()
            checks["atomic_linked_c_save"] = bool(
                first_saved
                and first_bytes
                == (window.controller.snapshot.generated_c or "").encode("utf-8")
                and not tuple(temporary_root.glob(".linked-result.c.*.tmp"))
            )

            baseline_source = window.source.toPlainText()
            retained_c = linked_c.read_bytes()
            _replace_editor_text(
                window.source,
                baseline_source + "# semantic edit\n",
            )
            edit_settled = _wait_until(
                app,
                QtCore,
                lambda: not window._source_sync_pending,
            )
            stale_snapshot = window.controller.snapshot
            stale_save = window.save_c()
            _pump(app, QtCore)
            checks["stale_output_blocks_save"] = bool(
                edit_settled
                and stale_snapshot.state.value == "stale"
                and not stale_snapshot.can_save_c
                and stale_snapshot.generated_c == converted.generated_c
                and not stale_save
                and linked_c.read_bytes() == retained_c
            )

            _replace_editor_text(window.source, baseline_source)
            changed_back_settled = _wait_until(
                app,
                QtCore,
                lambda: not window._source_sync_pending,
            )
            changed_back = window.controller.snapshot
            changed_back_save = window.save_c()
            _pump(app, QtCore)
            checks["changed_back_source_blocks_save"] = bool(
                changed_back_settled
                and changed_back.state.value == "stale"
                and not changed_back.can_save_c
                and not changed_back_save
                and linked_c.read_bytes() == retained_c
            )

            recovered = _convert_and_wait(window, app, QtCore)
            checks["stale_recovery_conversion"] = bool(
                recovered
                and window.controller.snapshot.can_save_c
                and window.controller.snapshot.bundle_fingerprint
                == window.controller.snapshot.result_bundle_fingerprint
            )
            recovered_saved = _save_c_and_wait(
                window,
                linked_c,
                app,
                QtCore,
            )

            before_identity_c = linked_c.read_bytes()
            before_identity_snapshot = window.controller.snapshot
            window.navigator.module_edit.setText("app_renamed")
            pending_was_uncommitted = (
                before_identity_snapshot.active_document.module_id == "app"
                and window.navigator.pending_identity()[0] == "app_renamed"
            )
            identity_save = window.save_c()
            _pump(app, QtCore)
            identity_snapshot = window.controller.snapshot
            checks["pending_identity_committed_before_save_c"] = bool(
                pending_was_uncommitted
                and identity_snapshot.active_document.module_id == "app_renamed"
            )
            checks["identity_change_blocks_save"] = bool(
                recovered_saved
                and not identity_save
                and identity_snapshot.state.value == "stale"
                and not identity_snapshot.can_save_c
                and linked_c.read_bytes() == before_identity_c
            )

            final_recovered = _convert_and_wait(window, app, QtCore)
            final_saved = _save_c_and_wait(
                window,
                linked_c,
                app,
                QtCore,
            )
            final_snapshot = window.controller.snapshot
            checks["final_recovery_conversion_and_save"] = bool(
                final_recovered
                and final_saved
                and final_snapshot.can_save_c
                and final_snapshot.primary_document.module_id == "app_renamed"
                and linked_c.read_bytes()
                == (final_snapshot.generated_c or "").encode("utf-8")
                and not tuple(temporary_root.glob(".linked-result.c.*.tmp"))
            )

            # Release screenshots must remain usable at both tested device
            # scale factors: both editors, both bundle rows, and the primary
            # save control must have a real visible viewport.
            editor_sizes = window.editor_splitter.sizes()
            editor_total = sum(editor_sizes)
            main_sizes = window.main_splitter.sizes()
            main_total = sum(main_sizes)
            document_rows_height = sum(
                max(1, window.navigator.documents.sizeHintForRow(row))
                for row in range(window.navigator.documents.count())
            )
            document_rows_visible = all(
                window.navigator.documents.visualItemRect(
                    window.navigator.documents.item(row)
                ).intersects(
                    window.navigator.documents.viewport().rect()
                )
                for row in range(window.navigator.documents.count())
            )
            checks["responsive_splitter_layout"] = bool(
                len(editor_sizes) == 2
                and editor_total > 0
                and min(editor_sizes) >= editor_total * 0.35
                and len(main_sizes) == 2
                and main_total > 0
                and min(main_sizes) >= main_total * 0.25
                and document_rows_visible
                and window.navigator.documents.viewport().height()
                >= document_rows_height * 0.9
                and window.navigator.documents.geometry().bottom()
                < window.navigator.module_edit.geometry().top()
            )
            save_c_buttons = tuple(
                widget
                for widget in window.save_c_action.associatedWidgets()
                if isinstance(widget, QtWidgets.QToolButton)
            )
            checks["toolbar_save_c_visible"] = any(
                button.isVisible() and not button.visibleRegion().isEmpty()
                for button in save_c_buttons
            )
            checks["linked_destination_discoverable"] = bool(
                linked_c.name in window.linked_c_label.text()
                and window.linked_c_label.toolTip() == str(linked_c)
            )

            if screenshot_path is not None:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                _pump(app, QtCore, 8)
                checks["screenshot_written"] = bool(
                    window.grab().save(str(screenshot_path), "PNG")
                    and screenshot_path.is_file()
                    and screenshot_path.stat().st_size > 0
                )

            _pump(app, QtCore)
            checks["no_unexpected_modal_dialogs"] = bool(
                not dialog_observer.shown
                and not any(
                    isinstance(widget, QtWidgets.QDialog) and widget.isVisible()
                    for widget in app.topLevelWidgets()
                )
            )
        except Exception as exc:  # produce evidence rather than an unstructured traceback
            message = str(exc).replace(str(temporary_root), "<temporary>").strip()
            error = f"{exc.__class__.__name__}: {message or 'widget smoke failed'}"
        finally:
            if app is not None and dialog_observer is not None:
                app.removeEventFilter(dialog_observer)
            if window is not None:
                # Bypass the interactive dirty-document close question in this
                # automated smoke; all tested custody decisions are already in
                # the report.  Perform the controller cleanup explicitly.
                window._closing = True
                try:
                    window.controller.unsubscribe(window._snapshot_listener)
                except (AttributeError, RuntimeError, ValueError):
                    pass
                try:
                    window.controller.close(wait=True)
                finally:
                    window.close()
                    if app is not None:
                        _pump(app, QtCore)

    return build_report(
        runtime=runtime,
        checks=checks,
        error=error,
        screenshot_requested=screenshot_requested,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the PyCForge 0.12.2 actual offscreen widget smoke."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="atomically write the deterministic JSON report to this path",
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="optionally capture the final workspace surface as a PNG",
    )
    args = parser.parse_args(argv)

    report = run_widget_smoke(args.screenshot)
    text = render_report(report)
    if args.output is not None:
        AtomicWriter().write_text(args.output, text)
    print(text, end="")
    return 0 if report.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
