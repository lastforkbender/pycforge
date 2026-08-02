"""Construction helpers for split source and tabbed generated-C surfaces."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
)

from .editor import CodeEditor


def build_source_editor_surface(owner) -> QFrame:
    """Build the primary and optional synchronized Python source views."""

    panel = QFrame()
    panel.setObjectName("SourceEditorSurface")
    panel.setProperty("role", "source-surface")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    owner.source_splitter = QSplitter(Qt.Horizontal)
    owner.source_splitter.setObjectName("PythonSourceViewSplitter")
    owner.source_splitter.setChildrenCollapsible(False)
    owner.source = CodeEditor(language="python")
    owner.source.setObjectName("PythonSourceEditor")
    owner.source.setPlaceholderText(
        "Enter supported Python source, or open a source "
        "bundle document…"
    )
    owner.source.setAccessibleName("Primary Python source editor")
    owner.source_secondary = CodeEditor(
        language="python",
        highlighting=False,
    )
    owner.source_secondary.setObjectName("PythonSourceEditorSecondary")
    owner.source_secondary.setAccessibleName(
        "Secondary synchronized Python source editor"
    )
    owner.source_secondary.setAccessibleDescription(
        "A second view of the same active Python source document."
    )
    owner.source_secondary.setVisible(False)
    owner.source_splitter.addWidget(owner.source)
    owner.source_splitter.addWidget(owner.source_secondary)
    owner.source_splitter.setStretchFactor(0, 1)
    owner.source_splitter.setStretchFactor(1, 1)
    layout.addWidget(owner.source_splitter)
    return panel


def build_generated_c_surface(owner) -> QFrame:
    """Build one explicit read-only generated-C editor tab."""

    panel = QFrame()
    panel.setObjectName("GeneratedCPanel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    header = QHBoxLayout()
    title = QLabel("GENERATED C  ·  READ ONLY")
    title.setProperty("role", "panel-title")
    owner.output_state_label = QLabel("NO RESULT")
    owner.output_state_label.setProperty("role", "status-chip")
    owner.output_state_label.setProperty("status", "neutral")
    owner.linked_c_label = QLabel("C link: not set")
    owner.linked_c_label.setObjectName("PathLabel")
    owner.linked_c_label.setToolTip("Linked destination used by Save C")
    owner.linked_c_label.setMinimumWidth(0)
    owner.linked_c_label.setSizePolicy(
        QSizePolicy.Ignored,
        QSizePolicy.Preferred,
    )
    header.addWidget(title)
    header.addStretch(1)
    layout.addLayout(header)
    link_row = QHBoxLayout()
    link_row.addWidget(owner.output_state_label)
    link_row.addWidget(owner.linked_c_label, 1)
    layout.addLayout(link_row)

    owner.output_tabs = QTabWidget()
    owner.output_tabs.setObjectName("GeneratedCEditorTabs")
    owner.output_tabs.setDocumentMode(True)
    owner.output_tabs.setTabsClosable(True)
    owner.output_tabs.setAccessibleName("Generated C read-only tabs")
    owner.output = CodeEditor(language="c")
    owner.output.setObjectName("GeneratedCEditor")
    owner.output.setReadOnly(True)
    owner.output.setAccessibleName("Generated C read-only viewer")
    owner.output.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    owner.output_tabs.addTab(owner.output, "generated.c")
    owner.output_tabs.tabCloseRequested.connect(
        lambda _index: owner._set_output_visible(False)
    )
    layout.addWidget(owner.output_tabs, 1)
    panel.setVisible(False)
    return panel


__all__ = [
    "build_generated_c_surface",
    "build_source_editor_surface",
]
