"""Bounded settings, file observation, dialogs, and shutdown for Qt."""

from __future__ import annotations

import re
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QByteArray, QTimer

from pycforge._version import __version__

from .action_contract import DynamicActionEntry, MAX_DYNAMIC_LABEL_CHARS
from .qt_contract import (
    MAX_RECENT_PATHS,
    MAX_SETTINGS_BLOB_BYTES,
    MAX_SETTINGS_PATH_CHARS,
    PRESENTATION_SETTING_KEYS,
    SETTINGS_ORGANIZATION,
    SETTINGS_SCHEMA_VERSION,
    coerce_settings_schema_version,
)


class QtStateMixin:
    """Own presentation persistence and guarded filesystem observation."""

    def _restore_workspace_state(self) -> None:
        restorations = (
            ("window/geometry", self.restoreGeometry),
            ("window/state", self.restoreState),
            ("splitter/workspace", self.workspace_splitter.restoreState),
            ("splitter/editors", self.editor_splitter.restoreState),
            ("splitter/main", self.main_splitter.restoreState),
            ("splitter/source", self.source_splitter.restoreState),
        )
        for key, restore in restorations:
            value = self._setting_blob(key)
            if value is None:
                continue
            try:
                restore(value)
            except Exception:
                # Presentation settings are untrusted, optional input and
                # can never prevent construction of the workspace.
                continue
        self._set_navigator_visible(
            self._setting_bool("view/bundle", True)
        )
        self._set_output_visible(
            self._setting_bool("view/generated_c", False)
        )
        self._set_details_visible(
            self._setting_bool("view/details", False)
        )
        self._set_source_split_visible(
            self._setting_bool("view/source_split", False)
        )
        self._set_whitespace_visible(
            self._setting_bool("view/whitespace", False)
        )

    def _persist_workspace_state(self) -> None:
        values = {
            "settings/schema_version": SETTINGS_SCHEMA_VERSION,
            "window/geometry": self.saveGeometry(),
            "window/state": self.saveState(),
            "splitter/workspace": self.workspace_splitter.saveState(),
            "splitter/editors": self.editor_splitter.saveState(),
            "splitter/main": self.main_splitter.saveState(),
            "splitter/source": self.source_splitter.saveState(),
            "view/bundle": self.navigator.isVisible(),
            "view/generated_c": self.output_panel.isVisible(),
            "view/details": self.tabs.isVisible(),
            "view/source_split": self.source_secondary.isVisible(),
            "view/whitespace": self.source.whitespace_visible,
            "workspace/last_directory": self._last_directory,
            "workspace/recent_paths": self._recent_paths,
        }
        for key, value in values.items():
            self._set_setting(key, value)
        try:
            self.settings.sync()
        except Exception:
            pass

    def _prepare_settings(self) -> None:
        """Validate stored presentation state or clear an incompatible schema."""

        raw_version = self._settings_value(
            "settings/schema_version", None
        )
        if raw_version is None:
            # v0.12.1 had the same bounded presentation keys but no schema
            # marker. Accept it once through the typed readers below.
            version = SETTINGS_SCHEMA_VERSION
        else:
            version = coerce_settings_schema_version(raw_version)
        if version != SETTINGS_SCHEMA_VERSION:
            for key in PRESENTATION_SETTING_KEYS:
                try:
                    self.settings.remove(key)
                except Exception:
                    pass
        self._set_setting(
            "settings/schema_version", SETTINGS_SCHEMA_VERSION
        )

    def _settings_value(self, key: str, default: Any) -> Any:
        try:
            return self.settings.value(key, default)
        except Exception:
            return default

    def _set_setting(self, key: str, value: Any) -> None:
        try:
            self.settings.setValue(key, value)
        except Exception:
            pass

    def _setting_blob(self, key: str) -> QByteArray | None:
        value = self._settings_value(key, None)
        if not isinstance(value, (QByteArray, bytes, bytearray)):
            return None
        if not 0 < len(value) <= MAX_SETTINGS_BLOB_BYTES:
            return None
        return QByteArray(value)

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self._settings_value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str) and len(value) <= 16:
            normalized = value.casefold()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default

    def _setting_text(self, key: str, default: str) -> str:
        value = self._settings_value(key, default)
        if (
            not isinstance(value, str)
            or len(value) > MAX_SETTINGS_PATH_CHARS
            or "\0" in value
        ):
            return default
        return value

    def _load_recent_paths(self) -> list[str]:
        value = self._settings_value("workspace/recent_paths", [])
        if isinstance(value, str):
            candidates = (value,)
        elif isinstance(value, (list, tuple)):
            candidates = value
        else:
            return []
        paths: list[str] = []
        for item in candidates[: MAX_RECENT_PATHS * 10]:
            if (
                not isinstance(item, str)
                or not item
                or len(item) > MAX_SETTINGS_PATH_CHARS
                or "\0" in item
                or item in paths
            ):
                continue
            paths.append(item)
            if len(paths) == MAX_RECENT_PATHS:
                break
        return paths

    def _remember_path(self, path: Path) -> None:
        value = str(path)
        self._recent_paths = [
            value,
            *(item for item in self._recent_paths if item != value),
        ][:MAX_RECENT_PATHS]
        self._last_directory = str(path.parent)
        self._set_setting(
            "workspace/recent_paths", self._recent_paths
        )
        self._set_setting(
            "workspace/last_directory", self._last_directory
        )
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        if not hasattr(self, "action_registry"):
            return
        entries = []
        for path in self._recent_paths:
            label = path
            if len(label) > MAX_DYNAMIC_LABEL_CHARS:
                label = "…" + label[-(MAX_DYNAMIC_LABEL_CHARS - 1):]
            name = Path(path).name or path
            entries.append(
                DynamicActionEntry(
                    key=path,
                    label=label,
                    tooltip=path,
                    accessible_name=(
                        f"Open recent Python document {name}"
                    ),
                    payload=path,
                )
            )
        self.action_registry.replace_dynamic(
            "recent_python",
            entries,
            self._open_recent_path,
        )

    def _open_recent_path(self, value: str) -> None:
        self._open_path(Path(value))

    def _refresh_watchers(self, snapshot) -> None:
        key = (
            snapshot.revision_generation,
            snapshot.revision_authenticated,
            tuple(item.path for item in snapshot.documents),
        )
        if key == self._watcher_projection_key:
            return
        revision = self.controller.committed_revision
        if revision is None:
            return
        self._watcher_projection_key = key
        linked = {
            item.path: revision.index_for(
                item.document_id
            ).utf8_sha256
            for item in snapshot.documents
            if item.path is not None
        }
        desired = set(linked)
        self._known_file_fingerprints = {
            path: fingerprint for path, fingerprint in linked.items()
        }
        current = set(self.file_watcher.files())
        remove = sorted(current - desired)
        add = sorted(desired - current)
        if remove:
            self.file_watcher.removePaths(remove)
        if add:
            self.file_watcher.addPaths(add)

    def _external_file_changed(self, path: str) -> None:
        # Atomic replacement can briefly remove the watched path. Assess
        # decoded contents after the filesystem settles instead of using a
        # timing-only self-save suppression window.
        QTimer.singleShot(
            120,
            lambda value=path: self._assess_external_file_change(value),
        )

    def _assess_external_file_change(self, path: str) -> None:
        expected = self._known_file_fingerprints.get(path)
        try:
            future = self.controller.observe_linked_file_async(path)
        except Exception as exc:
            self._show_error(
                "Could not inspect the linked Python file", exc
            )
            return

        def assessed(completed: Future) -> None:
            try:
                observation = completed.result()
            except Exception as exc:
                self.toast.show_message(
                    f"{path} became unavailable or unreadable: {exc}",
                    "warning",
                )
            else:
                observed = observation.utf8_sha256
                if expected is not None and observed != expected:
                    self.toast.show_message(
                        f"{path} changed outside PyCForge. "
                        "Reopen it explicitly to review the disk version.",
                        "warning",
                    )
            self._watcher_projection_key = None
            self._refresh_watchers(self.controller.snapshot)

        self._dispatch_io(future, assessed)

    def _unique_module_id(
        self,
        seed: str,
        replacing_document_id: str | None = None,
    ) -> str:
        base = re.sub(
            r"[^a-z0-9_]+", "_", seed.casefold()
        ).strip("_")
        if not base or not base[0].isalpha():
            base = "module_" + (base or "source")
        base = base[:55]
        used = {
            item.module_id for item in self.controller.snapshot.documents
            if item.document_id != replacing_document_id
        }
        candidate = base
        index = 2
        while candidate in used:
            candidate = f"{base[:59]}_{index}"
            index += 1
        return candidate

    def _unique_logical_name(
        self,
        seed: str,
        replacing_document_id: str | None = None,
    ) -> str:
        safe = Path(seed).name or "source.py"
        if not safe.endswith(".py"):
            safe += ".py"
        used = {
            item.logical_name
            for item in self.controller.snapshot.documents
            if item.document_id != replacing_document_id
        }
        candidate = safe
        index = 2
        path = Path(safe)
        while candidate in used:
            candidate = f"{path.stem}_{index}{path.suffix}"
            index += 1
        return candidate

    def _commit_pending_identity(self) -> bool:
        if not self._flush_pending_source_sync():
            return False
        document_id = self.navigator.current_document_id
        if document_id is None:
            return True
        module_id, logical_name = self.navigator.pending_identity()
        try:
            document = next(
                item for item in self.controller.snapshot.documents
                if item.document_id == document_id
            )
        except StopIteration:
            self.toast.show_message(
                "The selected module no longer exists.", "warning"
            )
            return False
        if (
            module_id == document.module_id
            and logical_name == document.logical_name
        ):
            return True
        try:
            self.controller.set_document_identity(
                document_id,
                module_id=module_id,
                logical_name=logical_name,
            )
        except Exception as exc:
            self._show_error(
                "Document identity was not accepted", exc
            )
            self._navigator_key = None
            self._apply_snapshot(self.controller.snapshot)
            return False
        return True

    def _show_error(self, heading: str, exc: Exception) -> None:
        message = str(exc).strip() or exc.__class__.__name__
        self.toast.show_message(
            f"{heading}: {message}", "error"
        )
        self.statusBar().showMessage(heading, 9000)

    @staticmethod
    def _linked_c_display(path: str | None) -> str:
        """Keep the destination filename visible; tooltip has full path."""

        if not path:
            return "not set"
        return Path(path).name or path

    def _update_window_title(self, active) -> None:
        dirty = " •" if active.dirty else ""
        self.setWindowTitle(
            f"{active.logical_name}{dirty} — PyCForge {__version__}"
        )

__all__ = ["QtStateMixin"]
