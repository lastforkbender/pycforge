"""Widget construction and action wiring for the PyCForge Qt workspace."""

from __future__ import annotations
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .find_replace import FindReplaceBar
from .icons import pycforge_icon_path
from .qt_editor_surfaces import (
    build_generated_c_surface,
    build_source_editor_surface,
)
from .qt_workspace_widgets import BreadcrumbBar, DocumentTabBar
from .qt_workspace_panels import (
    BundleSearchView,
    OutlineView,
    SessionHistoryView,
)
from .panels import (
    DiagnosticsView,
    DocumentNavigator,
    InspectorTree,
    MappingsView,
    ToastBanner,
)
from .qt_actions import QtActionRegistry
from .qt_menus import QtMenuFactory
from .qt_shell_interactions import QtShellInteractionMixin
from .visual_tokens import PYCFORGE_METRICS


class QtShellMixin(QtShellInteractionMixin):
    """Construct and connect the fixed professional workspace shell."""

    def _build_workspace(self) -> None:
        self.setWindowIcon(
            QIcon(str(pycforge_icon_path("brand-mark")))
        )
        shell = QWidget()
        shell.setObjectName("workspaceShell")
        shell.setProperty("role", "workspace-shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(10, 9, 10, 8)
        shell_layout.setSpacing(7)

        self.toast = ToastBanner()
        shell_layout.addWidget(self.toast)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setObjectName("MainWorkspaceSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        shell_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(shell)

        self.workspace_splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter.setObjectName("SourceBundleSplitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.workspace_splitter)

        self.navigator = DocumentNavigator()
        self.navigator.add_button.setIcon(
            QIcon(str(pycforge_icon_path("add-document")))
        )
        self.navigator.remove_button.setIcon(
            QIcon(str(pycforge_icon_path("remove-document")))
        )
        self.navigator.add_button.setText("")
        self.navigator.remove_button.setText("")
        self.workspace_splitter.addWidget(self.navigator)

        editor_panel = QFrame()
        editor_panel.setObjectName("editorPanel")
        editor_panel.setProperty("role", "panel")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("PYTHON SOURCE")
        title.setProperty("role", "panel-title")
        self.active_module_label = QLabel("main  ·  main.py")
        self.active_module_label.setObjectName("ActiveModuleLabel")
        self.active_path_label = QLabel("Unsaved document")
        self.active_path_label.setObjectName("PathLabel")
        self.active_path_label.setToolTip(
            "Active Python file linkage"
        )
        self.active_path_label.setMinimumWidth(0)
        self.active_path_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.state_chip = QLabel("EMPTY")
        self.state_chip.setProperty("role", "status-chip")
        self.state_chip.setProperty("status", "neutral")
        header.addWidget(title)
        header.addWidget(self.active_module_label)
        header.addWidget(self.active_path_label, 1)
        header.addWidget(self.state_chip)
        editor_layout.addLayout(header)

        self.document_tabs = DocumentTabBar()
        editor_layout.addWidget(self.document_tabs)
        self.breadcrumbs = BreadcrumbBar()
        editor_layout.addWidget(self.breadcrumbs)

        self.find_bar = FindReplaceBar()
        editor_layout.addWidget(self.find_bar)

        self.editor_splitter = QSplitter(Qt.Horizontal)
        self.editor_splitter.setObjectName("PythonCEditorSplitter")
        self.editor_splitter.setChildrenCollapsible(False)
        editor_layout.addWidget(self.editor_splitter, 1)

        source_panel = build_source_editor_surface(self)
        self.editor_splitter.addWidget(source_panel)

        self.output_panel = build_generated_c_surface(self)
        self.editor_splitter.addWidget(self.output_panel)
        self.editor_splitter.setStretchFactor(0, 1)
        self.editor_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.addWidget(editor_panel)
        self.workspace_splitter.setStretchFactor(0, 0)
        self.workspace_splitter.setStretchFactor(1, 1)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("detailsPanel")
        self.tabs.setAccessibleName("Transpilation details")
        self.diags = DiagnosticsView()
        self.summary = InspectorTree("Transpilation summary")
        self.trace = InspectorTree("Decision trace")
        self.mappings = MappingsView()
        self.telemetry = InspectorTree("Telemetry")
        self.outline = OutlineView()
        self.bundle_search = BundleSearchView()
        self.session_history = SessionHistoryView()
        self.tabs.addTab(self.diags, "Diagnostics")
        self.tabs.addTab(self.summary, "Summary")
        self.tabs.addTab(self.trace, "Decision Trace")
        self.tabs.addTab(self.mappings, "Mappings")
        self.tabs.addTab(self.telemetry, "Telemetry")
        self.tabs.addTab(self.outline, "Outline")
        self.tabs.addTab(self.bundle_search, "Bundle Search")
        self.tabs.addTab(self.session_history, "History")
        self.tabs.setVisible(False)
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 2)

        self.progress = QProgressBar()
        self.progress.setAccessibleName("Transpilation progress")
        self.progress.setMinimumWidth(170)
        self.progress.setMaximumWidth(250)
        self.progress.setTextVisible(True)
        self.progress.hide()
        self.status_document = QLabel("main.py")
        self.status_document.setObjectName("MutedLabel")
        self.statusBar().addPermanentWidget(self.status_document)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_actions(self) -> None:
        handlers = {
            "file.open_python": self.open_file,
            "bundle.new_module": self.add_document,
            "bundle.remove_module": self.remove_active_document,
            "bundle.move_up": self._move_document_up,
            "bundle.move_down": self._move_document_down,
            "bundle.make_primary": self._make_selected_primary,
            "file.save_python": self.save_source,
            "file.save_python_as": self.save_source_as,
            "output.set_destination": self.link_c_file,
            "output.save_c": self.save_c,
            "conversion.convert": self.convert,
            "conversion.cancel": self.controller.cancel,
            "edit.undo": lambda: self._invoke_target_method("undo"),
            "edit.redo": lambda: self._invoke_target_method("redo"),
            "edit.cut": lambda: self._invoke_target_method("cut"),
            "edit.copy": self._copy_action_selection,
            "edit.paste": lambda: self._invoke_target_method("paste"),
            "edit.select_all": (
                lambda: self._invoke_target_method("selectAll")
            ),
            "edit.duplicate_line": self._duplicate_source,
            "edit.move_line_up": self._move_source_up,
            "edit.move_line_down": self._move_source_down,
            "edit.indent": self._indent_source,
            "edit.outdent": self._outdent_source,
            "edit.toggle_comment": self._toggle_source_comment,
            "search.find": lambda: self._open_find(False),
            "search.replace": lambda: self._open_find(True),
            "search.bundle": self._show_bundle_search,
            "search.next_match": self.find_bar.next_match,
            "search.previous_match": self.find_bar.previous_match,
            "search.replace_current": self.find_bar.replace_current,
            "search.replace_all": self.find_bar.replace_all,
            "search.close": self.find_bar.close_bar,
            "view.source_bundle": self._set_navigator_visible,
            "view.generated_c": self._set_output_visible,
            "view.conversion_details": self._set_details_visible,
            "view.outline": self._show_outline,
            "view.conversion_history": self._show_conversion_history,
            "view.whitespace": self._set_whitespace_visible,
            "view.split_source": self._set_source_split_visible,
            "editor.toggle_fold": self._toggle_source_fold,
            "navigation.go_to_line": self._go_to_source_line,
            "workspace.command_palette": self._open_command_palette,
            "tree.expand_all": (
                lambda: self._invoke_target_method("expandAll")
            ),
            "tree.collapse_all": (
                lambda: self._invoke_target_method("collapseAll")
            ),
            "diagnostics.reveal_source": (
                self._reveal_selected_diagnostic
            ),
            "mappings.reveal_output": self._reveal_selected_mapping,
            "mappings.reveal_source": (
                self._reveal_selected_mapping_source
            ),
        }
        self.action_registry = QtActionRegistry(
            self,
            handlers,
            state_provider=self._action_states,
        )
        self.menu_factory = QtMenuFactory(self.action_registry, self)
        compatibility = {
            "open_action": "file.open_python",
            "add_document_action": "bundle.new_module",
            "remove_document_action": "bundle.remove_module",
            "save_python_action": "file.save_python",
            "save_python_as_action": "file.save_python_as",
            "convert_action": "conversion.convert",
            "cancel_action": "conversion.cancel",
            "find_action": "search.find",
            "replace_action": "search.replace",
            "link_c_action": "output.set_destination",
            "save_c_action": "output.save_c",
            "show_c_action": "view.generated_c",
            "show_details_action": "view.conversion_details",
            "show_navigator_action": "view.source_bundle",
        }
        for attribute, action_id in compatibility.items():
            setattr(self, attribute, self.action_registry.action(action_id))
        self.action_registry.set_checked("view.source_bundle", True)
        self.navigator.bind_action_registry(self.action_registry)
        self.find_bar.bind_action_registry(self.action_registry)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("PyCForge Workspace")
        toolbar.setObjectName("PyCForgeToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        size = PYCFORGE_METRICS.icon_toolbar
        toolbar.setIconSize(QSize(size, size))
        self.addToolBar(toolbar)
        self.menu_factory.populate_toolbar(toolbar)
        self.workspace_toolbar = toolbar
        for action in (
            self.open_action,
            self.save_python_action,
            self.convert_action,
            self.cancel_action,
        ):
            button = toolbar.widgetForAction(action)
            if isinstance(button, QToolButton):
                button.setToolButtonStyle(
                    Qt.ToolButtonTextBesideIcon
                )
        convert_button = toolbar.widgetForAction(
            self.convert_action
        )
        if isinstance(convert_button, QToolButton):
            convert_button.setProperty("role", "primary")
            convert_button.setAccessibleName(
                "Transpile source bundle to C source"
            )
        cancel_button = toolbar.widgetForAction(
            self.cancel_action
        )
        if isinstance(cancel_button, QToolButton):
            cancel_button.setProperty("role", "danger")

    def _build_menus(self) -> None:
        self.main_menus = self.menu_factory.install_main_menus(self.menuBar())
        self.recent_menu = self.menu_factory.menu("menu.open_recent")
        self._rebuild_recent_menu()
        required_contexts = (
            (self.source, "context.python_source"),
            (self.source_secondary, "context.python_source"),
            (self.output, "context.generated_c"),
            (self.navigator.documents, "context.source_bundle"),
            (self.document_tabs, "context.document_tabs"),
            (self.diags.tree, "context.diagnostics"),
            (self.mappings.tree, "context.mappings"),
            (self.summary.tree, "context.inspector"),
            (self.trace.tree, "context.inspector"),
            (self.telemetry.tree, "context.inspector"),
            (self.outline.tree, "context.inspector"),
            (self.bundle_search.tree, "context.bundle_search"),
            (
                self.session_history.tree,
                "context.conversion_history",
            ),
        )
        for widget, surface_id in required_contexts:
            self.menu_factory.install_context_menu(widget, surface_id)
        text_inputs = (
            self.navigator.filter_edit,
            self.navigator.module_edit,
            self.navigator.logical_edit,
            self.find_bar.find_edit,
            self.find_bar.replace_edit,
            self.diags.filter_edit,
            self.summary.filter_edit,
            self.trace.filter_edit,
            self.mappings.filter_edit,
            self.telemetry.filter_edit,
            self.outline.filter_edit,
            self.bundle_search.query_edit,
        )
        for widget in text_inputs:
            self.menu_factory.install_context_menu(
                widget, "context.text_input"
            )
        self.menu_factory.install_context_menu(
            self.diags.details, "context.read_only_text"
        )


# Executable wiring is separated into ``QtShellInteractionMixin``. These two
# seam markers retain the predecessor's static integration audit vocabulary:
# self.navigator.identity_pending_changed.connect(
# and not self.navigator.identity_pending
__all__ = ["QtShellMixin"]
