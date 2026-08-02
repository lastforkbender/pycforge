"""Line-number and quantum-rail widgets used by the PyCForge editor."""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QWidget


class _LineNumberArea(QWidget):
    """Narrow line-number gutter delegated to its owning editor."""

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self.editor = editor
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):  # noqa: N802 - Qt API
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.editor.paint_line_number_area(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.editor.go_to_line_at_y(event.pos().y())
        super().mousePressEvent(event)


class _QuantumRail(QWidget):
    """Accessible bounded overview/navigation rail for editor markers."""

    WIDTH = 18

    def __init__(self, editor) -> None:
        super().__init__(editor)
        self.editor = editor
        self._keyboard_marker_index = -1
        self.setObjectName("QuantumVisibilityRail")
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Source quantum visibility rail")
        self.setAccessibleDescription(
            "Overview of search, diagnostic, mapping, and viewport "
            "positions. Use arrow keys to navigate markers, Page Up "
            "and Page Down to scroll, and Enter or Space to activate "
            "a marker."
        )
        self.setToolTip(
            "Source overview: arrows navigate markers; Enter activates"
        )

    def sizeHint(self):  # noqa: N802 - Qt API
        return QSize(self.WIDTH, 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.editor.paint_quantum_rail(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.setFocus(Qt.MouseFocusReason)
        marker = self.editor.marker_near_rail_position(
            event.pos().y()
        )
        if marker is not None:
            markers = self._ordered_markers()
            self._keyboard_marker_index = markers.index(marker)
        self.editor.activate_rail_position(event.pos().y())
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        marker = self.editor.marker_near_rail_position(
            event.pos().y()
        )
        self.setToolTip(
            marker.message
            if marker is not None else "Scroll overview"
        )
        super().mouseMoveEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key in (Qt.Key_Up, Qt.Key_Left):
            self._select_relative_marker(-1)
        elif key in (Qt.Key_Down, Qt.Key_Right):
            self._select_relative_marker(1)
        elif key == Qt.Key_Home:
            self._select_endpoint_marker(first=True)
        elif key == Qt.Key_End:
            self._select_endpoint_marker(first=False)
        elif key == Qt.Key_PageUp:
            self._scroll_page(-1)
        elif key == Qt.Key_PageDown:
            self._scroll_page(1)
        elif key in (
            Qt.Key_Return,
            Qt.Key_Enter,
            Qt.Key_Space,
        ):
            self._activate_keyboard_marker()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def markers_changed(self) -> None:
        """Retire a keyboard selection that may no longer exist."""

        self._keyboard_marker_index = -1
        self.update()

    def selected_marker(self):
        markers = self._ordered_markers()
        if 0 <= self._keyboard_marker_index < len(markers):
            return markers[self._keyboard_marker_index]
        return None

    def _ordered_markers(self) -> tuple:
        return tuple(
            sorted(
                self.editor._rail_markers(),
                key=lambda marker: (
                    marker.start,
                    marker.end,
                    marker.kind,
                    marker.marker_id,
                ),
            )
        )

    def _select_relative_marker(self, step: int) -> None:
        markers = self._ordered_markers()
        if not markers:
            self._scroll_line(step)
            return
        if 0 <= self._keyboard_marker_index < len(markers):
            index = min(
                len(markers) - 1,
                max(0, self._keyboard_marker_index + step),
            )
        else:
            position = self.editor.textCursor().position()
            if step > 0:
                index = next(
                    (
                        marker_index
                        for marker_index, marker in enumerate(markers)
                        if marker.start >= position
                    ),
                    len(markers) - 1,
                )
            else:
                index = next(
                    (
                        marker_index
                        for marker_index in range(
                            len(markers) - 1, -1, -1
                        )
                        if markers[marker_index].start <= position
                    ),
                    0,
                )
        self._select_marker(index, markers)

    def _select_endpoint_marker(self, *, first: bool) -> None:
        markers = self._ordered_markers()
        if markers:
            self._select_marker(
                0 if first else len(markers) - 1,
                markers,
            )
            return
        bar = self.editor.verticalScrollBar()
        bar.setValue(bar.minimum() if first else bar.maximum())
        self.update()

    def _select_marker(
        self,
        index: int,
        markers: tuple,
    ) -> None:
        self._keyboard_marker_index = index
        marker = markers[index]
        self.editor.go_to_position(
            marker.start, marker.end, focus=False
        )
        self.setToolTip(
            marker.message
            or (
                f"{marker.kind.capitalize()} marker at source "
                f"position {marker.start}"
            )
        )
        self.update()

    def _activate_keyboard_marker(self) -> None:
        marker = self.selected_marker()
        if marker is None:
            markers = self._ordered_markers()
            if not markers:
                return
            position = self.editor.textCursor().position()
            index = min(
                range(len(markers)),
                key=lambda item: (
                    abs(markers[item].start - position),
                    item,
                ),
            )
            self._select_marker(index, markers)
            marker = markers[index]
        self.editor.activate_rail_marker(marker, focus=False)
        self.update()

    def _scroll_line(self, step: int) -> None:
        bar = self.editor.verticalScrollBar()
        bar.setValue(
            bar.value() + step * max(1, bar.singleStep())
        )
        self.update()

    def _scroll_page(self, step: int) -> None:
        bar = self.editor.verticalScrollBar()
        bar.setValue(
            bar.value() + step * max(1, bar.pageStep())
        )
        self.update()


__all__ = ["_LineNumberArea", "_QuantumRail"]
