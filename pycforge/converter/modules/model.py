"""Immutable values published by explicit SourceBundle module resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ModuleResolutionError(Exception):
    """A deterministic source rejection discovered during module resolution."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        module_id: str,
        logical_name: str,
        source_span: dict[str, Any],
        related_spans: tuple[dict[str, Any], ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.module_id = module_id
        self.logical_name = logical_name
        self.source_span = source_span
        self.related_spans = related_spans


class ModuleAnalysisCanceled(Exception):
    """Internal control signal used to preserve cancellation semantics."""


@dataclass(frozen=True, slots=True)
class ModuleResolutionProduct:
    """Closed result passed from module analysis to the cumulative analyzer."""

    python_ir: dict[str, Any]
    module_bundle: dict[str, Any]
    module_resolution: dict[str, Any]
    module_fact_tables: tuple[dict[str, Any], ...]
    module_import_node_ids: tuple[str, ...]
    module_function_by_node: dict[str, dict[str, Any]]
    module_record_by_node: dict[str, dict[str, Any]]
    module_bundle_assembly_node_id: str


@dataclass(frozen=True, slots=True)
class ResolvedImport:
    import_item_id: str
    import_node_id: str
    alias_node_id: str
    importer_module_id: str
    target_module_id: str
    imported_name: str
    local_name: str
    target_function_node_id: str
    source_ordinal: int

    def to_fact(self) -> dict[str, Any]:
        return {
            "import_item_id": self.import_item_id,
            "import_node_id": self.import_node_id,
            "alias_node_id": self.alias_node_id,
            "importer_module_id": self.importer_module_id,
            "target_module_id": self.target_module_id,
            "imported_name": self.imported_name,
            "local_name": self.local_name,
            "target_function_node_id": self.target_function_node_id,
            "source_ordinal": self.source_ordinal,
            "supported": True,
        }
