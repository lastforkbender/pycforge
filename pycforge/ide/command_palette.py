"""Deterministic, bounded command-palette projection over declared actions.

The palette returns inert metadata and stable action IDs only.  It does not
accept handlers, evaluate command strings, or provide an execution mechanism;
the optional Qt adapter must resolve a selected ID through the sole declared
action registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .action_contract import ACTION_SPECS, ActionSpec, ActionState


MAX_COMMAND_PALETTE_RESULTS = 50
MAX_COMMAND_PALETTE_QUERY_CHARS = 256


@dataclass(frozen=True, slots=True)
class CommandPaletteItem:
    """One inert projection of a visible static action."""

    action_id: str
    label: str
    tooltip: str
    accessible_name: str
    icon_name: str | None
    shortcut: str | None
    shortcut_kind: str | None
    enabled: bool
    checked: bool | None
    tone: str


@dataclass(frozen=True, slots=True)
class CommandPaletteProjection:
    """A bounded result set plus its untruncated matching count."""

    query: str
    items: tuple[CommandPaletteItem, ...]
    total_count: int
    limit: int

    @property
    def truncated(self) -> bool:
        return self.total_count > len(self.items)


def strip_mnemonics(text: str) -> str:
    """Remove Qt mnemonic markers while preserving escaped ampersands."""

    if not isinstance(text, str):
        raise TypeError("action label must be text")
    rendered: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character != "&":
            rendered.append(character)
            index += 1
            continue
        if index + 1 < len(text) and text[index + 1] == "&":
            rendered.append("&")
            index += 2
            continue
        index += 1
    return "".join(rendered)


def _shortcut(spec: ActionSpec) -> tuple[str | None, str | None]:
    if spec.standard_shortcut:
        return spec.standard_shortcut, "standard"
    if spec.shortcut:
        return spec.shortcut, "literal"
    return None, None


def _rank(
    query_terms: tuple[str, ...],
    label: str,
    spec: ActionSpec,
    shortcut: str | None,
    declaration_index: int,
) -> tuple[int, int, str, str] | None:
    if not query_terms:
        return 0, declaration_index, "", spec.action_id
    normalized_label = label.casefold()
    normalized_id = spec.action_id.replace(".", " ").replace("_", " ").casefold()
    searchable = " ".join(
        (
            normalized_label,
            normalized_id,
            spec.tooltip.casefold(),
            spec.accessible_name.casefold(),
            (shortcut or "").casefold(),
        )
    )
    if any(term not in searchable for term in query_terms):
        return None
    joined = " ".join(query_terms)
    if normalized_label == joined:
        quality = 0
    elif normalized_label.startswith(joined):
        quality = 1
    elif all(
        any(word.startswith(term) for word in normalized_label.split())
        for term in query_terms
    ):
        quality = 2
    elif joined in normalized_label:
        quality = 3
    elif joined in normalized_id:
        quality = 4
    else:
        quality = 5
    return quality, declaration_index, normalized_label, spec.action_id


def project_command_palette(
    query: str = "",
    *,
    states: Mapping[str, ActionState] | None = None,
    action_specs: Mapping[str, ActionSpec] = ACTION_SPECS,
    limit: int = MAX_COMMAND_PALETTE_RESULTS,
) -> CommandPaletteProjection:
    """Project visible static actions under a deterministic absolute limit."""

    if not isinstance(query, str):
        raise TypeError("palette query must be text")
    if len(query) > MAX_COMMAND_PALETTE_QUERY_CHARS:
        raise ValueError(
            "palette query exceeds "
            f"{MAX_COMMAND_PALETTE_QUERY_CHARS} characters"
        )
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_COMMAND_PALETTE_RESULTS
    ):
        raise ValueError(
            f"palette result limit must be between 1 and "
            f"{MAX_COMMAND_PALETTE_RESULTS}"
        )
    if not isinstance(action_specs, Mapping):
        raise TypeError("action specs must be a mapping")
    projected_states = {} if states is None else dict(states)
    unknown = set(projected_states).difference(action_specs)
    if unknown:
        raise KeyError(f"state supplied for unknown actions: {sorted(unknown)}")
    if any(
        not isinstance(state, ActionState)
        for state in projected_states.values()
    ):
        raise TypeError("palette states must be ActionState values")

    normalized_query = " ".join(query.split())
    query_terms = tuple(normalized_query.casefold().split())
    ranked: list[
        tuple[tuple[int, int, str, str], CommandPaletteItem]
    ] = []
    for declaration_index, (action_id, spec) in enumerate(
        action_specs.items()
    ):
        if not isinstance(spec, ActionSpec):
            raise TypeError("palette action specs must be ActionSpec values")
        if action_id != spec.action_id:
            raise ValueError(f"action mapping key mismatch: {action_id}")
        if spec.dynamic:
            continue
        state = projected_states.get(action_id, ActionState())
        if not state.visible:
            continue
        label = strip_mnemonics(spec.menu_text)
        shortcut, shortcut_kind = _shortcut(spec)
        rank = _rank(
            query_terms,
            label,
            spec,
            shortcut,
            declaration_index,
        )
        if rank is None:
            continue
        ranked.append(
            (
                rank,
                CommandPaletteItem(
                    action_id=action_id,
                    label=label,
                    tooltip=spec.tooltip,
                    accessible_name=spec.accessible_name,
                    icon_name=spec.icon_name,
                    shortcut=shortcut,
                    shortcut_kind=shortcut_kind,
                    enabled=state.enabled,
                    checked=state.checked,
                    tone=spec.tone,
                ),
            )
        )
    ranked.sort(key=lambda record: record[0])
    return CommandPaletteProjection(
        normalized_query,
        tuple(item for _rank_value, item in ranked[:limit]),
        len(ranked),
        limit,
    )


filter_command_palette = project_command_palette


__all__ = [
    "MAX_COMMAND_PALETTE_QUERY_CHARS",
    "MAX_COMMAND_PALETTE_RESULTS",
    "CommandPaletteItem",
    "CommandPaletteProjection",
    "filter_command_palette",
    "project_command_palette",
    "strip_mnemonics",
]
