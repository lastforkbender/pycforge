"""Professional PyQt5 workspace for the PyCForge facade.

The desktop surface remains presentation and orchestration only. It never
executes Python, compiles generated C, resolves imports through the host, or
changes converter contracts. The module is import-safe when PyQt5 is absent.

The implementation is decomposed into cohesive mixins so the active workspace
surface stays reviewable: shell construction, document actions, bounded
snapshot projection, settings/file observation, and guarded close behavior.
"""

from __future__ import annotations

from typing import Any

from pycforge._version import __version__

from .controller import WorkspaceController
from .qt_contract import (
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
    SETTINGS_SCHEMA_VERSION,
    coerce_settings_schema_version,
    diagnostic_character_range,
    line_column_offset,
    mapping_character_range,
    python_offset_to_qt_position,
    qt_position_to_python_offset,
    qt_range,
)
from .theme import apply_pycforge_theme


# Preserve the original private helper spelling used by the workspace tests
# and downstream integrations.
_coerce_settings_schema_version = coerce_settings_schema_version
_qt_range = qt_range


try:
    from PyQt5.QtCore import (
        QFileSystemWatcher,
        QSettings,
        Qt,
        QTimer,
        pyqtSignal,
    )
    from PyQt5.QtWidgets import QApplication, QMainWindow
except (ImportError, ModuleNotFoundError) as exc:
    QT_AVAILABLE = False
    _QT_ERROR = exc
else:
    QT_AVAILABLE = True
    _QT_ERROR = None


if QT_AVAILABLE:
    from .qt_close import QtCloseMixin
    from .qt_documents import QtDocumentActionsMixin
    from .qt_projection import QtProjectionMixin
    from .qt_shell import QtShellMixin
    from .qt_state import QtStateMixin
    from .qt_workspace_features import QtWorkspaceFeaturesMixin

    class MainWindow(
        QtShellMixin,
        QtWorkspaceFeaturesMixin,
        QtDocumentActionsMixin,
        QtProjectionMixin,
        QtStateMixin,
        QtCloseMixin,
        QMainWindow,
    ):
        """Python-first SourceBundle workspace with immutable C presentation."""

        snapshot_ready = pyqtSignal(object)
        structure_ready = pyqtSignal(object)
        operation_error = pyqtSignal(str)
        io_finished = pyqtSignal(object, object)

        _STAGE_LABELS = {
            "frontend.source_document": "Reading source bundle",
            "frontend.parse": "Parsing Python documents",
            "frontend.normalize": "Normalizing Python IR",
            "modules.resolve": "Resolving module bundle",
            "analysis.plan": "Analyzing and planning",
            "lowering.first_slice": (
                "Lowering, resolving helpers, and validating C"
            ),
        }
        _SUCCESS_STATES = {
            "converted",
            "warning",
            "approximation",
            "observer-incomplete",
        }

        def __init__(
            self,
            controller: WorkspaceController | None = None,
        ):
            super().__init__()
            self.controller = controller or WorkspaceController()
            self.settings = QSettings(
                SETTINGS_ORGANIZATION,
                SETTINGS_APPLICATION,
            )
            self._prepare_settings()
            self._displayed_document_id: str | None = None
            self._displayed_source_key: tuple[str, int] | None = None
            self._displayed_output_key: (
                tuple[int | None, int] | None
            ) = None
            self._output_projection_key: (
                tuple[int | None, int] | None
            ) = None
            self._output_projection_offset = 0
            self._output_projection_text = ""
            self._navigator_key: tuple[Any, ...] | None = None
            self._detail_projection_key: (
                tuple[Any, ...] | None
            ) = None
            self._source_marker_key: tuple[Any, ...] | None = None
            self._output_marker_key: tuple[Any, ...] | None = None
            self._last_snapshot = None
            self._progress_sequence: int | None = None
            self._closing = False
            self._close_save_pending = 0
            self._close_save_failed = False
            self._applying_source_text = False
            self._source_sync_pending = False
            self._source_sync_document_id: str | None = None
            self._source_sync_timer = QTimer(self)
            self._source_sync_timer.setSingleShot(True)
            self._source_sync_timer.setInterval(120)
            self._source_sync_timer.timeout.connect(
                self._flush_pending_source_sync
            )
            self._known_file_fingerprints: dict[str, str] = {}
            self._watcher_projection_key: (
                tuple[Any, ...] | None
            ) = None
            self._recent_paths = self._load_recent_paths()
            self._last_directory = self._setting_text(
                "workspace/last_directory", ""
            )
            self._initialize_workspace_features()

            self.setObjectName("PyCForgeMainWindow")
            self.setWindowTitle(f"PyCForge {__version__} — Workspace")
            self.resize(1420, 880)
            self.setMinimumSize(960, 620)

            self._build_workspace()
            self._build_actions()
            self._build_toolbar()
            self._build_menus()
            self._wire_workspace()
            self._restore_workspace_state()

            self.file_watcher = QFileSystemWatcher(self)
            self.file_watcher.fileChanged.connect(
                self._external_file_changed
            )

            self.snapshot_ready.connect(self._apply_snapshot)
            self.operation_error.connect(
                lambda message: self.toast.show_message(
                    message, "error"
                )
            )
            self.io_finished.connect(
                lambda callback, future: callback(future)
            )
            self._snapshot_listener = self.snapshot_ready.emit
            self.controller.subscribe(self._snapshot_listener)
            self._apply_snapshot(self.controller.snapshot)


# Static integration vocabulary remains documented at the public module seam
# after decomposition. Runtime implementations live in the cohesive mixins:
# CodeEditor(language="python"), CodeEditor(language="c"), DocumentNavigator(),
# FindReplaceBar(), DiagnosticsView(), MappingsView(), QProgressBar;
# toolbar.setObjectName("PyCForgeToolbar");
# self.controller.save_generated_c_linked_async(), snapshot.can_save_c;
# self.output.setReadOnly(True), self.output.setVisible(False),
# self.tabs.setVisible(False); action label "Show C"; progress delay 180 ms.


def run() -> int:
    if not QT_AVAILABLE:
        raise RuntimeError(
            "PyQt5 is required for the PyCForge workspace"
        ) from _QT_ERROR
    if QApplication.instance() is None:
        QApplication.setAttribute(
            Qt.AA_EnableHighDpiScaling, True
        )
        QApplication.setAttribute(
            Qt.AA_UseHighDpiPixmaps, True
        )
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("PyCForge")
    app.setOrganizationName("PyCForge")
    apply_pycforge_theme(app)
    window = MainWindow()
    window.show()
    return app.exec_()


__all__ = [
    "MainWindow",
    "QT_AVAILABLE",
    "SETTINGS_SCHEMA_VERSION",
    "diagnostic_character_range",
    "line_column_offset",
    "mapping_character_range",
    "python_offset_to_qt_position",
    "qt_position_to_python_offset",
    "run",
] if QT_AVAILABLE else [
    "QT_AVAILABLE",
    "SETTINGS_SCHEMA_VERSION",
    "diagnostic_character_range",
    "line_column_offset",
    "mapping_character_range",
    "python_offset_to_qt_position",
    "qt_position_to_python_offset",
    "run",
]
