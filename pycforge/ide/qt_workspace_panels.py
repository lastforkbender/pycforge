"""Qt panels for bounded Phase 15C workspace observers.

This module intentionally imports PyQt directly. The desktop entry point
imports it only after its existing ``QT_AVAILABLE`` gate succeeds.
"""

from __future__ import annotations

from itertools import islice
from typing import Iterable
from weakref import finalize

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .session_history import (
    MAX_CONVERSION_HISTORY_ENTRIES,
    ConversionHistoryEntry,
)
from .source_structure import (
    MAX_OUTLINE_SYMBOLS,
    SourceStructureResult,
)
from .workspace_search import (
    MAX_BUNDLE_DOCUMENTS,
    MAX_QUERY_CHARS,
    AsyncBundleSearchService,
    BundleSearchResult,
    WorkspaceSearchDocument,
)


def _status_label(name: str) -> QLabel:
    label = QLabel("No data")
    label.setObjectName("MutedLabel")
    label.setAccessibleName(name)
    return label


class OutlineView(QWidget):
    """Bounded hierarchy projected from one inert structure result."""

    symbolActivated = pyqtSignal(str, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OutlineView")
        self.setAccessibleName("Python source outline")
        self._rows: tuple[tuple[QTreeWidgetItem, int], ...] = ()

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filter source outline…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setAccessibleName("Filter Python source outline")
        self.status_label = _status_label("Source outline status")
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("OutlineTree")
        self.tree.setAccessibleName("Python source symbols")
        self.tree.setAccessibleDescription(
            "Symbols derived only from already-open normalized Python syntax."
        )
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(("Symbol", "Kind", "Location"))
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)

        header = QHBoxLayout()
        header.addWidget(self.filter_edit, 1)
        header.addWidget(self.status_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.tree, 1)

        self.filter_edit.textChanged.connect(self._filter)
        self.tree.itemActivated.connect(self._activate)

    def set_result(self, result: SourceStructureResult | None) -> None:
        """Replace the tree without retaining normalized source payloads."""

        self.tree.clear()
        self._rows = ()
        if result is None:
            self.status_label.setText("No outline")
            return
        if not isinstance(result, SourceStructureResult):
            raise TypeError("outline result has the wrong type")

        symbols = result.symbols[:MAX_OUTLINE_SYMBOLS]
        items: dict[str, QTreeWidgetItem] = {}
        pending: list[tuple[object, QTreeWidgetItem]] = []
        for symbol in symbols:
            if symbol.node_id in items:
                continue
            location = (
                f"{symbol.logical_name}:{symbol.start_line}:"
                f"{symbol.start_column + 1}"
            )
            item = QTreeWidgetItem(
                (symbol.name, symbol.detail, location)
            )
            item.setData(
                0,
                Qt.UserRole,
                (
                    symbol.document_id,
                    symbol.start,
                    symbol.end,
                    symbol.node_id,
                ),
            )
            item.setData(
                0,
                Qt.AccessibleTextRole,
                (
                    f"{symbol.name}, {symbol.detail}, "
                    f"{location}"
                ),
            )
            items[symbol.node_id] = item
            pending.append((symbol, item))

        rows: list[tuple[QTreeWidgetItem, int]] = []
        for symbol, item in pending:
            parent_item = (
                items.get(symbol.parent_node_id)
                if symbol.parent_node_id is not None
                else None
            )
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            rows.append((item, symbol.depth))
        self._rows = tuple(rows)
        self.tree.expandToDepth(1)
        notices: list[str] = []
        if result.invalid_document_ids:
            notices.append(
                f"{len(result.invalid_document_ids)} invalid"
            )
        if result.observer_failed_document_ids:
            notices.append(
                f"{len(result.observer_failed_document_ids)} unavailable"
            )
        truncated = (
            result.truncated
            or len(result.symbols) > MAX_OUTLINE_SYMBOLS
        )
        if truncated:
            notices.append("bounded view")
        suffix = f" · {', '.join(notices)}" if notices else ""
        self.status_label.setText(
            f"{len(symbols)} symbol"
            f"{'' if len(symbols) == 1 else 's'}{suffix}"
        )
        self.status_label.setAccessibleDescription(
            self.status_label.text()
        )
        self._filter(self.filter_edit.text())

    def _filter(self, value: str) -> None:
        needle = value.casefold().strip()
        if not needle:
            for item, _depth in self._rows:
                item.setHidden(False)
            return
        # Depth ordering ensures descendants publish visibility first.
        for item, _depth in sorted(
            self._rows, key=lambda row: row[1], reverse=True
        ):
            own = needle in " ".join(
                item.text(column)
                for column in range(item.columnCount())
            ).casefold()
            child_visible = any(
                not item.child(index).isHidden()
                for index in range(item.childCount())
            )
            item.setHidden(not (own or child_visible))

    def _activate(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        data = item.data(0, Qt.UserRole)
        if (
            isinstance(data, tuple)
            and len(data) == 4
            and isinstance(data[0], str)
            and isinstance(data[1], int)
            and isinstance(data[2], int)
        ):
            self.symbolActivated.emit(data[0], data[1], data[2])


class BundleSearchView(QWidget):
    """Debounced, generation-safe literal search over captured documents."""

    matchActivated = pyqtSignal(str, int, int)
    _searchCompleted = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BundleSearchView")
        self.setAccessibleName("Search open source bundle")
        self._documents: tuple[WorkspaceSearchDocument, ...] = ()
        self._document_key: tuple[tuple[str, str, int], ...] = ()
        self._expected_generation: int | None = None
        self._search_service = AsyncBundleSearchService()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)

        self.query_edit = QLineEdit(self)
        self.query_edit.setObjectName("BundleSearchQuery")
        self.query_edit.setPlaceholderText("Search open Python documents…")
        self.query_edit.setClearButtonEnabled(True)
        self.query_edit.setMaxLength(MAX_QUERY_CHARS)
        self.query_edit.setAccessibleName("Bundle-wide literal search")
        self.match_case = QCheckBox("Match case", self)
        self.match_case.setAccessibleName("Match search case")
        self.whole_word = QCheckBox("Whole word", self)
        self.whole_word.setAccessibleName("Match whole source word")
        self.status_label = _status_label("Bundle search status")

        controls = QHBoxLayout()
        controls.addWidget(self.query_edit, 1)
        controls.addWidget(self.match_case)
        controls.addWidget(self.whole_word)
        controls.addWidget(self.status_label)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("BundleSearchTree")
        self.tree.setAccessibleName("Bundle search results")
        self.tree.setAccessibleDescription(
            "Bounded literal matches from explicitly open documents only."
        )
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(("Source", "Offsets", "Preview"))
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(controls)
        layout.addWidget(self.tree, 1)

        self.query_edit.textChanged.connect(self._schedule_search)
        self.match_case.toggled.connect(self._schedule_search)
        self.whole_word.toggled.connect(self._schedule_search)
        self._search_timer.timeout.connect(self._submit_search)
        self._searchCompleted.connect(self._apply_result)
        self.tree.itemActivated.connect(self._activate)
        search_service = self._search_service
        self._search_service_finalizer = finalize(
            self,
            search_service.close,
        )

    def set_documents(self, documents: Iterable[object]) -> None:
        """Capture exact snapshot strings without reading linked paths."""

        records = tuple(islice(documents, MAX_BUNDLE_DOCUMENTS + 1))
        if len(records) > MAX_BUNDLE_DOCUMENTS:
            raise ValueError("bundle search accepts at most 64 documents")
        captured: list[WorkspaceSearchDocument] = []
        for record in records:
            document_id = getattr(record, "document_id", None)
            logical_name = getattr(record, "logical_name", None)
            text = getattr(record, "text", None)
            if not all(
                isinstance(value, str)
                for value in (document_id, logical_name, text)
            ):
                raise TypeError(
                    "bundle search requires snapshot document values"
                )
            if not document_id or not logical_name:
                raise ValueError(
                    "bundle search document identities must be non-empty"
                )
            captured.append(
                WorkspaceSearchDocument(
                    document_id, logical_name, text
                )
            )
        document_ids = [item.document_id for item in captured]
        logical_names = [item.logical_name for item in captured]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("bundle search document IDs must be unique")
        if len(logical_names) != len(set(logical_names)):
            raise ValueError("bundle search logical names must be unique")
        key = tuple(
            (
                item.document_id,
                item.logical_name,
                id(item.text),
            )
            for item in captured
        )
        if key == self._document_key:
            return
        self._document_key = key
        self._documents = tuple(captured)
        self._schedule_search()

    def _invalidate_search(self) -> None:
        self._search_timer.stop()
        self._search_service.cancel()
        self._expected_generation = None
        self.tree.clear()

    def invalidate_results(self) -> None:
        """Clear captured source and matches while an editor sync is pending."""

        self._invalidate_search()
        self._documents = ()
        self._document_key = ()
        self.status_label.setText("Waiting for source synchronization")

    def _schedule_search(self, *_args) -> None:
        self._invalidate_search()
        if not self.query_edit.text():
            self.status_label.setText("Enter literal text")
            return
        if not self._documents:
            self.status_label.setText("No open documents")
            return
        self.status_label.setText("Waiting…")
        self._search_timer.start()

    def _submit_search(self) -> None:
        if not self.query_edit.text() or not self._documents:
            return
        self.status_label.setText("Searching…")
        self._expected_generation = self._search_service.submit(
            self._documents,
            self.query_edit.text(),
            match_case=self.match_case.isChecked(),
            whole_word=self.whole_word.isChecked(),
            callback=self._searchCompleted.emit,
        )

    def _apply_result(self, result: BundleSearchResult) -> None:
        if (
            not isinstance(result, BundleSearchResult)
            or result.generation != self._expected_generation
        ):
            return
        self.tree.clear()
        for match in result.matches:
            item = QTreeWidgetItem(
                (
                    match.logical_name,
                    f"{match.start}:{match.end}",
                    match.preview,
                )
            )
            item.setData(
                0,
                Qt.UserRole,
                (
                    match.document_id,
                    match.qt_start,
                    match.qt_end,
                ),
            )
            item.setData(
                0,
                Qt.AccessibleTextRole,
                (
                    f"{match.logical_name}, offsets "
                    f"{match.start} to {match.end}, {match.preview}"
                ),
            )
            self.tree.addTopLevelItem(item)
        if result.truncated:
            label = (
                f"{len(result.matches)} shown · at least "
                f"{result.total_count} matches"
            )
        else:
            label = (
                f"{result.total_count} match"
                f"{'' if result.total_count == 1 else 'es'}"
            )
        self.status_label.setText(label)
        self.status_label.setAccessibleDescription(label)

    def _activate(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        data = item.data(0, Qt.UserRole)
        if (
            isinstance(data, tuple)
            and len(data) == 3
            and isinstance(data[0], str)
            and isinstance(data[1], int)
            and isinstance(data[2], int)
        ):
            self.matchActivated.emit(data[0], data[1], data[2])

    def close_service(self) -> None:
        self._search_timer.stop()
        self._expected_generation = None
        self._search_service.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.close_service()
        super().closeEvent(event)


class SessionHistoryView(QWidget):
    """Payload-free projection of at most 64 immutable terminal entries."""

    historyActivated = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SessionHistoryView")
        self.setAccessibleName("Current session transpilation history")
        self.status_label = _status_label("Session history status")
        self.tree = QTreeWidget(self)
        self.tree.setObjectName("SessionHistoryTree")
        self.tree.setAccessibleName("Current session transpilation entries")
        self.tree.setAccessibleDescription(
            "Bounded terminal summaries with no source or generated payload."
        )
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            (
                "Request",
                "Status",
                "Stages",
                "Diagnostics",
                "Publication",
                "Output",
            )
        )
        self.tree.setUniformRowHeights(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.status_label)
        layout.addWidget(self.tree, 1)
        self.tree.itemActivated.connect(self._activate)

    def set_entries(
        self,
        entries: Iterable[ConversionHistoryEntry],
    ) -> None:
        records = tuple(
            islice(entries, MAX_CONVERSION_HISTORY_ENTRIES + 1)
        )
        if len(records) > MAX_CONVERSION_HISTORY_ENTRIES:
            raise ValueError("session history exceeds the 64-entry limit")
        if any(
            not isinstance(entry, ConversionHistoryEntry)
            for entry in records
        ):
            raise TypeError(
                "session history requires immutable history entries"
            )
        self.tree.clear()
        for entry in reversed(records):
            stages = (
                f"{entry.completed_stage_count}/"
                f"{entry.total_stage_count}"
            )
            output = (
                entry.output_fingerprint[:12]
                if entry.output_fingerprint is not None
                else "—"
            )
            item = QTreeWidgetItem(
                (
                    str(entry.request_sequence),
                    entry.status,
                    stages,
                    str(entry.diagnostic_count),
                    "Published" if entry.published else "Not published",
                    output,
                )
            )
            item.setData(
                0, Qt.UserRole, entry.request_sequence
            )
            item.setData(
                0,
                Qt.AccessibleTextRole,
                (
                    f"Request {entry.request_sequence}, {entry.status}, "
                    f"{stages} stages, "
                    f"{entry.diagnostic_count} diagnostics, "
                    f"{'published' if entry.published else 'not published'}"
                ),
            )
            tooltip = (
                f"Bundle {entry.bundle_fingerprint}\n"
                f"Reason: {entry.reason or 'terminal result'}"
            )
            item.setToolTip(0, tooltip)
            self.tree.addTopLevelItem(item)
        label = (
            f"{len(records)} session entr"
            f"{'y' if len(records) == 1 else 'ies'}"
        )
        self.status_label.setText(label)
        self.status_label.setAccessibleDescription(label)

    def _activate(
        self,
        item: QTreeWidgetItem,
        _column: int,
    ) -> None:
        sequence = item.data(0, Qt.UserRole)
        if isinstance(sequence, int) and not isinstance(sequence, bool):
            self.historyActivated.emit(sequence)


__all__ = [
    "BundleSearchView",
    "OutlineView",
    "SessionHistoryView",
]
