"""Focused Qt widgets for the Phase 15C PyCForge editor workspace."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTabBar,
    QToolButton,
    QWidget,
)

from .icons import pycforge_icon_path


class DocumentTabBar(QTabBar):
    """Bounded tab projection of the explicit open SourceBundle."""

    document_selected = pyqtSignal(str)
    close_requested = pyqtSignal(str)
    order_requested = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SourceDocumentTabs")
        self.setAccessibleName("Open Python source documents")
        self.setAccessibleDescription(
            "Tabs for the explicit Python documents already in the source "
            "bundle. Closing a tab requests removal from that bundle."
        )
        self.setDocumentMode(True)
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideMiddle)
        self.setFocusPolicy(Qt.StrongFocus)
        self._updating = False
        self._document_key: tuple[tuple[object, ...], ...] = ()
        self.currentChanged.connect(self._selected)
        self.tabCloseRequested.connect(self._close)
        self.tabMoved.connect(self._moved)
        self.customContextMenuRequested.connect(
            self._select_context_tab
        )

    @property
    def current_document_id(self) -> str | None:
        index = self.currentIndex()
        if index < 0:
            return None
        value = self.tabData(index)
        return str(value) if value else None

    def document_id_at(self, index: int) -> str | None:
        if not 0 <= index < self.count():
            return None
        value = self.tabData(index)
        return str(value) if value else None

    def set_documents(
        self,
        documents: Iterable[Any],
        active_document_id: str,
    ) -> None:
        records = tuple(documents)
        key = tuple(
            (
                item.document_id,
                item.module_id,
                item.logical_name,
                item.path,
                item.is_primary,
                item.dirty,
            )
            for item in records
        )
        if (
            self._document_key == key
            and self.current_document_id == active_document_id
        ):
            return
        self._updating = True
        self.blockSignals(True)
        try:
            while self.count():
                self.removeTab(0)
            selected = 0
            for index, document in enumerate(records):
                label = document.logical_name.rsplit("/", 1)[-1]
                if document.dirty:
                    label += "  •"
                tab = self.addTab(
                    QIcon(
                        str(
                            pycforge_icon_path(
                                "primary-module"
                                if document.is_primary
                                else "module"
                            )
                        )
                    ),
                    label,
                )
                self.setTabData(tab, document.document_id)
                state = []
                if document.is_primary:
                    state.append("primary")
                if document.dirty:
                    state.append("modified")
                detail = ", ".join(state) if state else "saved"
                self.setTabToolTip(
                    tab,
                    f"{document.module_id}\n{document.logical_name}\n"
                    f"{document.path or 'Unsaved document'}\n{detail}",
                )
                self.setTabWhatsThis(
                    tab,
                    f"Python source module {document.module_id}; {detail}.",
                )
                if document.document_id == active_document_id:
                    selected = index
            self.setCurrentIndex(selected)
            self._document_key = key
        finally:
            self.blockSignals(False)
            self._updating = False
        self.update()

    def _selected(self, index: int) -> None:
        if self._updating:
            return
        document_id = self.document_id_at(index)
        if document_id is not None:
            self.document_selected.emit(document_id)

    def _close(self, index: int) -> None:
        document_id = self.document_id_at(index)
        if document_id is not None:
            self.close_requested.emit(document_id)

    def _moved(self, _source: int, _destination: int) -> None:
        if self._updating:
            return
        order = tuple(
            document_id
            for index in range(self.count())
            if (document_id := self.document_id_at(index)) is not None
        )
        self.order_requested.emit(order)

    def _select_context_tab(self, position) -> None:
        index = self.tabAt(position)
        if index >= 0 and index != self.currentIndex():
            self.setCurrentIndex(index)


class BreadcrumbBar(QWidget):
    """Compact, keyboard-reachable path through the active source outline."""

    location_requested = pyqtSignal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SourceBreadcrumbBar")
        self.setAccessibleName("Python source breadcrumbs")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 0, 2, 0)
        self._layout.setSpacing(2)
        self._placeholder = QLabel("No source symbol at the cursor")
        self._placeholder.setObjectName("MutedLabel")
        self._layout.addWidget(self._placeholder)
        self._layout.addStretch(1)

    def set_locations(
        self,
        logical_name: str,
        locations: Iterable[Any],
    ) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        records = tuple(locations)[-16:]
        entries = ((logical_name, 1, 0, "document"),) + tuple(
            (
                str(getattr(item, "name", "symbol")),
                int(getattr(item, "line", 1)),
                int(getattr(item, "column", 0)),
                str(getattr(item, "kind", "symbol")),
            )
            for item in records
        )
        for index, (label, line, column, kind) in enumerate(entries):
            button = QToolButton(self)
            button.setObjectName("BreadcrumbButton")
            button.setAutoRaise(True)
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setToolTip(
                f"{kind.replace('_', ' ').title()} at line {line}"
            )
            button.setAccessibleName(
                f"{label}, {kind.replace('_', ' ')}, line {line}"
            )
            button.clicked.connect(
                lambda _checked=False, row=line, col=column:
                self.location_requested.emit(row, col)
            )
            self._layout.insertWidget(self._layout.count() - 1, button)
            if index < len(entries) - 1:
                separator = QLabel("›")
                separator.setObjectName("BreadcrumbSeparator")
                separator.setAccessibleName("then")
                self._layout.insertWidget(
                    self._layout.count() - 1,
                    separator,
                )


__all__ = ["BreadcrumbBar", "DocumentTabBar"]
