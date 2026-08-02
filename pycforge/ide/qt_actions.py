"""Optional Qt materialization of the declared PyCForge action contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .action_contract import (
    ACTION_SPECS,
    DYNAMIC_ACTION_GROUPS,
    ActionSpec,
    ActionState,
    DynamicActionEntry,
    validated_dynamic_entries,
)


try:
    from PyQt5.QtCore import QObject, QSignalBlocker, Qt
    from PyQt5.QtGui import QIcon, QKeySequence
    from PyQt5.QtWidgets import QAction, QToolButton, QWidget
except (ImportError, ModuleNotFoundError) as exc:
    QT_ACTIONS_AVAILABLE = False
    _QT_ERROR = exc
else:
    QT_ACTIONS_AVAILABLE = True
    _QT_ERROR = None


ActionHandler = Callable[..., Any]
ActionStateProvider = Callable[
    [str | None, object | None],
    Mapping[str, ActionState],
]


if QT_ACTIONS_AVAILABLE:
    from .icons import pycforge_icon_path

    _STANDARD_KEYS = {
        "Open": QKeySequence.Open,
        "New": QKeySequence.New,
        "Save": QKeySequence.Save,
        "SaveAs": QKeySequence.SaveAs,
        "Undo": QKeySequence.Undo,
        "Redo": QKeySequence.Redo,
        "Cut": QKeySequence.Cut,
        "Copy": QKeySequence.Copy,
        "Paste": QKeySequence.Paste,
        "SelectAll": QKeySequence.SelectAll,
        "Find": QKeySequence.Find,
        "Replace": QKeySequence.Replace,
        "FindNext": QKeySequence.FindNext,
    }

    class QtActionRegistry(QObject):
        """Own exactly one QAction per declared non-parameterized action."""

        def __init__(
            self,
            owner: QWidget,
            handlers: Mapping[str, ActionHandler] | None = None,
            *,
            state_provider: ActionStateProvider | None = None,
            action_specs: Mapping[str, ActionSpec] = ACTION_SPECS,
        ) -> None:
            if owner is None:
                raise TypeError("owner must be a QWidget")
            super().__init__(owner)
            self._owner = owner
            self._specs = dict(action_specs)
            self._handlers = dict(handlers or {})
            self._state_provider = state_provider
            self._actions: dict[str, QAction] = {}
            self._dynamic_actions: dict[str, tuple[QAction, ...]] = {}
            self._last_states: dict[str, ActionState] = {}
            self._active_surface_id: str | None = None
            self._active_target: object | None = None
            for action_id, spec in self._specs.items():
                if spec.dynamic:
                    continue
                action = self._materialize(spec)
                self._actions[action_id] = action
                if spec.shortcut_context == "window":
                    owner.addAction(action)
            self.refresh()

        @property
        def active_surface_id(self) -> str | None:
            return self._active_surface_id

        @property
        def active_target(self) -> object | None:
            return self._active_target

        def action(self, action_id: str) -> QAction:
            """Return the sole QAction for a declared static action."""

            try:
                return self._actions[action_id]
            except KeyError as exc:
                if action_id in self._specs:
                    raise KeyError(
                        f"dynamic action has no static instance: {action_id}"
                    ) from exc
                raise KeyError(f"unknown PyCForge action: {action_id}") from exc

        def spec(self, action_id: str) -> ActionSpec:
            try:
                return self._specs[action_id]
            except KeyError as exc:
                raise KeyError(
                    f"unknown PyCForge action: {action_id}"
                ) from exc

        def static_action_ids(self) -> tuple[str, ...]:
            return tuple(self._actions)

        def is_disabled_window_shortcut(
            self,
            key: int,
            modifiers: int,
        ) -> bool:
            """Return whether a reserved disabled shortcut must be consumed."""

            sequence = QKeySequence(int(modifiers) | int(key))
            for action_id, action in self._actions.items():
                shortcut = action.shortcut()
                if (
                    self._specs[action_id].shortcut_context == "window"
                    and not action.isEnabled()
                    and not shortcut.isEmpty()
                    and sequence.matches(shortcut)
                    == QKeySequence.ExactMatch
                ):
                    return True
            return False

        def register_handler(
            self, action_id: str, handler: ActionHandler
        ) -> None:
            if action_id not in self._actions:
                raise KeyError(f"unknown static action: {action_id}")
            if not callable(handler):
                raise TypeError("action handler must be callable")
            self._handlers[action_id] = handler
            self.refresh()

        def unregister_handler(self, action_id: str) -> None:
            self._handlers.pop(action_id, None)
            self.refresh()

        def set_state_provider(
            self, provider: ActionStateProvider | None
        ) -> None:
            if provider is not None and not callable(provider):
                raise TypeError("state provider must be callable")
            self._state_provider = provider
            self.refresh()

        def set_active_context(
            self, surface_id: str | None, target: object | None
        ) -> None:
            self._active_surface_id = surface_id
            self._active_target = target
            self.refresh()

        def clear_active_context(self) -> None:
            self.set_active_context(None, None)

        def refresh(
            self,
            states: Mapping[str, ActionState] | None = None,
        ) -> None:
            """Project bounded application state onto every static action."""

            if states is None and self._state_provider is not None:
                states = self._state_provider(
                    self._active_surface_id,
                    self._active_target,
                )
            if states is not None:
                unknown = set(states).difference(self._actions)
                if unknown:
                    raise KeyError(
                        f"state supplied for unknown actions: {sorted(unknown)}"
                    )
                if any(
                    not isinstance(value, ActionState)
                    for value in states.values()
                ):
                    raise TypeError("action states must be ActionState values")
                self._last_states = dict(states)
            for action_id, action in self._actions.items():
                state = self._last_states.get(action_id, ActionState())
                enabled = state.enabled and action_id in self._handlers
                action.setEnabled(enabled)
                action.setVisible(state.visible)
                if action.isCheckable() and state.checked is not None:
                    blocker = QSignalBlocker(action)
                    action.setChecked(bool(state.checked))
                    del blocker

        def set_enabled(self, action_id: str, enabled: bool) -> None:
            current = self._last_states.get(action_id, ActionState())
            self._last_states[action_id] = ActionState(
                enabled=bool(enabled),
                checked=current.checked,
                visible=current.visible,
            )
            self.refresh(self._last_states)

        def set_checked(self, action_id: str, checked: bool) -> None:
            action = self.action(action_id)
            if not action.isCheckable():
                raise ValueError(f"action is not checkable: {action_id}")
            current = self._last_states.get(action_id, ActionState())
            self._last_states[action_id] = ActionState(
                enabled=current.enabled,
                checked=bool(checked),
                visible=current.visible,
            )
            self.refresh(self._last_states)

        def attach_to_widget(
            self, action_id: str, widget: QWidget
        ) -> QAction:
            """Attach a widget-scoped shortcut to its intended owner."""

            action = self.action(action_id)
            if self.spec(action_id).shortcut_context != "widget":
                raise ValueError(
                    f"action is not widget-scoped: {action_id}"
                )
            widget.addAction(action)
            return action

        def bind_tool_button(
            self,
            action_id: str,
            button: QToolButton,
            *,
            accessible_description: str | None = None,
        ) -> None:
            """Bind a button without duplicating labels, icons, or callbacks."""

            if not isinstance(button, QToolButton):
                raise TypeError("button must be a QToolButton")
            spec = self.spec(action_id)
            button.setDefaultAction(self.action(action_id))
            button.setAccessibleName(spec.accessible_name)
            if accessible_description:
                button.setAccessibleDescription(accessible_description)

        def replace_dynamic(
            self,
            group_id: str,
            entries: tuple[DynamicActionEntry, ...] | list[DynamicActionEntry],
            handler: Callable[[str], Any],
        ) -> tuple[QAction, ...]:
            """Replace a bounded parameterized group owned by this registry."""

            if group_id not in DYNAMIC_ACTION_GROUPS:
                raise KeyError(f"unknown dynamic action group: {group_id}")
            if not callable(handler):
                raise TypeError("dynamic action handler must be callable")
            records = validated_dynamic_entries(entries)
            if not records:
                records = (
                    DynamicActionEntry(
                        key="empty",
                        label="No recent Python documents",
                        tooltip="No recent Python documents are available",
                        accessible_name="No recent Python documents",
                        payload="",
                        enabled=False,
                    ),
                )
            for action in self._dynamic_actions.get(group_id, ()):
                action.setParent(None)
                action.deleteLater()
            template = self.spec(DYNAMIC_ACTION_GROUPS[group_id])
            actions = tuple(
                self._materialize_dynamic(
                    group_id, template, entry, handler, index
                )
                for index, entry in enumerate(records)
            )
            self._dynamic_actions[group_id] = actions
            return actions

        def dynamic_actions(self, group_id: str) -> tuple[QAction, ...]:
            if group_id not in DYNAMIC_ACTION_GROUPS:
                raise KeyError(f"unknown dynamic action group: {group_id}")
            return self._dynamic_actions.get(group_id, ())

        def _materialize(self, spec: ActionSpec) -> QAction:
            icon = (
                QIcon(str(pycforge_icon_path(spec.icon_name)))
                if spec.icon_name else QIcon()
            )
            action = QAction(icon, spec.menu_text, self._owner)
            action.setObjectName(
                "pycforgeAction__" + spec.action_id.replace(".", "__")
            )
            action.setData(spec.action_id)
            action.setIconText(spec.toolbar_text)
            action.setCheckable(spec.checkable)
            action.setAutoRepeat(False)
            action.setProperty("pycforgeActionId", spec.action_id)
            action.setProperty("pycforgeTone", spec.tone)
            action.setProperty(
                "pycforgeAccessibleName", spec.accessible_name
            )
            sequence = self._shortcut(spec)
            if sequence is not None:
                action.setShortcut(sequence)
                context = (
                    Qt.WidgetWithChildrenShortcut
                    if spec.shortcut_context == "widget"
                    else Qt.WindowShortcut
                )
                action.setShortcutContext(context)
            tooltip = self._tooltip(spec.tooltip, sequence)
            action.setToolTip(tooltip)
            action.setStatusTip(spec.tooltip)
            action.setWhatsThis(spec.tooltip)
            action.triggered.connect(
                lambda checked=False, action_id=spec.action_id:
                self._invoke(action_id, checked)
            )
            return action

        def _materialize_dynamic(
            self,
            group_id: str,
            template: ActionSpec,
            entry: DynamicActionEntry,
            handler: Callable[[str], Any],
            index: int,
        ) -> QAction:
            icon = (
                QIcon(str(pycforge_icon_path(template.icon_name)))
                if template.icon_name else QIcon()
            )
            action = QAction(
                icon, entry.label.replace("&", "&&"), self._owner
            )
            action.setObjectName(
                f"pycforgeDynamic__{group_id}__{index}"
            )
            action.setData((group_id, entry.key))
            action.setEnabled(entry.enabled)
            action.setToolTip(entry.tooltip)
            action.setStatusTip(entry.tooltip)
            action.setProperty("pycforgeActionId", template.action_id)
            action.setProperty("pycforgeTone", template.tone)
            action.setProperty(
                "pycforgeAccessibleName", entry.accessible_name
            )
            if entry.enabled:
                action.triggered.connect(
                    lambda checked=False, payload=entry.payload:
                    handler(payload)
                )
            return action

        def _invoke(self, action_id: str, checked: bool) -> None:
            handler = self._handlers.get(action_id)
            if handler is None:
                return
            if self._specs[action_id].checkable:
                handler(bool(checked))
            else:
                handler()

        @staticmethod
        def _shortcut(spec: ActionSpec) -> QKeySequence | None:
            if spec.standard_shortcut:
                try:
                    return QKeySequence(
                        _STANDARD_KEYS[spec.standard_shortcut]
                    )
                except KeyError as exc:
                    raise ValueError(
                        "unknown standard shortcut: "
                        f"{spec.standard_shortcut}"
                    ) from exc
            if spec.shortcut:
                return QKeySequence(spec.shortcut)
            return None

        @staticmethod
        def _tooltip(
            tooltip: str, sequence: QKeySequence | None
        ) -> str:
            if sequence is None or sequence.isEmpty():
                return tooltip
            rendered = sequence.toString(QKeySequence.NativeText)
            return f"{tooltip} ({rendered})" if rendered else tooltip


else:
    class QtActionRegistry:
        """Import-safe placeholder for a damaged installation without PyQt5."""

        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError(
                "PyQt5 is required for the PyCForge action registry"
            ) from _QT_ERROR


__all__ = [
    "ActionHandler",
    "ActionStateProvider",
    "QT_ACTIONS_AVAILABLE",
    "QtActionRegistry",
]
