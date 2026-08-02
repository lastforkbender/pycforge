"""Build the PyCForge Qt stylesheet from semantic visual tokens."""

from __future__ import annotations
from string import Template
from .icons import pycforge_icon_path
from .theme_workspace_stylesheet import build_workspace_stylesheet
from .visual_tokens import PYCFORGE_COLORS, PyCForgeColors, color_tokens


_PYCFORGE_QSS_TEMPLATE = Template(
    r"""
QMainWindow, QDialog {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:0.42 ${canvas},stop:1 ${void});
    color: ${text};
}
QWidget {
    color: ${text};
    selection-background-color: ${selection};
    selection-color: #FFFFFF;
}
QWidget#workspaceShell, QWidget[role="workspace-shell"] { background: transparent; }
QFrame#DocumentNavigator {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:0.58 ${surface},stop:1 ${canvas});
    border: 1px solid ${border};
    border-right: 1px solid ${border_strong};
    border-radius: 8px;
}
QFrame#editorPanel, QFrame#detailsPanel, QFrame[role="panel"] {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${surface});
    border: 1px solid ${border};
    border-radius: 8px;
}
QLabel {
    background: transparent;
    color: ${text_soft};
}
QLabel#PanelEyebrow {
    color: ${blue_bright};
    font-weight: 700;
    padding: 3px 0 5px 0;
    border-bottom: 1px solid ${blue_dim};
}
QLabel#MutedLabel { color: ${text_muted}; padding: 2px 3px; }
QLabel#PathLabel { color: ${text_muted}; font-style: italic; padding: 2px 4px; }
QLabel#ActiveModuleLabel {
    color: ${violet_bright};
    font-weight: 600;
    padding: 2px 6px;
    border-left: 2px solid ${violet_dim};
}
QLabel[role="panel-title"] {
    color: ${text};
    font-weight: 600;
    padding: 4px 2px 5px 2px;
    border-bottom: 1px solid ${blue_dim};
}
QFrame#SourceEditorSurface, QFrame#GeneratedCPanel {
    background: ${void};
    border: 1px solid ${border};
    border-radius: 7px;
}
QFrame#GeneratedCPanel { border-top: 2px solid ${warm_dim}; }
QPlainTextEdit#PythonSourceEditor, QPlainTextEdit#PythonSourceEditorSecondary, QPlainTextEdit#GeneratedCEditor {
    border: 0;
    border-radius: 6px;
    padding: 2px;
}
QPlainTextEdit#GeneratedCEditor { background: ${void}; color: ${text_soft}; }
QLabel[status="neutral"], QLabel[role="status-chip"] {
    color: ${text_soft};
    background: ${surface_active};
    border: 1px solid ${border_strong};
    border-radius: 9px;
    padding: 2px 8px;
}
QLabel[status="success"] {
    color: ${success_bright};
    background: ${success_dim};
    border: 1px solid ${success};
    border-radius: 9px;
    padding: 2px 8px;
}
QLabel[status="warning"] {
    color: ${warning_bright};
    background: ${warning_dim};
    border: 1px solid ${warning};
    border-radius: 9px;
    padding: 2px 8px;
}
QLabel[status="error"] {
    color: ${error_bright};
    background: ${error_dim};
    border: 1px solid ${error};
    border-radius: 9px;
    padding: 2px 8px;
}
QFrame#ToastBanner { border-radius: 7px; padding: 1px; }
QFrame#ToastBanner QLabel {
    color: ${text}; background: transparent; font-weight: 500;
}
QFrame#ToastBanner QToolButton {
    min-width: 22px;
    min-height: 22px;
    padding: 2px;
    color: ${text_soft};
    background: transparent;
    border: 1px solid transparent;
}
QFrame#ToastBanner QToolButton:hover,
QFrame#ToastBanner QToolButton:focus {
    color: #FFFFFF;
    background: ${surface_hover};
    border-color: ${focus_ring};
}
QFrame#ToastBanner[tone="info"] {
    color: #CDEFFC;
    background: #12313D;
    border: 1px solid #3E8FB0;
    border-left: 3px solid ${blue};
}
QFrame#ToastBanner[tone="success"] {
    color: #C9F7E2;
    background: #123329;
    border: 1px solid #448E70;
    border-left: 3px solid ${success};
}
QFrame#ToastBanner[tone="warning"] {
    color: #FFE4AB;
    background: #3A301B;
    border: 1px solid #8D7037;
    border-left: 3px solid ${warning};
}
QFrame#ToastBanner[tone="error"] {
    color: #FFD0D6;
    background: #3A1E26;
    border: 1px solid #9A4958;
    border-left: 3px solid ${error};
}
QFrame#ToastBanner[tone="info"] QLabel { color: #CDEFFC; }
QFrame#ToastBanner[tone="success"] QLabel { color: #C9F7E2; }
QFrame#ToastBanner[tone="warning"] QLabel { color: #FFE4AB; }
QFrame#ToastBanner[tone="error"] QLabel { color: #FFD0D6; }
QMenuBar {
    color: ${text_soft};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${canvas});
    border: 0;
    border-bottom: 1px solid ${border_strong};
    padding: 3px 6px;
    spacing: 3px;
}
QMenuBar::item {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 10px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${blue_dim},stop:0.62 ${violet_dim},stop:1 ${warm_dim});
    border-color: ${border_strong};
    border-bottom: 2px solid ${warm};
}
QMenuBar::item:disabled { color: ${text_disabled}; }
QMenu, QMenu#PyCForgeMenu, QComboBox QAbstractItemView {
    color: ${text};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${surface});
    border: 1px solid ${border_strong};
    border-radius: 9px;
    padding: 6px;
    selection-background-color: ${selection};
    selection-color: #FFFFFF;
}
QMenu::item, QMenu#PyCForgeMenu::item {
    min-height: 18px;
    padding: 7px 36px 7px 38px;
    margin: 1px 3px;
    border: 1px solid transparent;
    border-radius: 5px;
}
QMenu::item:selected, QMenu#PyCForgeMenu::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${selection},stop:0.64 ${violet_dim},stop:1 ${surface_hover});
    border: 1px solid ${border_strong};
    border-left: 3px solid ${blue_bright};
}
QMenu::item:pressed, QMenu#PyCForgeMenu::item:pressed {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${blue_dim},stop:0.58 ${violet_dim},stop:1 ${warm_dim});
    border-left: 3px solid ${blue_bright};
    border-bottom: 2px solid ${warm};
}
QMenu::item:disabled, QMenu#PyCForgeMenu::item:disabled {
    color: ${text_disabled}; background: transparent;
    border-color: transparent;
}
QMenu#PyCForgeMenu[pycforgeTone="primary"]::item:selected {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${blue_dim},stop:0.58 ${violet_dim},stop:1 ${warm_dim});
    color: #FFFFFF; border-left: 3px solid ${warm_bright};
}
QMenu#PyCForgeMenu[pycforgeTone="danger"]::item:selected { color: ${error_bright}; background: ${error_dim}; border-left: 3px solid ${error}; }
QMenu::separator { height: 1px; margin: 6px 12px; background: ${border}; }
QMenu::icon { left: 12px; width: 18px; height: 18px; }
QMenu::indicator {
    width: 15px;
    height: 15px;
    left: 12px;
    border: 1px solid ${border_strong};
    border-radius: 4px;
    background: ${canvas};
}
QMenu::indicator:checked {
    image: url("${check_icon}");
    background: ${blue_dim};
    border: 1px solid ${blue_bright};
}
QMenu::right-arrow {
    image: url("${chevron_icon}");
    width: 14px;
    height: 14px;
    right: 10px;
}
QMenu::scroller {
    height: 18px;
    background: ${surface_active};
    border: 1px solid ${border};
}
QToolBar {
    color: ${text};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${surface});
    border: 0;
    border-bottom: 1px solid ${border_strong};
    spacing: 5px;
    padding: 7px 9px;
}
QToolBar::separator { width: 1px; margin: 4px 7px; background: ${border}; }
QPushButton, QToolButton {
    color: ${text_soft};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_hover},stop:1 ${surface_raised});
    border: 1px solid ${border_strong};
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 18px;
}
QPushButton:hover, QToolButton:hover {
    color: #FFFFFF;
    background: ${surface_hover};
    border-color: ${blue};
    border-bottom: 2px solid ${blue};
}
QPushButton:focus, QToolButton:focus {
    color: #FFFFFF;
    border: 1px solid ${focus_ring};
    border-bottom: 2px solid ${violet};
}
QPushButton:pressed, QToolButton:pressed,
QPushButton:checked, QToolButton:checked {
    color: #FFFFFF;
    background: ${blue_dim};
    border-color: ${blue};
    border-bottom: 2px solid ${warm};
}
QPushButton:disabled, QToolButton:disabled {
    color: ${text_disabled};
    background: ${surface};
    border-color: ${border};
}
QPushButton[role="primary"], QToolButton[role="primary"] {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${selection_active},stop:0.7 ${violet_dim},stop:1 ${warm_dim});
    border-color: ${blue_bright};
    font-weight: 600;
}
QPushButton[role="danger"], QToolButton[role="danger"] {
    color: ${error_bright}; background: ${error_dim}; border-color: ${error};
}
QToolButton#IconButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 2px;
    border-radius: 6px;
}
QPlainTextEdit, QTextEdit, QLineEdit, QSpinBox, QComboBox {
    color: ${text};
    background: ${canvas};
    border: 1px solid ${border};
    border-radius: 6px;
    padding: 5px 7px;
}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus,
QSpinBox:focus, QComboBox:focus {
    background: ${surface};
    border: 1px solid ${blue};
    border-bottom: 2px solid ${violet};
}
QPlainTextEdit:read-only, QTextEdit:read-only {
    color: ${text_soft};
    background: ${void};
    border-color: ${border};
}
QLineEdit[state="error"], QPlainTextEdit[state="error"] {
    border: 1px solid ${error};
    border-bottom: 2px solid ${error};
    background: ${error_dim};
}
QLineEdit[state="warning"], QPlainTextEdit[state="warning"] {
    border: 1px solid ${warning};
    border-bottom: 2px solid ${warning};
    background: ${warning_dim};
}
QLineEdit[state="success"], QPlainTextEdit[state="success"] {
    border: 1px solid ${success};
    border-bottom: 2px solid ${success};
    background: ${success_dim};
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
QComboBox:disabled, QSpinBox:disabled {
    color: ${text_disabled};
    background: ${surface};
    border-color: ${border};
}
QLineEdit#NavigatorFilter {
    background: ${void}; border-bottom: 2px solid ${blue_dim};
}
QWidget#findReplaceBar, QFrame#findReplaceBar,
QWidget[role="find-bar"], QFrame[role="find-bar"] {
    color: ${text};
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${surface},stop:0.72 ${surface_raised},stop:1 ${violet_dim});
    border: 1px solid ${border_strong};
    border-bottom: 2px solid ${warm_dim};
    border-radius: 7px;
}
QListWidget#DocumentList {
    color: ${text_soft};
    background: ${void};
    border: 1px solid ${border};
    border-radius: 6px;
    outline: 0;
    padding: 3px;
}
QListWidget#DocumentList:focus {
    border: 1px solid ${blue}; border-bottom: 2px solid ${violet};
}
QListWidget#DocumentList::item {
    border: 1px solid transparent;
    border-bottom: 1px solid ${surface_raised};
    border-radius: 5px;
    padding: 8px 7px;
    margin: 1px 0;
}
QListWidget#DocumentList::item:hover {
    color: #FFFFFF;
    background: ${surface_hover};
    border-color: ${border_strong};
}
QListWidget#DocumentList::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${selection},stop:1 ${violet_dim});
    border: 1px solid ${blue};
    border-left: 3px solid ${blue_bright};
}
QListWidget#DocumentList::item:disabled {
    color: ${text_disabled}; background: ${surface};
}
QTabWidget::pane {
    background: ${surface};
    border: 1px solid ${border};
    border-top: 1px solid ${border_strong};
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    color: ${text_muted};
    background: ${canvas};
    border: 1px solid ${border};
    border-bottom: 1px solid ${border_strong};
    padding: 8px 13px;
    min-width: 72px;
}
QTabBar::tab:hover {
    color: ${text};
    background: ${surface_active};
    border-bottom: 2px solid ${blue};
}
QTabBar::tab:selected {
    color: #FFFFFF;
    background: ${surface_hover};
    border-color: ${border_strong};
    border-bottom: 2px solid ${violet};
}
QTabBar::tab:disabled { color: ${text_disabled}; background: ${canvas}; }
QSplitter::handle { background: ${surface_raised}; border: 0; }
QSplitter::handle:horizontal {
    width: 5px;
    border-left: 1px solid ${border};
    border-right: 1px solid ${blue_dim};
}
QSplitter::handle:vertical {
    height: 5px;
    border-top: 1px solid ${border};
    border-bottom: 1px solid ${blue_dim};
}
QSplitter::handle:hover { background: ${border_strong}; }
QTreeView, QListView, QTableView {
    color: ${text_soft};
    background: ${canvas};
    alternate-background-color: ${surface};
    border: 1px solid ${border};
    gridline-color: ${border};
    outline: 0;
}
QTreeView:focus, QListView:focus, QTableView:focus {
    border: 1px solid ${blue}; border-bottom: 2px solid ${violet};
}
QWidget#DiagnosticsView, QWidget#MappingsView, QWidget#InspectorTree {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${canvas});
    border: 0;
}
QWidget#DiagnosticsView QLineEdit,
QWidget#MappingsView QLineEdit,
QWidget#InspectorTree QLineEdit {
    background: ${void};
    border-color: ${border_strong};
    border-bottom: 2px solid ${blue_dim};
}
QWidget#DiagnosticsView QLineEdit:focus,
QWidget#MappingsView QLineEdit:focus,
QWidget#InspectorTree QLineEdit:focus {
    border-color: ${blue};
    border-bottom: 2px solid ${violet};
}
QTreeWidget#DiagnosticsTree, QTreeWidget#MappingsTree,
QWidget#InspectorTree QTreeWidget {
    background: ${void};
    border: 1px solid ${border};
    border-radius: 6px;
}
QTreeWidget#DiagnosticsTree:focus,
QTreeWidget#MappingsTree:focus,
QWidget#InspectorTree QTreeWidget:focus {
    border: 1px solid ${blue};
    border-bottom: 2px solid ${violet};
}
QTextBrowser#DiagnosticDetails {
    color: ${text_soft};
    background: ${surface};
    border: 1px solid ${border_strong};
    border-left: 2px solid ${violet};
    border-radius: 6px;
    padding: 7px;
}
QTreeView::item, QListView::item, QTableView::item { padding: 4px; }
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {
    color: #FFFFFF; background: ${surface_hover};
}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {
    color: #FFFFFF;
    background: ${selection};
    border-left: 2px solid ${blue_bright};
}
QTreeView:focus::item:selected,
QListView:focus::item:selected,
QTableView:focus::item:selected {
    border: 1px solid ${focus_ring};
    border-left: 3px solid ${violet};
}
QHeaderView::section {
    color: ${text_soft};
    background: ${surface_raised};
    border: 0;
    border-right: 1px solid ${border};
    border-bottom: 1px solid ${border_strong};
    padding: 6px 8px;
}
QScrollBar:vertical { background: ${canvas}; width: 12px; margin: 1px; }
QScrollBar:horizontal { background: ${canvas}; height: 12px; margin: 1px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: ${border_strong};
    border: 1px solid ${text_disabled};
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: ${selection_active}; border-color: ${blue};
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
    border: none;
    width: 0;
    height: 0;
}
QStatusBar {
    color: ${text_soft};
    background: ${canvas};
    border-top: 1px solid ${border_strong};
}
QStatusBar::item { border: 0; }
QProgressBar {
    color: ${text};
    background: ${void};
    border: 1px solid ${border};
    border-radius: 6px;
    text-align: center;
    min-height: 16px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${blue},stop:0.62 ${violet},stop:1 ${warm});
    border-radius: 5px;
}
QCheckBox, QRadioButton { color: ${text_soft}; spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 15px;
    height: 15px;
    background: ${canvas};
    border: 1px solid ${border_strong};
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: ${selection}; border: 2px solid ${blue};
}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {
    border-color: ${focus_ring};
}
QToolTip {
    color: #FFFFFF;
    background: ${surface_active};
    border: 1px solid ${blue};
    padding: 5px 7px;
}
QDockWidget {
    color: ${text}; titlebar-close-icon: none; titlebar-normal-icon: none;
}
QDockWidget::title {
    color: ${text_soft};
    background: ${surface_raised};
    border-bottom: 1px solid ${border_strong};
    padding: 6px;
}
QMainWindow[visualMode="high-contrast"],
QDialog[visualMode="high-contrast"] { background: ${void}; }
QWidget[visualMode="high-contrast"] QMenu,
QWidget[visualMode="high-contrast"] QToolButton,
QWidget[visualMode="high-contrast"] QPushButton,
QWidget[visualMode="high-contrast"] QLineEdit,
QWidget[visualMode="high-contrast"] QPlainTextEdit,
QWidget[visualMode="high-contrast"] QTreeView,
QWidget[visualMode="high-contrast"] QListView {
    border-color: ${text_muted};
}
QWidget[visualMode="high-contrast"] QMenu::item:selected,
QWidget[visualMode="high-contrast"] QTreeView::item:selected,
QWidget[visualMode="high-contrast"] QListView::item:selected {
    color: #FFFFFF;
    background: ${selection_active};
    border: 2px solid ${focus_ring};
}
"""
)


def build_pycforge_stylesheet(
    colors: PyCForgeColors = PYCFORGE_COLORS,
) -> str:
    """Return the complete deterministic stylesheet for *colors*."""

    values = dict(color_tokens(colors))
    values.update(
        {
            "check_icon": pycforge_icon_path("check").as_posix(),
            "chevron_icon": pycforge_icon_path(
                "chevron-right"
            ).as_posix(),
        }
    )
    foundation = _PYCFORGE_QSS_TEMPLATE.substitute(values).strip()
    workspace = build_workspace_stylesheet(colors).strip()
    return foundation + "\n" + workspace + "\n"


__all__ = ["build_pycforge_stylesheet"]
