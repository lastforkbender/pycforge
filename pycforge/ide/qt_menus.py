"""Native-semantics PyQt menu surfaces for the PyCForge action registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .action_contract import (
    MAIN_MENU_SURFACES,
    SURFACE_SPECS,
    PlacementKind,
    SurfaceKind,
    SurfaceSpec,
)
from .qt_actions import QT_ACTIONS_AVAILABLE, QtActionRegistry


if QT_ACTIONS_AVAILABLE:
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtWidgets import (
        QAbstractScrollArea,
        QAction,
        QMenu,
        QMenuBar,
        QToolBar,
        QToolButton,
        QWidget,
    )
    from .visual_tokens import PYCFORGE_METRICS
    QT_MENUS_AVAILABLE = True
    _QT_ERROR = None
else:
    QT_MENUS_AVAILABLE = False
    _QT_ERROR = RuntimeError("PyQt5 is unavailable")


if QT_MENUS_AVAILABLE:
    class PyCForgeMenu(QMenu):
        """A styled QMenu that leaves native interaction semantics intact."""

        def __init__(
            self,
            surface: SurfaceSpec,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(surface.title, parent)
            self.surface_id = surface.surface_id
            self.setObjectName("PyCForgeMenu")
            self.setAccessibleName(surface.accessible_name)
            self.setProperty("pycforgeSurfaceId", surface.surface_id)
            self.setProperty("pycforgeTone", "normal")
            self.setSeparatorsCollapsible(True)
            self.setToolTipsVisible(True)
            self.setProperty(
                "pycforgeIconSize", PYCFORGE_METRICS.icon_menu
            )
            self.hovered.connect(self._project_hover_tone)
            self.aboutToHide.connect(self._clear_hover_tone)

        def _project_hover_tone(self, action: QAction) -> None:
            tone = str(action.property("pycforgeTone") or "normal")
            if tone != self.property("pycforgeTone"):
                self.setProperty("pycforgeTone", tone)
                self._refresh_style()

        def _clear_hover_tone(self) -> None:
            if self.property("pycforgeTone") != "normal":
                self.setProperty("pycforgeTone", "normal")
                self._refresh_style()

        def _refresh_style(self) -> None:
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()


    class QtMenuFactory:
        """Compose menus and toolbars solely from declared action placements."""

        def __init__(
            self,
            registry: QtActionRegistry,
            parent: QWidget,
        ) -> None:
            if not isinstance(registry, QtActionRegistry):
                raise TypeError("registry must be a QtActionRegistry")
            if parent is None:
                raise TypeError("parent must be a QWidget")
            self.registry = registry
            self.parent = parent
            self._menus: dict[str, PyCForgeMenu] = {}
            self._context_targets: dict[str, object] = {}
            self._main_menus: tuple[PyCForgeMenu, ...] = ()
            self._context_connections: list[
                tuple[QWidget, Callable[[QPoint], None]]
            ] = []

        def menu(self, surface_id: str) -> PyCForgeMenu:
            """Return one persistent native menu for a declared menu surface."""

            surface = self._surface(surface_id)
            if surface.kind is SurfaceKind.TOOLBAR:
                raise ValueError(
                    f"toolbar cannot be materialized as a menu: {surface_id}"
                )
            existing = self._menus.get(surface_id)
            if existing is not None:
                return existing
            menu = PyCForgeMenu(surface, self.parent)
            self._menus[surface_id] = menu
            self._populate(menu, surface)
            menu.aboutToShow.connect(
                lambda menu=menu, surface=surface:
                self._menu_opening(menu, surface)
            )
            menu.aboutToHide.connect(
                lambda surface_id=surface_id:
                self._menu_closing(surface_id)
            )
            return menu

        def install_main_menus(
            self, menu_bar: QMenuBar
        ) -> tuple[PyCForgeMenu, ...]:
            """Install the declared top-level menus exactly once."""

            if not isinstance(menu_bar, QMenuBar):
                raise TypeError("menu_bar must be a QMenuBar")
            if self._main_menus:
                return self._main_menus
            menu_bar.setObjectName("PyCForgeMenuBar")
            menu_bar.setAccessibleName("PyCForge application menus")
            menu_bar.setNativeMenuBar(False)
            menus = tuple(
                self.menu(surface_id)
                for surface_id in MAIN_MENU_SURFACES
            )
            for menu in menus:
                menu_bar.addMenu(menu)
            self._main_menus = menus
            return menus

        def populate_toolbar(
            self,
            toolbar: QToolBar,
            surface_id: str = "toolbar.workspace",
        ) -> tuple[QAction, ...]:
            """Populate one toolbar with the registry's QAction identities."""

            if not isinstance(toolbar, QToolBar):
                raise TypeError("toolbar must be a QToolBar")
            surface = self._surface(surface_id)
            if surface.kind is not SurfaceKind.TOOLBAR:
                raise ValueError(
                    f"surface is not a toolbar: {surface_id}"
                )
            toolbar.clear()
            toolbar.setWindowTitle(surface.title)
            toolbar.setAccessibleName(surface.accessible_name)
            toolbar.setProperty("pycforgeSurfaceId", surface.surface_id)
            added: list[QAction] = []
            for placement in surface.placements:
                if placement.kind is PlacementKind.SEPARATOR:
                    toolbar.addSeparator()
                    continue
                if placement.kind is not PlacementKind.ACTION:
                    raise ValueError(
                        f"unsupported toolbar placement: {placement.kind}"
                    )
                action = self.registry.action(placement.target)
                toolbar.addAction(action)
                added.append(action)
            for action in added:
                button = toolbar.widgetForAction(action)
                if isinstance(button, QToolButton):
                    action_id = str(action.data())
                    self.registry.bind_tool_button(action_id, button)
            return tuple(added)

        def exec_context(
            self,
            surface_id: str,
            target: object,
            global_position: QPoint,
        ) -> QAction | None:
            """Execute a context menu with Qt's native placement/dismissal."""

            surface = self._surface(surface_id)
            if surface.kind is not SurfaceKind.CONTEXT:
                raise ValueError(
                    f"surface is not a context menu: {surface_id}"
                )
            menu = self.menu(surface_id)
            self._context_targets[surface_id] = target
            self.registry.set_active_context(surface_id, target)
            try:
                return menu.exec_(global_position)
            finally:
                self._context_targets.pop(surface_id, None)
                if self.registry.active_surface_id == surface_id:
                    self.registry.clear_active_context()

        def install_context_menu(
            self,
            widget: QWidget,
            surface_id: str,
            *,
            target_resolver: Callable[[], object] | None = None,
        ) -> None:
            """Replace a widget's implicit menu with a declared surface."""

            surface = self._surface(surface_id)
            if surface.kind is not SurfaceKind.CONTEXT:
                raise ValueError(
                    f"surface is not a context menu: {surface_id}"
                )
            widget.setContextMenuPolicy(Qt.CustomContextMenu)

            def requested(position: QPoint) -> None:
                target = (
                    target_resolver()
                    if target_resolver is not None else widget
                )
                coordinate_widget = (
                    widget.viewport()
                    if isinstance(widget, QAbstractScrollArea)
                    else widget
                )
                anchor = (
                    coordinate_widget.rect().center()
                    if position.x() < 0 or position.y() < 0
                    else position
                )
                self.exec_context(
                    surface_id,
                    target,
                    coordinate_widget.mapToGlobal(anchor),
                )

            widget.customContextMenuRequested.connect(requested)
            self._context_connections.append((widget, requested))

        def action_ids(self, surface_id: str) -> tuple[str, ...]:
            """Return static action IDs in exact visual order."""

            surface = self._surface(surface_id)
            return tuple(
                placement.target
                for placement in surface.placements
                if placement.kind is PlacementKind.ACTION
            )

        def _populate(
            self, menu: PyCForgeMenu, surface: SurfaceSpec
        ) -> None:
            for placement in surface.placements:
                if placement.kind is PlacementKind.ACTION:
                    menu.addAction(
                        self.registry.action(placement.target)
                    )
                elif placement.kind is PlacementKind.SEPARATOR:
                    menu.addSeparator()
                elif placement.kind is PlacementKind.SUBMENU:
                    menu.addMenu(self.menu(placement.target))
                elif placement.kind is PlacementKind.DYNAMIC:
                    menu.addActions(
                        self.registry.dynamic_actions(placement.target)
                    )

        def _menu_opening(
            self, menu: PyCForgeMenu, surface: SurfaceSpec
        ) -> None:
            target = self._context_targets.get(surface.surface_id)
            self.registry.set_active_context(
                surface.surface_id, target
            )
            if any(
                item.kind is PlacementKind.DYNAMIC
                for item in surface.placements
            ):
                menu.clear()
                self._populate(menu, surface)

        def _menu_closing(self, surface_id: str) -> None:
            if (
                surface_id not in self._context_targets
                and self.registry.active_surface_id == surface_id
            ):
                self.registry.clear_active_context()

        @staticmethod
        def _surface(surface_id: str) -> SurfaceSpec:
            try:
                return SURFACE_SPECS[surface_id]
            except KeyError as exc:
                raise KeyError(
                    f"unknown PyCForge action surface: {surface_id}"
                ) from exc


else:
    class PyCForgeMenu:
        """Import-safe placeholder for a damaged installation without PyQt5."""

        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError(
                "PyQt5 is required for PyCForge menus"
            ) from _QT_ERROR


    class QtMenuFactory:
        """Import-safe placeholder for a damaged installation without PyQt5."""

        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError(
                "PyQt5 is required for PyCForge menus"
            ) from _QT_ERROR


__all__ = [
    "PyCForgeMenu",
    "QT_MENUS_AVAILABLE",
    "QtMenuFactory",
]
