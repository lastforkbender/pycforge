"""Headless contracts for PyCForge application actions and menu surfaces.

The declarations in this module contain no Qt objects.  They are the stable
source for action identity, user-facing text, shortcuts, accessibility, and
surface placement.  The optional Qt adapter materializes these declarations
without becoming a second source of action metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping


MAX_DYNAMIC_ACTIONS = 10
MAX_DYNAMIC_LABEL_CHARS = 160
MAX_DYNAMIC_TOOLTIP_CHARS = 4096


class PlacementKind(str, Enum):
    """Kinds of entries accepted by a declared action surface."""

    ACTION = "action"
    SEPARATOR = "separator"
    SUBMENU = "submenu"
    DYNAMIC = "dynamic"


class SurfaceKind(str, Enum):
    """Presentation roles supported by the Phase 15 action foundation."""

    MENU = "menu"
    TOOLBAR = "toolbar"
    CONTEXT = "context"


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """Complete immutable presentation contract for one application action."""

    action_id: str
    menu_text: str
    toolbar_text: str
    tooltip: str
    accessible_name: str
    icon_name: str | None = None
    standard_shortcut: str | None = None
    shortcut: str | None = None
    shortcut_context: str = "window"
    checkable: bool = False
    tone: str = "normal"
    dynamic: bool = False


@dataclass(frozen=True, slots=True)
class ActionState:
    """One bounded enabled/checked projection supplied by the application."""

    enabled: bool = True
    checked: bool | None = None
    visible: bool = True


@dataclass(frozen=True, slots=True)
class ActionPlacement:
    """An action, separator, submenu, or dynamic group in a surface."""

    kind: PlacementKind
    target: str = ""

    @classmethod
    def action(cls, action_id: str) -> "ActionPlacement":
        return cls(PlacementKind.ACTION, action_id)

    @classmethod
    def separator(cls) -> "ActionPlacement":
        return cls(PlacementKind.SEPARATOR)

    @classmethod
    def submenu(cls, surface_id: str) -> "ActionPlacement":
        return cls(PlacementKind.SUBMENU, surface_id)

    @classmethod
    def dynamic(cls, group_id: str) -> "ActionPlacement":
        return cls(PlacementKind.DYNAMIC, group_id)


@dataclass(frozen=True, slots=True)
class SurfaceSpec:
    """Declarative composition of one main, toolbar, or context surface."""

    surface_id: str
    kind: SurfaceKind
    title: str
    accessible_name: str
    placements: tuple[ActionPlacement, ...]


@dataclass(frozen=True, slots=True)
class DynamicActionEntry:
    """Validated data for one bounded parameterized action instance."""

    key: str
    label: str
    tooltip: str
    accessible_name: str
    payload: str
    enabled: bool = True


def _action(
    action_id: str,
    menu_text: str,
    tooltip: str,
    accessible_name: str,
    *,
    toolbar_text: str | None = None,
    icon_name: str | None = None,
    standard_shortcut: str | None = None,
    shortcut: str | None = None,
    shortcut_context: str = "window",
    checkable: bool = False,
    tone: str = "normal",
    dynamic: bool = False,
) -> ActionSpec:
    return ActionSpec(
        action_id=action_id,
        menu_text=menu_text,
        toolbar_text=toolbar_text or menu_text.replace("&", ""),
        tooltip=tooltip,
        accessible_name=accessible_name,
        icon_name=icon_name,
        standard_shortcut=standard_shortcut,
        shortcut=shortcut,
        shortcut_context=shortcut_context,
        checkable=checkable,
        tone=tone,
        dynamic=dynamic,
    )


# Row fields after the four required strings are:
# toolbar, icon, standard key, literal key, context, checkable, tone, dynamic.
_ACTION_ROWS = (
    ("file.open_python", "&Open Python…", "Open Python documents into the source bundle", "Open Python documents", "Open", "open", "Open", None, "window", False, "normal", False),
    ("file.open_recent", "Open Recent Python", "Open this recent Python document", "Open recent Python document", None, "open", None, None, "window", False, "normal", True),
    ("bundle.new_module", "&New Module", "Add a blank logical module to the source bundle", "Add source bundle module", "New Module", "add-document", "New", None, "window", False, "normal", False),
    ("bundle.remove_module", "&Remove Module", "Remove the selected module from the source bundle", "Remove selected source bundle module", None, "remove-document", None, "Ctrl+Shift+W", "window", False, "danger", False),
    ("bundle.move_up", "Move Module &Up", "Move the selected module one position earlier", "Move selected module up", None, "move-up", None, "Alt+Up", "widget", False, "normal", False),
    ("bundle.move_down", "Move Module &Down", "Move the selected module one position later", "Move selected module down", None, "move-down", None, "Alt+Down", "widget", False, "normal", False),
    ("bundle.make_primary", "Make &Primary", "Make the selected module the primary source document", "Make selected module primary", None, "primary-module", None, None, "window", False, "normal", False),
    ("file.save_python", "&Save Python", "Atomically save the active Python document", "Save active Python document", "Save Python", "save-python", "Save", None, "window", False, "normal", False),
    ("file.save_python_as", "Save Python &As…", "Atomically save the active document to a new Python path", "Save active Python document as", None, "save-as", "SaveAs", None, "window", False, "normal", False),
    ("output.set_destination", "Set C &Destination…", "Choose the explicit destination for generated C", "Set generated C destination", "C Destination", "link-c", None, "Ctrl+Shift+L", "window", False, "normal", False),
    ("output.save_c", "Save Generated &C", "Atomically save fresh generated C to its destination", "Save current generated C", "Save C", "save-c", None, "Ctrl+Alt+S", "window", False, "normal", False),
    ("conversion.convert", "&Transpile Source Bundle", "Transpile the complete logical source bundle to C source", "Transpile source bundle to C source", "Transpile", "convert", None, "Ctrl+Return", "window", False, "primary", False),
    ("conversion.cancel", "&Cancel Transpilation", "Cancel the current isolated transpilation", "Cancel current transpilation", "Cancel", "cancel", None, None, "window", False, "danger", False),
    ("edit.undo", "&Undo", "Undo the most recent source edit", "Undo source edit", None, "undo", "Undo", None, "window", False, "normal", False),
    ("edit.redo", "&Redo", "Redo the most recently undone source edit", "Redo source edit", None, "redo", "Redo", None, "window", False, "normal", False),
    ("edit.cut", "Cu&t", "Cut the selected writable text", "Cut selected text", None, "cut", "Cut", None, "window", False, "normal", False),
    ("edit.copy", "&Copy", "Copy the current selection", "Copy current selection", None, "copy", "Copy", None, "window", False, "normal", False),
    ("edit.paste", "&Paste", "Paste text into the writable source surface", "Paste text into source", None, "paste", "Paste", None, "window", False, "normal", False),
    ("edit.select_all", "Select &All", "Select all text or visible records in the focused surface", "Select all content", None, "select-all", "SelectAll", None, "window", False, "normal", False),
    ("edit.duplicate_line", "&Duplicate Line or Selection", "Duplicate the selected Python source lines", "Duplicate selected Python source lines", None, "duplicate-line", None, "Ctrl+Shift+D", "widget", False, "normal", False),
    ("edit.move_line_up", "Move &Line Up", "Move the selected Python source lines one line earlier", "Move selected Python source lines up", None, "move-line-up", None, "Alt+Shift+Up", "widget", False, "normal", False),
    ("edit.move_line_down", "Move Line Do&wn", "Move the selected Python source lines one line later", "Move selected Python source lines down", None, "move-line-down", None, "Alt+Shift+Down", "widget", False, "normal", False),
    ("edit.indent", "&Indent Lines", "Indent the selected Python source lines by four spaces", "Indent selected Python source lines", None, "indent", None, "Ctrl+]", "widget", False, "normal", False),
    ("edit.outdent", "&Outdent Lines", "Outdent the selected Python source lines by up to four spaces", "Outdent selected Python source lines", None, "outdent", None, "Ctrl+[", "widget", False, "normal", False),
    ("edit.toggle_comment", "Toggle Co&mment", "Toggle Python line comments for the selected source lines", "Toggle comments on selected Python source lines", None, "toggle-comment", None, "Ctrl+/", "widget", False, "normal", False),
    ("search.find", "&Find…", "Find text in the focused editor", "Find text", "Find", "find", "Find", None, "window", False, "normal", False),
    ("search.replace", "R&eplace…", "Find and replace text in Python source", "Find and replace Python source text", None, "replace", "Replace", None, "window", False, "normal", False),
    ("search.bundle", "Find in Source &Bundle…", "Search exact text across the already-open source bundle", "Find text in the open source bundle", "Bundle Search", "bundle-search", None, "Ctrl+Shift+F", "window", False, "normal", False),
    ("search.next_match", "Find &Next", "Move to the next literal search match", "Find next match", None, "next-match", "FindNext", None, "widget", False, "normal", False),
    ("search.previous_match", "Find Pre&vious", "Move to the previous literal search match", "Find previous match", None, "previous-match", None, "Shift+F3", "widget", False, "normal", False),
    ("search.replace_current", "Replace &Current", "Replace the active Python source match", "Replace current source match", None, "replace", None, None, "widget", False, "normal", False),
    ("search.replace_all", "Replace &All", "Replace every exact match in the active Python source document", "Replace all source matches", None, "replace", None, None, "widget", False, "normal", False),
    ("search.close", "&Close Find", "Close the find and replace controls", "Close find and replace", None, "close", None, "Escape", "widget", False, "normal", False),
    ("view.source_bundle", "Source &Bundle", "Show or hide the source bundle navigator", "Show or hide source bundle", None, "settings", None, "Ctrl+Alt+B", "window", True, "normal", False),
    ("view.generated_c", "Generated &C", "Show or hide the read-only generated C viewer", "Show or hide generated C", None, "view-c", None, "Ctrl+Shift+C", "window", True, "normal", False),
    ("view.conversion_details", "Transpilation &Details", "Show or hide structured transpilation details", "Show or hide transpilation details", None, "details", None, "Ctrl+Alt+D", "window", True, "normal", False),
    ("view.outline", "&Outline", "Show the bounded outline for already-open Python source", "Show Python source outline", None, "outline", None, "Ctrl+Shift+O", "window", False, "normal", False),
    ("view.conversion_history", "Transpilation &History", "Show bounded transpilation history for this application session", "Show current session transpilation history", None, "history", None, "Ctrl+Alt+H", "window", False, "normal", False),
    ("view.whitespace", "Show &Whitespace", "Show or hide whitespace marks in Python source views", "Show or hide Python source whitespace", None, "whitespace", None, "Ctrl+Alt+W", "window", True, "normal", False),
    ("view.split_source", "Split Python &View", "Show or hide a second synchronized Python source view", "Split the Python source editor", None, "split-view", None, "Ctrl+\\", "window", True, "normal", False),
    ("editor.toggle_fold", "Toggle Code Fold &State", "Fold or unfold the Python source region at the cursor", "Toggle Python source code fold", None, "toggle-fold", None, "Ctrl+Shift+[", "widget", False, "normal", False),
    ("navigation.go_to_line", "&Go to Line…", "Move to a line in the active Python source document", "Go to a Python source line", None, "go-to-line", None, "Ctrl+G", "window", False, "normal", False),
    ("workspace.command_palette", "&Command Palette…", "Search and invoke enabled declared PyCForge actions", "Open the PyCForge command palette", "Commands", "command-palette", None, "Ctrl+Shift+P", "window", False, "normal", False),
    ("tree.expand_all", "E&xpand All", "Expand every currently projected inspector branch", "Expand all inspector branches", None, "expand-all", None, None, "window", False, "normal", False),
    ("tree.collapse_all", "C&ollapse All", "Collapse every currently projected inspector branch", "Collapse all inspector branches", None, "collapse-all", None, None, "window", False, "normal", False),
    ("diagnostics.reveal_source", "&Reveal in Python Source", "Reveal the selected diagnostic in its Python source document", "Reveal selected diagnostic in Python source", None, "go-to-source", None, None, "window", False, "normal", False),
    ("mappings.reveal_output", "&Reveal in Generated C", "Reveal the selected mapping in read-only generated C", "Reveal selected mapping in generated C", None, "go-to-output", None, None, "window", False, "normal", False),
    ("mappings.reveal_source", "Reveal Source &Module", "Reveal the source module owned by the selected mapping", "Reveal selected mapping source module", None, "go-to-source", None, None, "window", False, "normal", False),
)


def _catalog_action(row: tuple[object, ...]) -> ActionSpec:
    (
        action_id, menu_text, tooltip, accessible_name, toolbar_text,
        icon_name, standard_shortcut, shortcut, shortcut_context,
        checkable, tone, dynamic,
    ) = row
    return _action(
        str(action_id), str(menu_text), str(tooltip), str(accessible_name),
        toolbar_text=None if toolbar_text is None else str(toolbar_text),
        icon_name=None if icon_name is None else str(icon_name),
        standard_shortcut=(
            None if standard_shortcut is None else str(standard_shortcut)
        ),
        shortcut=None if shortcut is None else str(shortcut),
        shortcut_context=str(shortcut_context),
        checkable=bool(checkable), tone=str(tone), dynamic=bool(dynamic),
    )


_ACTION_SPECS = tuple(_catalog_action(row) for row in _ACTION_ROWS)

ACTION_SPECS: Mapping[str, ActionSpec] = MappingProxyType(
    {spec.action_id: spec for spec in _ACTION_SPECS}
)

DYNAMIC_ACTION_GROUPS: Mapping[str, str] = MappingProxyType(
    {"recent_python": "file.open_recent"}
)


def _surface(
    surface_id: str,
    kind: SurfaceKind,
    title: str,
    accessible_name: str,
    *placements: ActionPlacement,
) -> SurfaceSpec:
    return SurfaceSpec(
        surface_id,
        kind,
        title,
        accessible_name,
        tuple(placements),
    )


def _layout(*tokens: str | None) -> tuple[ActionPlacement, ...]:
    placements: list[ActionPlacement] = []
    for token in tokens:
        if token is None:
            placements.append(ActionPlacement.separator())
        elif token.startswith(">"):
            placements.append(ActionPlacement.submenu(token[1:]))
        elif token.startswith("$"):
            placements.append(ActionPlacement.dynamic(token[1:]))
        else:
            placements.append(ActionPlacement.action(token))
    return tuple(placements)


_SURFACE_SPECS = (
    _surface(
        "menu.file", SurfaceKind.MENU, "&File", "File menu",
        *_layout(
            "file.open_python", ">menu.open_recent", None,
            "bundle.new_module", "bundle.remove_module", None,
            "file.save_python", "file.save_python_as", None,
            "output.set_destination", "output.save_c",
        ),
    ),
    _surface(
        "menu.open_recent", SurfaceKind.MENU, "Open Recen&t",
        "Open recent Python documents menu", *_layout("$recent_python"),
    ),
    _surface(
        "menu.edit", SurfaceKind.MENU, "&Edit", "Edit menu",
        *_layout(
            "edit.undo", "edit.redo", None, "edit.cut", "edit.copy",
            "edit.paste", "edit.select_all", None,
            "edit.duplicate_line", "edit.move_line_up",
            "edit.move_line_down", "edit.indent", "edit.outdent",
            "edit.toggle_comment", None, "search.find", "search.replace",
        ),
    ),
    _surface(
        "menu.view", SurfaceKind.MENU, "&View", "View menu",
        *_layout(
            "view.source_bundle", "view.generated_c",
            "view.conversion_details", None, "view.split_source",
            "view.whitespace", "editor.toggle_fold",
        ),
    ),
    _surface(
        "menu.navigate", SurfaceKind.MENU, "&Navigate", "Navigate menu",
        *_layout(
            "navigation.go_to_line", "search.bundle", "view.outline",
            "view.conversion_history", None,
            "workspace.command_palette",
        ),
    ),
    _surface(
        "menu.conversion", SurfaceKind.MENU, "&Transpile",
        "Transpile menu",
        *_layout("conversion.convert", "conversion.cancel"),
    ),
    _surface(
        "toolbar.workspace", SurfaceKind.TOOLBAR, "PyCForge Workspace",
        "PyCForge workspace actions",
        *_layout(
            "file.open_python", "file.save_python", None,
            "conversion.convert", "conversion.cancel", None,
            "view.generated_c", "view.conversion_details", "search.find",
            None, "output.set_destination", "output.save_c",
        ),
    ),
    _surface(
        "context.python_source", SurfaceKind.CONTEXT, "Python Source",
        "Python source editor menu",
        *_layout(
            "edit.undo", "edit.redo", None, "edit.cut", "edit.copy",
            "edit.paste", None, "edit.select_all", None,
            "edit.duplicate_line", "edit.move_line_up",
            "edit.move_line_down", "edit.indent", "edit.outdent",
            "edit.toggle_comment", None, "search.find",
            "search.replace", "navigation.go_to_line",
            "editor.toggle_fold",
        ),
    ),
    _surface(
        "context.generated_c", SurfaceKind.CONTEXT, "Generated C",
        "Generated C viewer menu",
        *_layout("edit.copy", "edit.select_all", None, "search.find"),
    ),
    _surface(
        "context.source_bundle", SurfaceKind.CONTEXT, "Source Bundle",
        "Source bundle menu",
        *_layout(
            "bundle.new_module", "bundle.remove_module", None,
            "bundle.move_up", "bundle.move_down", "bundle.make_primary",
        ),
    ),
    _surface(
        "context.document_tabs", SurfaceKind.CONTEXT, "Document Tabs",
        "Python document tabs menu",
        *_layout(
            "file.save_python", "file.save_python_as", None,
            "bundle.remove_module", "bundle.make_primary", None,
            "view.split_source",
        ),
    ),
    _surface(
        "context.diagnostics", SurfaceKind.CONTEXT, "Diagnostics",
        "Diagnostics menu",
        *_layout("edit.copy", None, "diagnostics.reveal_source"),
    ),
    _surface(
        "context.mappings", SurfaceKind.CONTEXT, "Mappings",
        "Source mappings menu",
        *_layout(
            "edit.copy", None, "mappings.reveal_output",
            "mappings.reveal_source",
        ),
    ),
    _surface(
        "context.bundle_search", SurfaceKind.CONTEXT, "Bundle Search",
        "Source bundle search results menu",
        *_layout("edit.copy"),
    ),
    _surface(
        "context.conversion_history", SurfaceKind.CONTEXT,
        "Transpilation History", "Transpilation history menu",
        *_layout("edit.copy"),
    ),
    _surface(
        "context.inspector", SurfaceKind.CONTEXT, "Inspector",
        "Inspector tree menu",
        *_layout(
            "edit.copy", None, "tree.expand_all", "tree.collapse_all",
        ),
    ),
    _surface(
        "context.text_input", SurfaceKind.CONTEXT, "Text Input",
        "Text editing menu",
        *_layout(
            "edit.undo", "edit.redo", None, "edit.cut", "edit.copy",
            "edit.paste", None, "edit.select_all",
        ),
    ),
    _surface(
        "context.read_only_text", SurfaceKind.CONTEXT, "Read-only Text",
        "Read-only text menu",
        *_layout("edit.copy", "edit.select_all"),
    ),
)

SURFACE_SPECS: Mapping[str, SurfaceSpec] = MappingProxyType(
    {spec.surface_id: spec for spec in _SURFACE_SPECS}
)

MAIN_MENU_SURFACES = (
    "menu.file",
    "menu.edit",
    "menu.view",
    "menu.navigate",
    "menu.conversion",
)


def validated_dynamic_entries(
    entries: Iterable[DynamicActionEntry],
) -> tuple[DynamicActionEntry, ...]:
    """Return bounded entries after rejecting ambiguous or oversized data."""

    records = tuple(entries)
    if len(records) > MAX_DYNAMIC_ACTIONS:
        raise ValueError(
            f"dynamic actions exceed the limit of {MAX_DYNAMIC_ACTIONS}"
        )
    seen: set[str] = set()
    for entry in records:
        if not isinstance(entry, DynamicActionEntry):
            raise TypeError("dynamic entries must be DynamicActionEntry values")
        if not entry.key or entry.key in seen:
            raise ValueError("dynamic action keys must be non-empty and unique")
        seen.add(entry.key)
        if not entry.label or len(entry.label) > MAX_DYNAMIC_LABEL_CHARS:
            raise ValueError("dynamic action label is empty or oversized")
        if (
            not entry.tooltip
            or len(entry.tooltip) > MAX_DYNAMIC_TOOLTIP_CHARS
        ):
            raise ValueError("dynamic action tooltip is empty or oversized")
        if not entry.accessible_name:
            raise ValueError("dynamic action accessible name is required")
        if not isinstance(entry.payload, str):
            raise TypeError("dynamic action payload must be text")
    return records


def validate_action_contract(
    *,
    action_specs: Mapping[str, ActionSpec] = ACTION_SPECS,
    surface_specs: Mapping[str, SurfaceSpec] = SURFACE_SPECS,
    dynamic_groups: Mapping[str, str] = DYNAMIC_ACTION_GROUPS,
) -> tuple[str, ...]:
    """Return deterministic contract errors without importing optional Qt."""

    from .action_validation import validate_action_contract as validate

    return validate(
        action_specs=action_specs,
        surface_specs=surface_specs,
        dynamic_groups=dynamic_groups,
    )


__all__ = [
    "ACTION_SPECS",
    "DYNAMIC_ACTION_GROUPS",
    "MAIN_MENU_SURFACES",
    "MAX_DYNAMIC_ACTIONS",
    "ActionPlacement",
    "ActionSpec",
    "ActionState",
    "DynamicActionEntry",
    "PlacementKind",
    "SURFACE_SPECS",
    "SurfaceKind",
    "SurfaceSpec",
    "validate_action_contract",
    "validated_dynamic_entries",
]
