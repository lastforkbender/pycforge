"""Bounded snapshot projection and visibility behavior for the Qt workspace."""

from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QWidget

from .editor import EditorMarker
from .qt_contract import (
    diagnostic_character_range,
    mapping_character_range,
    qt_range,
)


class QtProjectionMixin:
    """Project immutable controller snapshots without blocking the event loop."""

    def _apply_snapshot(self, snapshot) -> None:
        pending_document_id = (
            self._source_sync_document_id
            if self._source_sync_pending else None
        )
        if (
            pending_document_id is not None
            and snapshot.active_document.document_id
            != pending_document_id
        ):
            # A controller-side selection may arrive without passing through
            # the window action. Preserve the old editor text before showing
            # the newly active document.
            if not self._flush_pending_source_sync():
                return
            snapshot = self.controller.snapshot
        self._last_snapshot = snapshot
        active = snapshot.active_document
        active_changed = self._displayed_document_id != active.document_id
        self._displayed_document_id = active.document_id
        pending_active = (
            self._source_sync_pending
            and self._source_sync_document_id == active.document_id
        )
        self._project_workspace_features(
            snapshot,
            active_changed=active_changed,
        )
        output_key = (
            snapshot.result_revision_generation,
            id(snapshot.generated_c),
        )
        if output_key != self._displayed_output_key:
            self._displayed_output_key = output_key
            self._start_output_projection(
                snapshot.generated_c or "", output_key
            )

        navigator_key = (
            snapshot.active_document_id,
            tuple(
                (
                    item.document_id,
                    item.module_id,
                    item.logical_name,
                    item.path,
                    item.is_primary,
                    item.dirty,
                )
                for item in snapshot.documents
            ),
        )
        if navigator_key != self._navigator_key:
            self._navigator_key = navigator_key
            self.navigator.set_documents(
                snapshot.documents, snapshot.active_document_id
            )

        dirty = "  •  modified" if active.dirty else ""
        primary = "  ·  PRIMARY" if active.is_primary else ""
        self.active_module_label.setText(
            f"{active.module_id}  ·  {active.logical_name}{primary}{dirty}"
        )
        self.active_path_label.setText(active.path or "Unsaved document")
        self.active_path_label.setToolTip(active.path or "Unsaved document")
        self.status_document.setText(
            active.logical_name + (" •" if active.dirty else "")
        )
        self._set_state_chip(snapshot.state.value)
        self._set_output_state(snapshot)
        self.linked_c_label.setText(
            self._linked_c_display(snapshot.linked_c_path)
        )
        self.linked_c_label.setToolTip(
            snapshot.linked_c_path or "No linked C destination"
        )
        self.linked_c_label.setAccessibleName(
            "Linked C destination: "
            + (snapshot.linked_c_path or "not set")
        )

        diagnostic_count = len(snapshot.diagnostics)
        self.tabs.setTabText(
            self.tabs.indexOf(self.diags),
            "Diagnostics"
            + (f"  {diagnostic_count}" if diagnostic_count else ""),
        )
        self.tabs.setTabText(
            self.tabs.indexOf(self.mappings),
            "Mappings"
            + (
                f"  {len(snapshot.mappings)}"
                if snapshot.mappings else ""
            ),
        )
        if self.tabs.isVisible():
            self._refresh_detail_views(snapshot)
        self._project_editor_markers(snapshot)
        self._configure_actions(snapshot)
        self._configure_progress_state(snapshot)
        self._refresh_watchers(snapshot)
        self._update_window_title(active)
        if pending_active:
            self._present_pending_source_sync()
        elif self.navigator.identity_pending:
            self._present_pending_identity_edit(True)

        if active_changed:
            self.find_bar.attach_editor(self.source)

    def _start_output_projection(
        self,
        text: str,
        key: tuple[int | None, int],
    ) -> None:
        """Populate generated C in bounded event-loop slices.

        Progress-only snapshots never materialize either full editor.
        A new complete result invalidates an older projection by key, and
        only the current projection is permitted to append another slice.
        """

        self._output_projection_key = key
        self._output_projection_text = text
        self._output_projection_offset = 0
        # ``len`` is constant-time and keeps result-envelope publication from
        # scanning all generated C merely to choose a projection mode.  Use a
        # deliberately conservative output threshold; the inspector is
        # read-only, so responsiveness takes priority over whole-file syntax
        # decoration for large results.
        self.output.set_large_file_mode(len(text) >= 64 * 1024)
        self.output.clear()
        if not self.output_panel.isVisible():
            return
        self._append_output_projection_slice(key)

    def _append_output_projection_slice(
        self,
        key: tuple[int | None, int],
    ) -> None:
        if key != self._output_projection_key:
            return
        start = self._output_projection_offset
        text = self._output_projection_text
        if start >= len(text):
            self._output_projection_text = ""
            self._output_marker_key = None
            if self._last_snapshot is not None:
                self._project_editor_markers(self._last_snapshot)
            return
        end = min(len(text), start + 32_768)
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text[start:end])
        self._output_projection_offset = end
        QTimer.singleShot(
            0,
            lambda current_key=key: self._append_output_projection_slice(
                current_key
            ),
        )

    def _refresh_detail_views(
        self, snapshot, *, force: bool = False
    ) -> None:
        key = (
            id(snapshot.diagnostics),
            snapshot.summary,
            id(snapshot.conversion_summary),
            id(snapshot.decision_trace),
            id(snapshot.telemetry),
            id(snapshot.mappings),
        )
        if not force and key == self._detail_projection_key:
            return
        self._detail_projection_key = key
        self.diags.set_diagnostics(snapshot.diagnostics)
        summary_data = (
            snapshot.conversion_summary
            if snapshot.conversion_summary is not None
            else dict(snapshot.summary)
        )
        self.summary.set_data(summary_data or {})
        self.trace.set_data(snapshot.decision_trace or {})
        self.telemetry.set_data(snapshot.telemetry or {})
        self.mappings.set_mappings(snapshot.mappings)

    def _project_editor_markers(self, snapshot) -> None:
        active = snapshot.active_document
        revision = self.controller.committed_revision
        source_position_index = None
        if revision is not None:
            try:
                source_position_index = revision.index_for(
                    active.document_id
                ).position_index
            except KeyError:
                source_position_index = None
        diagnostics_current = snapshot.state.value not in {
            "empty",
            "stale",
            "converting",
            "cancel-requested",
            "canceled",
        }
        source_key = (
            active.document_id,
            snapshot.state.value if diagnostics_current else "inactive",
            snapshot.source_fingerprint if diagnostics_current else None,
            id(snapshot.diagnostics) if diagnostics_current else None,
        )
        if source_key != self._source_marker_key:
            self._source_marker_key = source_key
            diagnostic_markers: list[EditorMarker] = []
            if diagnostics_current:
                for diagnostic in snapshot.diagnostics:
                    if (
                        diagnostic.get("source_logical_name")
                        != active.logical_name
                        and diagnostic.get("source_module_id")
                        != active.module_id
                    ):
                        continue
                    start, end = diagnostic_character_range(
                        diagnostic,
                        active.text,
                        source_position_index,
                    )
                    start, end = qt_range(
                        active.text,
                        start,
                        end,
                        source_position_index,
                    )
                    severity = str(
                        diagnostic.get("severity") or "Error"
                    )
                    kind = (
                        "warning"
                        if severity in {"Warning", "Approximation"}
                        else "info"
                        if severity in {"Info", "Information"}
                        else "diagnostic"
                    )
                    diagnostic_markers.append(
                        EditorMarker(
                            start,
                            end,
                            kind=kind,
                            message=(
                                f"{diagnostic.get('code', '')} · "
                                f"{diagnostic.get('message', '')}"
                            ),
                            marker_id=str(
                                diagnostic.get("diagnostic_id") or ""
                            ),
                        )
                    )
            self.source.set_diagnostic_ranges(diagnostic_markers)
            self.source_secondary.set_diagnostic_ranges(
                diagnostic_markers
            )

        output_text = snapshot.generated_c or ""
        output_position_index = self.controller.result_output_index
        output_key = (
            id(snapshot.mappings),
            id(snapshot.generated_c),
            id(output_position_index),
        )
        if output_key == self._output_marker_key:
            return
        self._output_marker_key = output_key
        if (
            output_text
            and snapshot.mappings
            and output_position_index is None
        ):
            self.output.set_mapping_ranges(())
            return
        mapping_markers = []
        for mapping in snapshot.mappings[:5000]:
            if not (
                mapping.get("module_id")
                or mapping.get("source_node_ids")
            ):
                continue
            start, end = mapping_character_range(
                mapping,
                output_text,
                output_position_index,
            )
            start, end = qt_range(
                output_text,
                start,
                end,
                output_position_index,
            )
            mapping_markers.append(
                EditorMarker(
                    start,
                    end,
                    kind="mapping",
                    message=(
                        f"{mapping.get('module_id') or 'source'} · "
                        f"{mapping.get('rule_plan_id') or mapping.get('origin_kind') or ''}"
                    ),
                    marker_id=str(mapping.get("c_node_id") or ""),
                )
            )
        self.output.set_mapping_ranges(mapping_markers)

    def _configure_actions(self, snapshot) -> None:
        self.action_registry.refresh()
        self.navigator.add_button.setEnabled(snapshot.can_add_document)
        self.navigator.remove_button.setEnabled(
            snapshot.can_remove_document
        )

    def _set_state_chip(self, state: str) -> None:
        labels = {
            "observer-incomplete": "TRANSPILED · OBSERVER INCOMPLETE",
            "approximation": "TRANSPILED · APPROXIMATION",
            "warning": "TRANSPILED · WARNING",
        }
        self.state_chip.setText(
            labels.get(state, state.replace("-", " ").upper())
        )
        if state in {"converted"}:
            tone = "success"
        elif state in {
            "warning",
            "approximation",
            "observer-incomplete",
            "stale",
        }:
            tone = "warning"
        elif state in {"rejected", "failed"}:
            tone = "error"
        else:
            tone = "neutral"
        self._set_dynamic_property(self.state_chip, "status", tone)

    def _set_output_state(self, snapshot) -> None:
        if snapshot.generated_c is None:
            label, tone = "NO RESULT", "neutral"
        elif snapshot.can_save_c:
            label, tone = "CURRENT · SAVE ELIGIBLE", "success"
        elif snapshot.state.value == "stale":
            label, tone = "STALE · LAST COMPLETE C", "warning"
        elif snapshot.state.value == "rejected":
            label, tone = "PREVIOUS C · REQUEST REJECTED", "error"
        elif snapshot.state.value == "converting":
            label, tone = "HELD · TRANSPILATION ACTIVE", "neutral"
        elif snapshot.state.value == "cancel-requested":
            label, tone = "HELD · CANCELLATION REQUESTED", "warning"
        else:
            label, tone = "PREVIOUS C · NOT SAVABLE", "warning"
        self.output_state_label.setText(label)
        self._set_dynamic_property(
            self.output_state_label, "status", tone
        )

    @staticmethod
    def _set_dynamic_property(
        widget: QWidget, name: str, value: str
    ) -> None:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _configure_progress_state(self, snapshot) -> None:
        if snapshot.state.value in {"converting", "cancel-requested"}:
            self._configure_progress(snapshot)
            if self._progress_sequence != snapshot.request_sequence:
                self._progress_sequence = snapshot.request_sequence
                self.progress.hide()
                QTimer.singleShot(
                    180,
                    lambda sequence=snapshot.request_sequence:
                    self._show_progress_if_current(sequence),
                )
            stage = self._STAGE_LABELS.get(
                snapshot.active_stage,
                snapshot.active_stage or "Preparing transpilation pipeline",
            )
            if snapshot.state.value == "cancel-requested":
                self.statusBar().showMessage(
                    "Cancel requested — waiting for isolated worker shutdown"
                )
            else:
                self.statusBar().showMessage(f"Transpiling — {stage}")
        else:
            self.progress.hide()
            count = len(snapshot.diagnostics)
            message = snapshot.state.value.replace("-", " ").title()
            if count:
                message += f" — {count} diagnostic" + (
                    "" if count == 1 else "s"
                )
            if snapshot.stale_reason:
                message += (
                    f" — {snapshot.stale_reason.replace('-', ' ')}"
                )
            self.statusBar().showMessage(message)

    def _configure_progress(self, snapshot) -> None:
        if snapshot.total_stages:
            self.progress.setRange(0, snapshot.total_stages)
            self.progress.setValue(snapshot.completed_stages)
            self.progress.setFormat("%v/%m stages")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Transpiling")

    def _show_progress_if_current(self, sequence: int) -> None:
        snapshot = self.controller.snapshot
        if (
            snapshot.state.value != "converting"
            or snapshot.request_sequence != sequence
        ):
            return
        self._configure_progress(snapshot)
        self.progress.show()

    def _set_output_visible(self, visible: bool) -> None:
        self.output_panel.setVisible(visible)
        self.output.setVisible(visible)
        self.output_tabs.setVisible(visible)
        self.action_registry.refresh()
        if visible:
            self.output_tabs.setCurrentWidget(self.output)
            if (
                self._output_projection_key is not None
                and self._output_projection_offset
                < len(self._output_projection_text)
            ):
                QTimer.singleShot(
                    0,
                    lambda key=self._output_projection_key:
                    self._append_output_projection_slice(key),
                )
            QTimer.singleShot(0, self._balance_editor_splitter)

    def _set_details_visible(self, visible: bool) -> None:
        self.tabs.setVisible(visible)
        self.action_registry.refresh()
        if visible:
            self._refresh_detail_views(
                self.controller.snapshot, force=True
            )
            QTimer.singleShot(0, self._balance_main_splitter)

    def _balance_editor_splitter(self) -> None:
        available = max(
            2,
            self.editor_splitter.width()
            - self.editor_splitter.handleWidth(),
        )
        source_width = available // 2
        self.editor_splitter.setSizes(
            (source_width, available - source_width)
        )

    def _balance_main_splitter(self) -> None:
        available = max(
            2,
            self.main_splitter.height() - self.main_splitter.handleWidth(),
        )
        workspace_height = round(available * 0.65)
        self.main_splitter.setSizes(
            (workspace_height, available - workspace_height)
        )

    def _set_navigator_visible(self, visible: bool) -> None:
        self.navigator.setVisible(visible)
        self.action_registry.refresh()


__all__ = ["QtProjectionMixin"]
