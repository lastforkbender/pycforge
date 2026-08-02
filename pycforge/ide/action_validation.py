"""Deterministic validation for the import-safe PyCForge action contract."""

from __future__ import annotations

import re
from typing import Mapping

from .action_contract import (
    ActionSpec,
    PlacementKind,
    SurfaceKind,
    SurfaceSpec,
)


def validate_action_contract(
    *,
    action_specs: Mapping[str, ActionSpec],
    surface_specs: Mapping[str, SurfaceSpec],
    dynamic_groups: Mapping[str, str],
) -> tuple[str, ...]:
    """Return stable contract errors without importing optional Qt."""

    errors: list[str] = []
    action_pattern = re.compile(
        r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
    )
    surface_pattern = re.compile(
        r"^(?:menu|toolbar|context)\.[a-z][a-z0-9_]*$"
    )
    shortcuts: dict[tuple[str, str, str], str] = {}
    for key, spec in sorted(action_specs.items()):
        if key != spec.action_id:
            errors.append(f"action mapping key mismatch: {key}")
        if not action_pattern.fullmatch(spec.action_id):
            errors.append(f"invalid action id: {spec.action_id}")
        if not spec.menu_text or not spec.tooltip or not spec.accessible_name:
            errors.append(f"incomplete action metadata: {spec.action_id}")
        mnemonics = _mnemonics(spec.menu_text)
        if not spec.dynamic and len(mnemonics) != 1:
            errors.append(
                f"action must declare one mnemonic: {spec.action_id}"
            )
        if "&" in spec.accessible_name or "&" in spec.toolbar_text:
            errors.append(f"presentation mnemonic leaked: {spec.action_id}")
        if spec.standard_shortcut and spec.shortcut:
            errors.append(
                f"ambiguous shortcut declaration: {spec.action_id}"
            )
        if spec.shortcut_context not in {"window", "widget"}:
            errors.append(f"invalid shortcut context: {spec.action_id}")
        if spec.tone not in {"normal", "primary", "danger"}:
            errors.append(f"invalid action tone: {spec.action_id}")
        sequence = spec.standard_shortcut or spec.shortcut
        if sequence:
            shortcut_key = (
                spec.shortcut_context,
                "standard" if spec.standard_shortcut else "literal",
                sequence.casefold(),
            )
            previous = shortcuts.get(shortcut_key)
            if previous:
                errors.append(
                    f"duplicate shortcut: {previous}, {spec.action_id}"
                )
            shortcuts[shortcut_key] = spec.action_id

    for group_id, action_id in sorted(dynamic_groups.items()):
        spec = action_specs.get(action_id)
        if not group_id or spec is None:
            errors.append(f"invalid dynamic group: {group_id}")
        elif not spec.dynamic:
            errors.append(
                f"dynamic template is not marked dynamic: {action_id}"
            )

    for key, surface in sorted(surface_specs.items()):
        _validate_surface(
            key,
            surface,
            action_specs,
            surface_specs,
            dynamic_groups,
            surface_pattern,
            errors,
        )
    return tuple(errors)


def _validate_surface(
    key: str,
    surface: SurfaceSpec,
    action_specs: Mapping[str, ActionSpec],
    surface_specs: Mapping[str, SurfaceSpec],
    dynamic_groups: Mapping[str, str],
    surface_pattern: re.Pattern[str],
    errors: list[str],
) -> None:
    if key != surface.surface_id:
        errors.append(f"surface mapping key mismatch: {key}")
    if not surface_pattern.fullmatch(surface.surface_id):
        errors.append(f"invalid surface id: {surface.surface_id}")
    if not surface.accessible_name:
        errors.append(
            f"missing surface accessible name: {surface.surface_id}"
        )
    if (
        surface.kind is SurfaceKind.MENU
        and len(_mnemonics(surface.title)) != 1
    ):
        errors.append(f"menu must declare one mnemonic: {surface.surface_id}")

    placements = surface.placements
    targets: set[tuple[PlacementKind, str]] = set()
    mnemonics: dict[str, str] = {}
    for index, placement in enumerate(placements):
        if placement.target:
            placement_key = (placement.kind, placement.target)
            if placement_key in targets:
                errors.append(
                    f"duplicate placement {placement.target} "
                    f"in {surface.surface_id}"
                )
            targets.add(placement_key)
        _validate_placement(
            placement,
            surface,
            action_specs,
            surface_specs,
            dynamic_groups,
            mnemonics,
            errors,
        )
        if placement.kind is PlacementKind.SEPARATOR and (
            index == 0
            or index == len(placements) - 1
            or placements[index - 1].kind is PlacementKind.SEPARATOR
        ):
            errors.append(f"misplaced separator in {surface.surface_id}")


def _validate_placement(
    placement,
    surface: SurfaceSpec,
    action_specs: Mapping[str, ActionSpec],
    surface_specs: Mapping[str, SurfaceSpec],
    dynamic_groups: Mapping[str, str],
    mnemonics: dict[str, str],
    errors: list[str],
) -> None:
    if placement.kind is PlacementKind.ACTION:
        spec = action_specs.get(placement.target)
        if spec is None:
            errors.append(
                f"unknown action {placement.target} in {surface.surface_id}"
            )
        elif spec.dynamic:
            errors.append(
                f"dynamic template placed directly: {placement.target}"
            )
        elif surface.kind is not SurfaceKind.TOOLBAR:
            _record_mnemonic(
                mnemonics,
                _mnemonics(spec.menu_text),
                placement.target,
                surface.surface_id,
                errors,
            )
    elif placement.kind is PlacementKind.SUBMENU:
        submenu = surface_specs.get(placement.target)
        if submenu is None or submenu.kind is not SurfaceKind.MENU:
            errors.append(
                f"unknown submenu {placement.target} in {surface.surface_id}"
            )
        else:
            _record_mnemonic(
                mnemonics,
                _mnemonics(submenu.title),
                placement.target,
                surface.surface_id,
                errors,
            )
    elif placement.kind is PlacementKind.DYNAMIC:
        if placement.target not in dynamic_groups:
            errors.append(
                f"unknown dynamic group {placement.target} "
                f"in {surface.surface_id}"
            )
    elif placement.target:
        errors.append(f"separator has a target in {surface.surface_id}")


def _mnemonics(text: str) -> tuple[str, ...]:
    markers: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "&":
            index += 1
            continue
        if index + 1 < len(text) and text[index + 1] == "&":
            index += 2
            continue
        if index + 1 < len(text):
            markers.append(text[index + 1].casefold())
        index += 1
    return tuple(markers)


def _record_mnemonic(
    owners: dict[str, str],
    mnemonics: tuple[str, ...],
    target: str,
    surface_id: str,
    errors: list[str],
) -> None:
    if len(mnemonics) != 1:
        return
    mnemonic = mnemonics[0]
    previous = owners.get(mnemonic)
    if previous is not None:
        errors.append(
            f"duplicate mnemonic {mnemonic!r} in {surface_id}: "
            f"{previous}, {target}"
        )
    else:
        owners[mnemonic] = target


__all__ = ["validate_action_contract"]
