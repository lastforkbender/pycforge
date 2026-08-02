"""PyCForge workspace navigation and inspection panels.

The module remains import-safe if the required PyQt5 dependency is missing from
a damaged installation. The headless controller remains the product boundary;
these widgets only project immutable workspace snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Any, Iterable

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtGui import QBrush, QColor, QIcon
    from PyQt5.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QSizePolicy,
        QTextBrowser,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except (ImportError, ModuleNotFoundError) as exc:
    QT_AVAILABLE = False
    _QT_ERROR = exc
else:
    QT_AVAILABLE = True
    _QT_ERROR = None

from .theme import pycforge_icon_path
from .visual_tokens import PYCFORGE_COLORS


INSPECTOR_TREE_MAX_NODES = 1024
INSPECTOR_TREE_MAX_DEPTH = 16
INSPECTOR_TREE_MAX_CHILDREN = 256
INSPECTOR_TREE_MAX_TEXT_CHARS = 2048


@dataclass(frozen=True)
class InspectorNode:
    """One bounded, parent-indexed row in a structured inspector projection."""

    parent_index: int | None
    key: str
    value: str


def _bounded_inspector_text(value: Any, limit: int) -> str:
    if value is None:
        return "null"
    rendered = value if isinstance(value, str) else str(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[: limit - 1] + "…"


def project_inspector_tree(
    value: Any,
    *,
    max_nodes: int = INSPECTOR_TREE_MAX_NODES,
    max_depth: int = INSPECTOR_TREE_MAX_DEPTH,
    max_children: int = INSPECTOR_TREE_MAX_CHILDREN,
    max_text_chars: int = INSPECTOR_TREE_MAX_TEXT_CHARS,
) -> tuple[InspectorNode, ...]:
    """Return a deterministic structured projection under absolute budgets."""

    if max_nodes < 2:
        raise ValueError("max_nodes must be at least 2")
    if max_depth < 0:
        raise ValueError("max_depth cannot be negative")
    if max_children < 1:
        raise ValueError("max_children must be positive")
    if max_text_chars < 8:
        raise ValueError("max_text_chars must be at least 8")

    # Frames are parent, key, value, depth, and an optional pre-rendered value.
    stack: list[tuple[int | None, str, Any, int, str | None]] = [
        (None, "root", value, 0, None)
    ]
    nodes: list[InspectorNode] = []
    seen_containers: dict[int, int] = {}
    data_node_limit = max_nodes - 1

    while stack and len(nodes) < data_node_limit:
        parent_index, key, current, depth, notice = stack.pop()
        bounded_key = _bounded_inspector_text(key, max_text_chars)
        if notice is not None:
            nodes.append(
                InspectorNode(
                    parent_index,
                    bounded_key,
                    _bounded_inspector_text(notice, max_text_chars),
                )
            )
            continue

        is_mapping = isinstance(current, dict)
        is_sequence = isinstance(current, (list, tuple))
        if not (is_mapping or is_sequence):
            nodes.append(
                InspectorNode(
                    parent_index,
                    bounded_key,
                    _bounded_inspector_text(current, max_text_chars),
                )
            )
            continue

        prior_index = seen_containers.get(id(current))
        if prior_index is not None:
            nodes.append(
                InspectorNode(
                    parent_index,
                    bounded_key,
                    _bounded_inspector_text(
                        f"reference to node {prior_index}",
                        max_text_chars,
                    ),
                )
            )
            continue

        node_index = len(nodes)
        seen_containers[id(current)] = node_index
        total = len(current)
        noun = "fields" if is_mapping else "items"
        depth_limited = depth >= max_depth and total > 0
        child_limited = total > max_children
        detail = f"{total} {noun}"
        if depth_limited:
            detail += " · depth limit reached"
        elif child_limited:
            detail += f" · first {max_children} shown"
        nodes.append(
            InspectorNode(
                parent_index,
                bounded_key,
                _bounded_inspector_text(detail, max_text_chars),
            )
        )
        if depth_limited or not total:
            continue

        if is_mapping:
            selected = list(islice(current.items(), max_children))
            children = [
                (
                    node_index,
                    _bounded_inspector_text(child_key, max_text_chars),
                    child,
                    depth + 1,
                    None,
                )
                for child_key, child in selected
            ]
        else:
            selected = current[:max_children]
            children = [
                (node_index, f"[{index}]", child, depth + 1, None)
                for index, child in enumerate(selected)
            ]
        if child_limited:
            stack.append(
                (
                    node_index,
                    "…",
                    None,
                    depth + 1,
                    f"{total - max_children} additional {noun} not shown",
                )
            )
        stack.extend(reversed(children))

    if stack:
        root_index = 0 if nodes else None
        nodes.append(
            InspectorNode(
                root_index,
                "…",
                _bounded_inspector_text(
                    f"node limit reached · first {data_node_limit} shown",
                    max_text_chars,
                ),
            )
        )
    return tuple(nodes)


if QT_AVAILABLE:
    class DocumentNavigator(QFrame):
        """Bundle document list with exact module/source identity controls."""

        document_selected = pyqtSignal(str)
        add_requested = pyqtSignal()
        remove_requested = pyqtSignal(str)
        move_up_requested = pyqtSignal(str)
        move_down_requested = pyqtSignal(str)
        identity_changed = pyqtSignal(str, str, str)
        identity_pending_changed = pyqtSignal(bool)
        primary_requested = pyqtSignal(str)

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("DocumentNavigator")
            self.setMinimumWidth(230)
            self.setMaximumWidth(360)
            self._document_id: str | None = None
            self._updating = False
            self._identity_baseline: tuple[str, str] | None = None
            self._identity_pending = False

            heading = QLabel("SOURCE BUNDLE")
            heading.setObjectName("PanelEyebrow")
            self.count_label = QLabel("1 / 64")
            self.count_label.setObjectName("MutedLabel")

            self.add_button = QToolButton()
            self.add_button.setObjectName("IconButton")
            self.add_button.setIcon(QIcon(str(pycforge_icon_path("add-document"))))
            self.add_button.setText("")
            self.add_button.setToolTip("Add module document")
            self.add_button.setAccessibleName("Add module document")
            self.remove_button = QToolButton()
            self.remove_button.setObjectName("IconButton")
            self.remove_button.setIcon(
                QIcon(str(pycforge_icon_path("remove-document")))
            )
            self.remove_button.setText("")
            self.remove_button.setToolTip("Remove selected module document")
            self.remove_button.setAccessibleName("Remove selected module document")
            self.move_up_button = QToolButton()
            self.move_up_button.setObjectName("IconButton")
            self.move_up_button.setIcon(QIcon(str(pycforge_icon_path("move-up"))))
            self.move_up_button.setText("")
            self.move_up_button.setToolTip("Move selected module up (Alt+Up)")
            self.move_up_button.setAccessibleName("Move selected module up")
            self.move_up_button.setAccessibleDescription(
                "Moves the selected document one position earlier in the source bundle."
            )
            self.move_up_button.setFocusPolicy(Qt.StrongFocus)
            self.move_down_button = QToolButton()
            self.move_down_button.setObjectName("IconButton")
            self.move_down_button.setIcon(QIcon(str(pycforge_icon_path("move-down"))))
            self.move_down_button.setText("")
            self.move_down_button.setToolTip("Move selected module down (Alt+Down)")
            self.move_down_button.setAccessibleName("Move selected module down")
            self.move_down_button.setAccessibleDescription(
                "Moves the selected document one position later in the source bundle."
            )
            self.move_down_button.setFocusPolicy(Qt.StrongFocus)

            title_row = QHBoxLayout()
            title_row.addWidget(heading)
            title_row.addStretch(1)
            title_row.addWidget(self.count_label)
            title_row.addWidget(self.add_button)
            title_row.addWidget(self.remove_button)

            self.filter_edit = QLineEdit()
            self.filter_edit.setObjectName("NavigatorFilter")
            self.filter_edit.setPlaceholderText("Filter modules…")
            self.filter_edit.setClearButtonEnabled(True)
            self.filter_edit.setAccessibleName("Filter source bundle documents")

            self.documents = QListWidget()
            self.documents.setObjectName("DocumentList")
            self.documents.setSelectionMode(QAbstractItemView.SingleSelection)
            self.documents.setAlternatingRowColors(False)
            self.documents.setMinimumHeight(68)
            self.documents.setAccessibleName("Source bundle documents")
            self.documents.setAccessibleDescription(
                "Select a module document. Use Alt+Up or Alt+Down to change bundle order."
            )

            self.module_edit = QLineEdit()
            self.module_edit.setPlaceholderText("module.id")
            self.module_edit.setAccessibleName("Logical module ID")
            self.logical_edit = QLineEdit()
            self.logical_edit.setPlaceholderText("relative/source.py")
            self.logical_edit.setAccessibleName("Logical source name")
            self.primary_check = QCheckBox("Primary document")
            self.primary_check.setAccessibleName("Make selected document primary")
            self.path_label = QLabel("Unsaved document")
            self.path_label.setObjectName("PathLabel")
            self.path_label.setMinimumWidth(0)
            self.path_label.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.path_label.setToolTip("Unsaved document")

            navigation_row = QHBoxLayout()
            navigation_row.addWidget(self.filter_edit, 1)
            navigation_row.addWidget(self.move_up_button)
            navigation_row.addWidget(self.move_down_button)

            identity_row = QHBoxLayout()
            identity_row.setSpacing(5)
            id_label = QLabel("ID")
            id_label.setObjectName("MutedLabel")
            source_label = QLabel("FILE")
            source_label.setObjectName("MutedLabel")
            identity_row.addWidget(id_label)
            identity_row.addWidget(self.module_edit, 3)
            identity_row.addWidget(source_label)
            identity_row.addWidget(self.logical_edit, 2)

            primary_row = QHBoxLayout()
            primary_row.addWidget(self.primary_check)
            primary_row.addWidget(self.path_label, 1)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 9)
            layout.setSpacing(6)
            layout.addLayout(title_row)
            layout.addLayout(navigation_row)
            layout.addWidget(self.documents, 1)
            layout.addLayout(identity_row)
            layout.addLayout(primary_row)

            self.add_button.clicked.connect(self._request_add)
            self.remove_button.clicked.connect(self._request_remove)
            self.move_up_button.clicked.connect(self._request_move_up)
            self.move_down_button.clicked.connect(self._request_move_down)
            self.documents.currentItemChanged.connect(self._select_item)
            self.filter_edit.textChanged.connect(self._filter)
            self.module_edit.textChanged.connect(
                self._update_identity_pending
            )
            self.logical_edit.textChanged.connect(
                self._update_identity_pending
            )
            self.module_edit.editingFinished.connect(self._emit_identity)
            self.logical_edit.editingFinished.connect(self._emit_identity)
            self.primary_check.clicked.connect(self._request_primary)

        def set_documents(self, documents: Iterable[Any], active_document_id: str | None) -> None:
            records = tuple(documents)
            self._updating = True
            self.documents.clear()
            selected: QListWidgetItem | None = None
            for document in records:
                states = []
                if document.is_primary:
                    states.append("primary")
                if document.dirty:
                    states.append("modified")
                state_text = (
                    " — " + ", ".join(states) if states else ""
                )
                item = QListWidgetItem(
                    f"{document.module_id}{state_text}\n"
                    f"    {document.logical_name}"
                )
                item.setIcon(
                    QIcon(
                        str(
                            pycforge_icon_path(
                                "primary-module"
                                if document.is_primary
                                else "module"
                            )
                        )
                    )
                )
                item.setData(Qt.UserRole, document.document_id)
                item.setData(Qt.UserRole + 1, document)
                item.setData(
                    Qt.AccessibleTextRole,
                    (
                        f"{document.module_id}, {document.logical_name}"
                        + (
                            ", " + ", ".join(states)
                            if states else ""
                        )
                    ),
                )
                item.setToolTip(
                    f"{document.module_id}\n{document.logical_name}\n"
                    f"{document.path or 'Unsaved document'}"
                )
                self.documents.addItem(item)
                if document.document_id == active_document_id:
                    selected = item
            self.count_label.setText(f"{len(records)} / 64")
            self.count_label.setAccessibleName(
                f"{len(records)} source bundle document"
                + ("" if len(records) == 1 else "s")
            )
            self.remove_button.setEnabled(len(records) > 1)
            if selected is not None:
                self.documents.setCurrentItem(selected)
                self._show_document(selected.data(Qt.UserRole + 1))
            self._updating = False
            self._filter(self.filter_edit.text())
            self._update_move_buttons()

        def _show_document(self, document: Any) -> None:
            was_updating = self._updating
            self._updating = True
            self._document_id = document.document_id
            try:
                self.module_edit.setText(document.module_id)
                self.logical_edit.setText(document.logical_name)
                self.primary_check.setChecked(bool(document.is_primary))
                self.primary_check.setEnabled(not document.is_primary)
                self.path_label.setText(document.path or "Unsaved")
                self.path_label.setToolTip(
                    document.path or "Unsaved document"
                )
            finally:
                self._updating = was_updating
            self._identity_baseline = (
                document.module_id,
                document.logical_name,
            )
            self._set_identity_pending(False)

        @property
        def current_document_id(self) -> str | None:
            return self._document_id

        def pending_identity(self) -> tuple[str, str]:
            return (
                self.module_edit.text().strip(),
                self.logical_edit.text().strip(),
            )

        @property
        def identity_pending(self) -> bool:
            return self._identity_pending

        def bind_action_registry(self, registry: Any) -> None:
            """Move button commands and widget shortcuts into *registry*."""

            bindings = (
                (
                    "bundle.new_module",
                    self.add_button,
                    self._request_add,
                ),
                (
                    "bundle.remove_module",
                    self.remove_button,
                    self._request_remove,
                ),
                (
                    "bundle.move_up",
                    self.move_up_button,
                    self._request_move_up,
                ),
                (
                    "bundle.move_down",
                    self.move_down_button,
                    self._request_move_down,
                ),
            )
            for action_id, button, handler in bindings:
                try:
                    button.clicked.disconnect(handler)
                except (RuntimeError, TypeError):
                    pass
                registry.register_handler(action_id, handler)
                registry.bind_tool_button(action_id, button)
            registry.attach_to_widget("bundle.move_up", self)
            registry.attach_to_widget("bundle.move_down", self)

        def _select_item(
            self,
            current: QListWidgetItem | None,
            previous: QListWidgetItem | None,
        ) -> None:
            del previous
            if current is None:
                self._document_id = None
                self._update_move_buttons()
                return
            self._show_document(current.data(Qt.UserRole + 1))
            self._update_move_buttons()
            if not self._updating:
                self.document_selected.emit(str(current.data(Qt.UserRole)))

        def _emit_identity(self) -> None:
            if self._updating or self._document_id is None:
                return
            self.identity_changed.emit(
                self._document_id,
                self.module_edit.text().strip(),
                self.logical_edit.text().strip(),
            )

        def _update_identity_pending(self, _value: str) -> None:
            if self._updating:
                return
            self._set_identity_pending(
                self._identity_baseline is not None
                and self.pending_identity() != self._identity_baseline
            )

        def _set_identity_pending(self, pending: bool) -> None:
            if pending == self._identity_pending:
                return
            self._identity_pending = pending
            self.identity_pending_changed.emit(pending)

        def _request_primary(self) -> None:
            if not self._updating and self._document_id is not None:
                self.primary_requested.emit(self._document_id)

        def _request_add(self) -> None:
            self.add_requested.emit()

        def _request_remove(self) -> None:
            if self._document_id is not None:
                self.remove_requested.emit(self._document_id)

        def _request_move_up(self) -> None:
            if self._document_id is not None and self.move_up_button.isEnabled():
                self.move_up_requested.emit(self._document_id)

        def _request_move_down(self) -> None:
            if self._document_id is not None and self.move_down_button.isEnabled():
                self.move_down_requested.emit(self._document_id)

        def _update_move_buttons(self) -> None:
            row = self.documents.currentRow()
            count = self.documents.count()
            self.move_up_button.setEnabled(row > 0)
            self.move_down_button.setEnabled(0 <= row < count - 1)

        def _filter(self, value: str) -> None:
            needle = value.casefold().strip()
            for row in range(self.documents.count()):
                item = self.documents.item(row)
                item.setHidden(bool(needle and needle not in item.text().casefold()))


    class DiagnosticsView(QWidget):
        """Filterable, navigable diagnostic list with remediation details."""

        diagnostic_activated = pyqtSignal(object)

        _SEVERITY_COLORS = {
            "InternalError": PYCFORGE_COLORS.error_bright,
            "Error": PYCFORGE_COLORS.error,
            "Warning": PYCFORGE_COLORS.warning,
            "Approximation": PYCFORGE_COLORS.violet_bright,
            "Information": PYCFORGE_COLORS.blue_bright,
            "Info": PYCFORGE_COLORS.blue_bright,
        }

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("DiagnosticsView")
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText("Filter diagnostics…")
            self.filter_edit.setClearButtonEnabled(True)
            self.filter_edit.setAccessibleName("Filter diagnostics")
            self.count_label = QLabel("No diagnostics")
            self.count_label.setObjectName("MutedLabel")
            self.tree = QTreeWidget()
            self.tree.setObjectName("DiagnosticsTree")
            self.tree.setColumnCount(5)
            self.tree.setHeaderLabels(("Severity", "Code", "Message", "Module", "Line"))
            self.tree.setRootIsDecorated(False)
            self.tree.setAlternatingRowColors(True)
            self.tree.setUniformRowHeights(True)
            self.tree.setAccessibleName("Conversion diagnostics")
            self.tree.header().setStretchLastSection(False)
            self.tree.header().resizeSection(0, 105)
            self.tree.header().resizeSection(1, 90)
            self.tree.header().resizeSection(2, 520)
            self.tree.header().resizeSection(3, 160)
            self.tree.header().resizeSection(4, 55)
            self.details = QTextBrowser()
            self.details.setObjectName("DiagnosticDetails")
            self.details.setOpenExternalLinks(False)
            self.details.setMaximumHeight(130)
            self.details.setPlaceholderText("Select a diagnostic for explanation and remediation.")

            top = QHBoxLayout()
            top.addWidget(self.filter_edit, 1)
            top.addWidget(self.count_label)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(7)
            layout.addLayout(top)
            layout.addWidget(self.tree, 1)
            layout.addWidget(self.details)

            self.filter_edit.textChanged.connect(self._filter)
            self.tree.currentItemChanged.connect(self._show_details)
            self.tree.itemActivated.connect(self._activate)

        def set_diagnostics(self, diagnostics: Iterable[dict[str, Any]]) -> None:
            records = tuple(diagnostics)
            self.tree.clear()
            for diagnostic in records:
                span = diagnostic.get("source_span") or {}
                start = span.get("start") or {}
                line = start.get("line")
                module = diagnostic.get("source_module_id") or diagnostic.get(
                    "source_logical_name"
                ) or "—"
                item = QTreeWidgetItem(
                    (
                        str(diagnostic.get("severity") or ""),
                        str(diagnostic.get("code") or ""),
                        str(diagnostic.get("message") or ""),
                        str(module),
                        str(line or "—"),
                    )
                )
                item.setData(0, Qt.UserRole, diagnostic)
                color = self._SEVERITY_COLORS.get(
                    str(diagnostic.get("severity")),
                    PYCFORGE_COLORS.text_muted,
                )
                item.setForeground(0, QBrush(QColor(color)))
                self.tree.addTopLevelItem(item)
            self.count_label.setText(
                "No diagnostics"
                if not records
                else f"{len(records)} diagnostic" + ("" if len(records) == 1 else "s")
            )
            self.details.clear()
            self._filter(self.filter_edit.text())

        def line_markers(self, logical_name: str) -> tuple[tuple[int, str], ...]:
            result = []
            for row in range(self.tree.topLevelItemCount()):
                diagnostic = self.tree.topLevelItem(row).data(0, Qt.UserRole)
                if diagnostic.get("source_logical_name") != logical_name:
                    continue
                span = diagnostic.get("source_span") or {}
                line = (span.get("start") or {}).get("line")
                if isinstance(line, int):
                    result.append((line, str(diagnostic.get("severity") or "Error")))
            return tuple(result)

        def _show_details(
            self,
            current: QTreeWidgetItem | None,
            previous: QTreeWidgetItem | None,
        ) -> None:
            del previous
            if current is None:
                self.details.clear()
                return
            diagnostic = current.data(0, Qt.UserRole)
            blocks = [
                f"{diagnostic.get('code', '')} — {diagnostic.get('message', '')}",
                str(diagnostic.get("explanation") or ""),
            ]
            remediation = diagnostic.get("remediation")
            if remediation:
                blocks.append(f"Suggested action: {remediation}")
            self.details.setPlainText("\n\n".join(item for item in blocks if item))

        def _activate(self, item: QTreeWidgetItem, column: int) -> None:
            del column
            self.diagnostic_activated.emit(item.data(0, Qt.UserRole))

        def _filter(self, value: str) -> None:
            needle = value.casefold().strip()
            for row in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(row)
                haystack = " ".join(item.text(column) for column in range(5)).casefold()
                item.setHidden(bool(needle and needle not in haystack))


    class InspectorTree(QWidget):
        """Searchable structured projection for summaries, traces, and telemetry."""

        def __init__(self, label: str, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("InspectorTree")
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText(f"Filter {label.casefold()}…")
            self.filter_edit.setClearButtonEnabled(True)
            self.filter_edit.setAccessibleName(f"Filter {label.casefold()}")
            self.tree = QTreeWidget()
            self.tree.setColumnCount(2)
            self.tree.setHeaderLabels(("Field", "Value"))
            self.tree.setAlternatingRowColors(True)
            self.tree.setAccessibleName(label)
            self.tree.header().resizeSection(0, 310)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(7)
            layout.addWidget(self.filter_edit)
            layout.addWidget(self.tree, 1)
            self.filter_edit.textChanged.connect(self._filter)

        def set_data(self, value: Any) -> None:
            self.tree.clear()
            items: list[QTreeWidgetItem] = []
            root = self.tree.invisibleRootItem()
            for node in project_inspector_tree(value):
                parent = (
                    root
                    if node.parent_index is None
                    else items[node.parent_index]
                )
                item = QTreeWidgetItem((node.key, node.value))
                parent.addChild(item)
                items.append(item)
            self.tree.expandToDepth(1)
            self._filter(self.filter_edit.text())

        def _filter(self, value: str) -> None:
            needle = value.casefold().strip()

            def visit(item: QTreeWidgetItem) -> bool:
                own = needle in (item.text(0) + " " + item.text(1)).casefold()
                child_match = False
                for index in range(item.childCount()):
                    child_match = visit(item.child(index)) or child_match
                visible = not needle or own or child_match
                item.setHidden(not visible)
                if child_match and needle:
                    item.setExpanded(True)
                return visible and (own or child_match)

            for index in range(self.tree.topLevelItemCount()):
                visit(self.tree.topLevelItem(index))


    class MappingsView(QWidget):
        """Filterable source-to-output provenance with direct C navigation."""

        mapping_activated = pyqtSignal(object)
        DISPLAY_LIMIT = 5000

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("MappingsView")
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText("Filter source mappings…")
            self.filter_edit.setClearButtonEnabled(True)
            self.filter_edit.setAccessibleName("Filter source-to-output mappings")
            self.count_label = QLabel("No mappings")
            self.count_label.setObjectName("MutedLabel")
            self.tree = QTreeWidget()
            self.tree.setObjectName("MappingsTree")
            self.tree.setColumnCount(5)
            self.tree.setHeaderLabels(("Module", "Origin", "Rule", "C range", "C node"))
            self.tree.setRootIsDecorated(False)
            self.tree.setAlternatingRowColors(True)
            self.tree.setUniformRowHeights(True)
            self.tree.setAccessibleName("Source-to-output mappings")
            self.tree.header().setStretchLastSection(True)
            self.tree.header().resizeSection(0, 170)
            self.tree.header().resizeSection(1, 190)
            self.tree.header().resizeSection(2, 210)
            self.tree.header().resizeSection(3, 130)

            top = QHBoxLayout()
            top.addWidget(self.filter_edit, 1)
            top.addWidget(self.count_label)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(7)
            layout.addLayout(top)
            layout.addWidget(self.tree, 1)

            self.filter_edit.textChanged.connect(self._filter)
            self.tree.itemActivated.connect(self._activate)

        def set_mappings(self, mappings: Iterable[dict[str, Any]]) -> None:
            records = tuple(mappings)
            self.tree.clear()
            for mapping in records[: self.DISPLAY_LIMIT]:
                positions = (
                    mapping.get("start_line"),
                    mapping.get("start_column"),
                    mapping.get("end_line"),
                    mapping.get("end_column"),
                )
                location = (
                    f"{positions[0]}:{positions[1]}–{positions[2]}:{positions[3]}"
                    if all(isinstance(value, int) for value in positions)
                    else "—"
                )
                module = mapping.get("module_id") or mapping.get(
                    "logical_source_name"
                ) or "synthetic"
                item = QTreeWidgetItem(
                    (
                        str(module),
                        str(mapping.get("origin_kind") or ""),
                        str(mapping.get("rule_plan_id") or "—"),
                        location,
                        str(mapping.get("c_node_id") or ""),
                    )
                )
                item.setData(0, Qt.UserRole, mapping)
                self.tree.addTopLevelItem(item)
            if not records:
                label = "No mappings"
            elif len(records) > self.DISPLAY_LIMIT:
                label = f"{self.DISPLAY_LIMIT} of {len(records)} mappings"
            else:
                label = f"{len(records)} mapping" + ("" if len(records) == 1 else "s")
            self.count_label.setText(label)
            self._filter(self.filter_edit.text())

        def _activate(self, item: QTreeWidgetItem, column: int) -> None:
            del column
            self.mapping_activated.emit(item.data(0, Qt.UserRole))

        def _filter(self, value: str) -> None:
            needle = value.casefold().strip()
            for row in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(row)
                haystack = " ".join(item.text(column) for column in range(5)).casefold()
                item.setHidden(bool(needle and needle not in haystack))


    class ToastBanner(QFrame):
        dismissed = pyqtSignal()

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("ToastBanner")
            self.setProperty("tone", "info")
            self.label = QLabel()
            self.label.setWordWrap(True)
            self.close_button = QToolButton()
            self.close_button.setObjectName("IconButton")
            self.close_button.setIcon(
                QIcon(str(pycforge_icon_path("close")))
            )
            self.close_button.setText("")
            self.close_button.setToolTip("Dismiss notification")
            self.close_button.setAccessibleName("Dismiss notification")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(12, 8, 8, 8)
            layout.addWidget(self.label, 1)
            layout.addWidget(self.close_button)
            self.close_button.clicked.connect(self.hide)
            self.close_button.clicked.connect(self.dismissed.emit)
            self.hide()

        def show_message(self, message: str, tone: str = "info") -> None:
            self.setProperty("tone", tone)
            self.style().unpolish(self)
            self.style().polish(self)
            self.label.setText(message)
            self.show()


else:
    class _QtRequired:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PyQt5 is required for workspace panels") from _QT_ERROR


    class DocumentNavigator(_QtRequired):
        pass


    class DiagnosticsView(_QtRequired):
        pass


    class InspectorTree(_QtRequired):
        pass


    class MappingsView(_QtRequired):
        pass


    class ToastBanner(_QtRequired):
        pass


__all__ = [
    "INSPECTOR_TREE_MAX_CHILDREN",
    "INSPECTOR_TREE_MAX_DEPTH",
    "INSPECTOR_TREE_MAX_NODES",
    "INSPECTOR_TREE_MAX_TEXT_CHARS",
    "QT_AVAILABLE",
    "DocumentNavigator",
    "DiagnosticsView",
    "InspectorNode",
    "InspectorTree",
    "MappingsView",
    "ToastBanner",
    "project_inspector_tree",
]
