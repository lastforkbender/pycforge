"""Frozen support-template registry and exact dependency resolver."""

from __future__ import annotations

import heapq
from dataclasses import fields, is_dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Iterable

from pycforge.converter.c_output import CRenderer, validate_c_text
from pycforge.converter.contracts.configuration import SUPPORTED_TARGET_CONTRACTS
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.ir.c_ir import (
    CProvenance,
    CStorage,
    CTranslationUnitBuilder,
    HELPER_SCHEMA_VERSION,
    serialize_translation_unit,
    validate_translation_unit,
)

from .factories import builtin_definitions
from .model import (
    HELPER_INTERFACE_ID,
    HELPER_REGISTRY_VERSION,
    HelperCIRAsset,
    HelperDefinition,
    HelperManifestEntry,
    HelperReference,
    ResolvedHelperPlan,
)


class HelperRegistryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class HelperResolutionCanceled(Exception):
    pass


class FrozenHelperRegistry:
    """Immutable project registry; registration order has no semantic effect."""

    def __init__(
        self,
        definitions: Iterable[HelperDefinition],
        *,
        registry_version: str = HELPER_REGISTRY_VERSION,
        interface_id: str = HELPER_INTERFACE_ID,
    ) -> None:
        ordered = tuple(sorted(definitions, key=lambda item: item.reference.canonical))
        references = [item.reference.canonical for item in ordered]
        if len(references) != len(set(references)):
            duplicate = next(item for item in references if references.count(item) > 1)
            raise HelperRegistryError("PYC3307", f"duplicate helper identity: {duplicate}")
        if not registry_version:
            raise HelperRegistryError("PYC3306", "helper registry version is empty")
        self.registry_version = registry_version
        self.interface_id = interface_id
        definitions_by_reference: dict[str, HelperDefinition] = {}
        assets_by_reference: dict[str, HelperCIRAsset] = {}
        entries_by_reference: dict[str, HelperManifestEntry] = {}
        rendered_by_reference: dict[str, str] = {}
        for definition in ordered:
            self._validate_contract(definition)
            try:
                asset = definition.factory()
            except Exception as exc:
                raise HelperRegistryError(
                    "PYC3306",
                    f"helper factory failed for {definition.reference.canonical}: {type(exc).__name__}",
                ) from None
            unit, rendered = self._validate_asset(definition, asset)
            asset_fingerprint = fingerprint(
                "helper-c-ir-asset",
                {
                    "contract": definition.contract_dict(),
                    "c_ir": serialize_translation_unit(unit),
                },
            ).value
            key = definition.reference.canonical
            definitions_by_reference[key] = definition
            assets_by_reference[key] = asset
            entries_by_reference[key] = HelperManifestEntry(definition, asset_fingerprint)
            rendered_by_reference[key] = rendered
        self._definitions = MappingProxyType(definitions_by_reference)
        self._assets = MappingProxyType(assets_by_reference)
        self._entries = MappingProxyType(entries_by_reference)
        self._rendered = MappingProxyType(rendered_by_reference)
        self._manifest = tuple(self._entries[key] for key in sorted(self._entries))
        self._fingerprint = fingerprint(
            "helper-registry-manifest",
            {
                "registry_version": self.registry_version,
                "interface_id": self.interface_id,
                "helpers": [item.to_dict() for item in self._manifest],
            },
        ).value

    @property
    def manifest(self) -> tuple[dict[str, object], ...]:
        return tuple(item.to_dict() for item in self._manifest)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def rendered_asset(self, reference: HelperReference | str) -> str:
        parsed = self._reference(reference)
        try:
            return self._rendered[parsed.canonical]
        except KeyError:
            raise HelperRegistryError("PYC3302", f"missing helper: {parsed.canonical}") from None

    def resolve(
        self,
        requirements: Iterable[HelperReference | str],
        *,
        target_contract: str,
        cancellation: object | None = None,
    ) -> ResolvedHelperPlan:
        if target_contract not in SUPPORTED_TARGET_CONTRACTS:
            raise HelperRegistryError(
                "PYC3304",
                f"unknown helper target contract: {target_contract}",
            )
        roots: dict[str, HelperReference] = {}
        for requirement in requirements:
            self._check_cancellation(cancellation)
            reference = self._reference(requirement)
            roots[reference.canonical] = reference
        root_references = tuple(roots[key] for key in sorted(roots))

        closure: dict[str, HelperDefinition] = {}
        pending = list(roots)
        heapq.heapify(pending)
        while pending:
            self._check_cancellation(cancellation)
            key = heapq.heappop(pending)
            if key in closure:
                continue
            definition = self._definitions.get(key)
            if definition is None:
                raise HelperRegistryError("PYC3302", f"missing helper dependency: {key}")
            if definition.interface_id != self.interface_id:
                raise HelperRegistryError(
                    "PYC3305",
                    f"helper interface mismatch for {key}: {definition.interface_id}",
                )
            if target_contract not in definition.target_contracts:
                raise HelperRegistryError(
                    "PYC3304",
                    f"helper {key} is incompatible with target contract {target_contract}",
                )
            closure[key] = definition
            for dependency in definition.dependencies:
                if dependency.canonical not in closure:
                    heapq.heappush(pending, dependency.canonical)

        indegree = {key: 0 for key in closure}
        consumers: dict[str, list[str]] = {key: [] for key in closure}
        for key, definition in closure.items():
            for dependency in definition.dependencies:
                dependency_key = dependency.canonical
                if dependency_key not in closure:
                    raise HelperRegistryError(
                        "PYC3302",
                        f"missing helper dependency: {dependency_key} required by {key}",
                    )
                indegree[key] += 1
                consumers[dependency_key].append(key)
        ready = [key for key, count in indegree.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while ready:
            self._check_cancellation(cancellation)
            key = heapq.heappop(ready)
            ordered.append(key)
            for consumer in sorted(consumers[key]):
                indegree[consumer] -= 1
                if indegree[consumer] == 0:
                    heapq.heappush(ready, consumer)
        if len(ordered) != len(closure):
            remaining = {key for key, count in indegree.items() if count > 0}
            cycle = self._cycle_path(remaining, closure)
            raise HelperRegistryError(
                "PYC3303",
                "helper dependency cycle: " + " -> ".join(cycle),
            )

        assets = tuple(self._assets[key] for key in ordered)
        manifest = tuple(self._entries[key] for key in ordered)
        manifest_dicts = [item.to_dict() for item in manifest]
        manifest_fingerprint = fingerprint(
            "helper-manifest",
            {
                "registry_version": self.registry_version,
                "target_contract": target_contract,
                "requirements": [item.canonical for item in root_references],
                "helpers": manifest_dicts,
            },
        ).value
        return ResolvedHelperPlan(
            target_contract,
            self.registry_version,
            root_references,
            assets,
            manifest,
            self.fingerprint,
            manifest_fingerprint,
        )

    def _validate_contract(self, definition: HelperDefinition) -> None:
        if definition.interface_id != self.interface_id:
            raise HelperRegistryError(
                "PYC3305",
                f"helper interface mismatch for {definition.reference.canonical}: {definition.interface_id}",
            )
        if not definition.target_contracts or tuple(sorted(set(definition.target_contracts))) != definition.target_contracts:
            raise HelperRegistryError("PYC3304", f"helper target contracts must be unique and sorted: {definition.reference.canonical}")
        if any(item not in SUPPORTED_TARGET_CONTRACTS for item in definition.target_contracts):
            raise HelperRegistryError("PYC3304", f"helper declares an unknown target contract: {definition.reference.canonical}")
        dependency_keys = tuple(item.canonical for item in definition.dependencies)
        if dependency_keys != tuple(sorted(set(dependency_keys))):
            raise HelperRegistryError("PYC3306", f"helper dependencies must be exact, unique, and sorted: {definition.reference.canonical}")
        if definition.reference in definition.dependencies:
            raise HelperRegistryError("PYC3303", f"helper directly depends on itself: {definition.reference.canonical}")
        if not definition.semantic_obligations or tuple(sorted(set(definition.semantic_obligations))) != definition.semantic_obligations:
            raise HelperRegistryError("PYC3306", f"helper lacks semantic obligations: {definition.reference.canonical}")
        if not definition.prospective_consumer or not definition.earliest_eligible_phase:
            raise HelperRegistryError("PYC3306", f"helper lacks prospective-consumer gate data: {definition.reference.canonical}")
        if not callable(definition.factory):
            raise HelperRegistryError("PYC3306", f"helper lacks a C IR factory: {definition.reference.canonical}")
        contract_strings = (
            *definition.ownership.to_dict().values(),
            definition.failure.strategy,
            definition.failure.violation_policy,
            definition.failure.runtime_failure_channel,
            definition.cancellation_policy,
        )
        if any(not isinstance(item, str) or not item for item in contract_strings) or not definition.failure.preconditions:
            raise HelperRegistryError("PYC3306", f"helper ownership/failure contract is incomplete: {definition.reference.canonical}")

    def _validate_asset(
        self,
        definition: HelperDefinition,
        asset: HelperCIRAsset,
    ) -> tuple[object, str]:
        reference = definition.reference
        if not isinstance(asset, HelperCIRAsset) or asset.reference != reference:
            raise HelperRegistryError("PYC3306", f"helper factory identity mismatch: {reference.canonical}")
        if asset.prototype.identifier.binding_id != asset.definition.identifier.binding_id:
            raise HelperRegistryError("PYC3306", f"helper prototype/definition binding mismatch: {reference.canonical}")
        if asset.prototype.storage is not CStorage.STATIC or asset.definition.storage is not CStorage.STATIC:
            raise HelperRegistryError("PYC3306", f"helper must use internal static linkage: {reference.canonical}")
        provenance_values = tuple(self._provenance_values(asset))
        if any(
            not isinstance(item, CProvenance)
            or item.origin_kind != "support-template"
            or item.source_document_id is not None
            or item.source_node_ids
            or item.rule_plan_id is not None
            for item in provenance_values
        ):
            raise HelperRegistryError("PYC3306", f"helper provenance is not isolated from source provenance: {reference.canonical}")
        primary_unit = None
        primary_rendered = None
        for target_contract in definition.target_contracts:
            builder = CTranslationUnitBuilder(
                target_contract,
                node_id=f"c-helper-tu-{reference.helper_id.replace('.', '-')}-{reference.version.replace('.', '-')}",
                provenance=CProvenance("support-template"),
                schema_version=HELPER_SCHEMA_VERSION,
            )
            for include in asset.includes:
                builder.add_include(include)
            builder.add_declaration(asset.prototype)
            builder.add_declaration(asset.definition)
            unit = builder.build()
            validation = validate_translation_unit(unit)
            if not validation.accepted:
                raise HelperRegistryError(
                    "PYC3306",
                    f"invalid structured C IR helper {reference.canonical}: {'; '.join(validation.errors)}",
                )
            rendered = CRenderer().render(unit).text
            conformance = validate_c_text(rendered)
            if not conformance.accepted:
                raise HelperRegistryError(
                    "PYC3306",
                    f"helper text conformance failed for {reference.canonical}: {conformance.message}",
                )
            if primary_unit is None:
                primary_unit = unit
                primary_rendered = rendered
        assert primary_unit is not None and primary_rendered is not None
        return primary_unit, primary_rendered

    @classmethod
    def _provenance_values(cls, value: object):
        if isinstance(value, CProvenance):
            yield value
            return
        if isinstance(value, tuple):
            for item in value:
                yield from cls._provenance_values(item)
            return
        if is_dataclass(value):
            for field in fields(value):
                yield from cls._provenance_values(getattr(value, field.name))

    @staticmethod
    def _reference(value: HelperReference | str) -> HelperReference:
        if isinstance(value, HelperReference):
            return value
        try:
            return HelperReference.parse(value)
        except (TypeError, ValueError) as exc:
            raise HelperRegistryError("PYC3301", str(exc)) from None

    @staticmethod
    def _check_cancellation(cancellation: object | None) -> None:
        if cancellation is not None and bool(getattr(cancellation, "is_canceled", False)):
            raise HelperResolutionCanceled

    @staticmethod
    def _cycle_path(
        remaining: set[str],
        closure: dict[str, HelperDefinition],
    ) -> tuple[str, ...]:
        state: dict[str, int] = {}
        for start in sorted(remaining):
            if state.get(start, 0):
                continue
            path: list[str] = [start]
            positions = {start: 0}
            state[start] = 1
            stack: list[tuple[str, int, tuple[str, ...]]] = [
                (
                    start,
                    0,
                    tuple(
                        sorted(
                            dependency.canonical
                            for dependency in closure[start].dependencies
                            if dependency.canonical in remaining
                        )
                    ),
                )
            ]
            while stack:
                node, index, dependencies = stack[-1]
                if index >= len(dependencies):
                    stack.pop()
                    state[node] = 2
                    positions.pop(node, None)
                    if path and path[-1] == node:
                        path.pop()
                    continue
                dependency = dependencies[index]
                stack[-1] = (node, index + 1, dependencies)
                dependency_state = state.get(dependency, 0)
                if dependency_state == 1:
                    return tuple(path[positions[dependency]:] + [dependency])
                if dependency_state == 2:
                    continue
                state[dependency] = 1
                positions[dependency] = len(path)
                path.append(dependency)
                next_dependencies = tuple(
                    sorted(
                        item.canonical
                        for item in closure[dependency].dependencies
                        if item.canonical in remaining
                    )
                )
                stack.append((dependency, 0, next_dependencies))
        return tuple(sorted(remaining))


@lru_cache(maxsize=1)
def default_helper_registry() -> FrozenHelperRegistry:
    return FrozenHelperRegistry(builtin_definitions())
