"""Phase 15C editor-workspace additions to the PyCForge visual system."""

from __future__ import annotations

from string import Template

from .visual_tokens import (
    PYCFORGE_COLORS,
    PyCForgeColors,
    color_tokens,
)


_WORKSPACE_QSS = Template(
    r"""
QTabBar#SourceDocumentTabs {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${void},stop:0.55 ${canvas},stop:1 ${surface_raised});
    border: 1px solid ${border};
    border-bottom: 1px solid ${border_strong};
    border-radius: 7px;
    padding: 3px 4px 0 4px;
}
QTabBar#SourceDocumentTabs::tab {
    color: ${text_soft};
    background: ${surface};
    border: 1px solid ${border};
    border-bottom: 2px solid ${border};
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 12px;
    min-width: 110px;
}
QTabBar#SourceDocumentTabs::tab:hover {
    color: #FFFFFF;
    background: ${surface_hover};
    border-bottom: 2px solid ${blue};
}
QTabBar#SourceDocumentTabs::tab:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${selection},stop:0.75 ${violet_dim},stop:1 ${warm_dim});
    border-color: ${blue};
    border-bottom: 2px solid ${violet_bright};
}
QTabBar#SourceDocumentTabs:focus {
    border: 1px solid ${focus_ring};
    border-bottom: 2px solid ${violet};
}
QWidget#SourceBreadcrumbBar {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${canvas},stop:0.72 ${surface},stop:1 ${violet_dim});
    border: 1px solid ${border};
    border-left: 2px solid ${blue};
    border-radius: 6px;
}
QToolButton#BreadcrumbButton {
    color: ${text_soft};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 3px 7px;
}
QToolButton#BreadcrumbButton:hover {
    color: #FFFFFF;
    background: ${surface_hover};
    border-color: ${blue_dim};
}
QToolButton#BreadcrumbButton:focus {
    color: #FFFFFF;
    border: 1px solid ${focus_ring};
    background: ${selection};
}
QLabel#BreadcrumbSeparator {
    color: ${violet_bright};
    padding: 0 1px;
}
QDialog#CommandPaletteDialog {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:0.55 ${canvas},stop:1 ${void});
    border: 1px solid ${blue};
    border-radius: 10px;
}
QLineEdit#CommandPaletteQuery {
    color: #FFFFFF;
    background: ${void};
    border: 1px solid ${blue};
    border-bottom: 2px solid ${violet};
    border-radius: 8px;
    padding: 9px 11px;
}
QTreeWidget#CommandPaletteResults,
QTreeWidget#BundleSearchTree,
QTreeWidget#OutlineTree,
QTreeWidget#SessionHistoryTree {
    color: ${text_soft};
    background: ${void};
    border: 1px solid ${border_strong};
    border-radius: 7px;
}
QTreeWidget#CommandPaletteResults::item,
QTreeWidget#BundleSearchTree::item,
QTreeWidget#OutlineTree::item,
QTreeWidget#SessionHistoryTree::item {
    border-bottom: 1px solid ${surface_raised};
    padding: 6px 5px;
}
QTreeWidget#CommandPaletteResults::item:hover,
QTreeWidget#BundleSearchTree::item:hover,
QTreeWidget#OutlineTree::item:hover,
QTreeWidget#SessionHistoryTree::item:hover {
    color: #FFFFFF;
    background: ${surface_hover};
}
QTreeWidget#CommandPaletteResults::item:selected,
QTreeWidget#BundleSearchTree::item:selected,
QTreeWidget#OutlineTree::item:selected,
QTreeWidget#SessionHistoryTree::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 ${selection},stop:1 ${violet_dim});
    border-left: 3px solid ${blue_bright};
}
QWidget#BundleSearchView,
QWidget#OutlineView,
QWidget#SessionHistoryView {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 ${surface_raised},stop:1 ${canvas});
}
QFrame#SourceSplitSurface {
    background: ${void};
    border: 1px solid ${border};
    border-top: 2px solid ${blue_dim};
    border-radius: 7px;
}
QLabel#GeneratedCWindowLabel {
    color: ${warning_bright};
    background: ${warning_dim};
    border: 1px solid ${warm_dim};
    border-radius: 7px;
    padding: 3px 8px;
}
"""
)


def build_workspace_stylesheet(
    colors: PyCForgeColors = PYCFORGE_COLORS,
) -> str:
    """Return deterministic styling for the Phase 15C workspace surfaces."""

    return _WORKSPACE_QSS.substitute(dict(color_tokens(colors))).strip() + "\n"


__all__ = ["build_workspace_stylesheet"]
