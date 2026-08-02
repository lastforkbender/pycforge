"""Immutable contracts for trusted, versioned support-template assets.

Support templates are project-owned structured C IR factories.  They are not a
runtime subsystem and Python input can never provide or select arbitrary text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from pycforge.converter.contracts.configuration import DEFAULT_HELPER_POLICY
from pycforge.converter.ir.c_ir import (
    CFunctionDefinition,
    CFunctionPrototype,
    CInclude,
)


HELPER_INTERFACE_ID = "pycforge-helper/1"
HELPER_REGISTRY_VERSION = DEFAULT_HELPER_POLICY

_HELPER_ID = re.compile(r"^pycf(?:\.[a-z][a-z0-9_]*)+$")
_VERSION = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


@dataclass(frozen=True, slots=True, order=True)
class HelperReference:
    """An exact helper identity; ranges and implicit latest versions are forbidden."""

    helper_id: str
    version: str

    def __post_init__(self) -> None:
        if not _HELPER_ID.fullmatch(self.helper_id):
            raise ValueError(f"invalid helper ID: {self.helper_id}")
        if not _VERSION.fullmatch(self.version):
            raise ValueError(f"invalid exact helper version: {self.version}")

    @property
    def canonical(self) -> str:
        return f"{self.helper_id}@{self.version}"

    @classmethod
    def parse(cls, value: str) -> "HelperReference":
        if not isinstance(value, str) or value.count("@") != 1:
            raise ValueError("helper requirement must be helper-id@exact-version")
        helper_id, version = value.split("@", 1)
        return cls(helper_id, version)


@dataclass(frozen=True, slots=True)
class HelperOwnershipContract:
    parameter_ownership: str
    return_ownership: str
    allocation: str
    lifetime: str
    cleanup: str

    def to_dict(self) -> dict[str, str]:
        return {
            "parameter_ownership": self.parameter_ownership,
            "return_ownership": self.return_ownership,
            "allocation": self.allocation,
            "lifetime": self.lifetime,
            "cleanup": self.cleanup,
        }


@dataclass(frozen=True, slots=True)
class HelperFailureContract:
    strategy: str
    preconditions: tuple[str, ...]
    violation_policy: str
    runtime_failure_channel: str

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "preconditions": list(self.preconditions),
            "violation_policy": self.violation_policy,
            "runtime_failure_channel": self.runtime_failure_channel,
        }


@dataclass(frozen=True, slots=True)
class HelperCIRAsset:
    reference: HelperReference
    includes: tuple[CInclude, ...]
    prototype: CFunctionPrototype
    definition: CFunctionDefinition


HelperFactory = Callable[[], HelperCIRAsset]


@dataclass(frozen=True, slots=True)
class HelperDefinition:
    reference: HelperReference
    interface_id: str
    target_contracts: tuple[str, ...]
    dependencies: tuple[HelperReference, ...]
    prospective_consumer: str
    earliest_eligible_phase: str
    summary: str
    semantic_obligations: tuple[str, ...]
    ownership: HelperOwnershipContract
    failure: HelperFailureContract
    cancellation_policy: str
    factory: HelperFactory

    def contract_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference.canonical,
            "helper_id": self.reference.helper_id,
            "version": self.reference.version,
            "interface_id": self.interface_id,
            "target_contracts": list(self.target_contracts),
            "dependencies": [item.canonical for item in self.dependencies],
            "prospective_consumer": self.prospective_consumer,
            "earliest_eligible_phase": self.earliest_eligible_phase,
            "summary": self.summary,
            "semantic_obligations": list(self.semantic_obligations),
            "ownership": self.ownership.to_dict(),
            "failure": self.failure.to_dict(),
            "cancellation_policy": self.cancellation_policy,
            "factory_kind": "structured-c-ir",
        }


@dataclass(frozen=True, slots=True)
class HelperManifestEntry:
    contract: HelperDefinition
    asset_fingerprint: str

    @property
    def reference(self) -> HelperReference:
        return self.contract.reference

    def to_dict(self) -> dict[str, object]:
        return {
            **self.contract.contract_dict(),
            "asset_fingerprint": self.asset_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ResolvedHelperPlan:
    target_contract: str
    registry_version: str
    requirements: tuple[HelperReference, ...]
    assets: tuple[HelperCIRAsset, ...]
    manifest: tuple[HelperManifestEntry, ...]
    registry_fingerprint: str
    manifest_fingerprint: str

    def manifest_dicts(self) -> tuple[dict[str, object], ...]:
        return tuple(item.to_dict() for item in self.manifest)
