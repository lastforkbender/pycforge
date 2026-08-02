from __future__ import annotations
from dataclasses import dataclass, field
from pycforge.converter.contracts.configuration import (
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    DEFAULT_SEMANTIC_POLICY,
    DEFAULT_TARGET_CONTRACT,
)
from .resource_policy import ResourcePolicy

@dataclass(frozen=True, slots=True)
class SourceDocumentInput:
    logical_name: str
    text: str
    module_id: str | None = None

@dataclass(frozen=True, slots=True)
class SourceBundle:
    primary: SourceDocumentInput
    companions: tuple[SourceDocumentInput,...]=()

@dataclass(frozen=True, slots=True)
class ObservationOptions:
    trace_level: str="None"
    telemetry_enabled: bool=False

@dataclass(frozen=True, slots=True)
class ConversionRequest:
    source_bundle: SourceBundle
    python_version: str="3.11"
    target_contract: str=DEFAULT_TARGET_CONTRACT
    semantic_policy: str=DEFAULT_SEMANTIC_POLICY
    approximation_allowlist: tuple[str,...]=()
    rule_set_version: str=DEFAULT_RULE_SET
    renderer_version: str=DEFAULT_RENDERER
    helper_policy_version: str=DEFAULT_HELPER_POLICY
    container_policy_version: str=DEFAULT_CONTAINER_POLICY
    resource_policy: ResourcePolicy=field(default_factory=ResourcePolicy)
    module_policy_version: str=DEFAULT_MODULE_POLICY
    record_policy_version: str=DEFAULT_RECORD_POLICY
    numeric_policy_version: str=DEFAULT_NUMERIC_POLICY

    @classmethod
    def from_source(cls, source: str, logical_name: str="main.py", module_id: str="main", **kwargs: object) -> "ConversionRequest":
        return cls(SourceBundle(SourceDocumentInput(logical_name,source,module_id)), **kwargs)
