"""Pipeline stage for explicit closed-world module resolution."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from pycforge.converter.contracts.configuration import (
    MAX_IMPORT_ITEMS,
    supports_keyword_only_calls,
    supports_modules,
    supports_records,
)
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.enums import Severity, StageTerminal
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.core.stage_outcome import StageOutcome
from pycforge.converter.frontend.validation import validate_python_ir
from pycforge.converter.ir.python_ir import Provenance, PythonIRModule, PythonIRNode

from .analysis import ExplicitModuleAnalyzer
from .model import ModuleAnalysisCanceled, ModuleResolutionError


def _freeze_field(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((key, _freeze_field(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_field(item) for item in value)
    return value


def _python_ir_value(value: dict[str, Any]) -> PythonIRModule:
    nodes = []
    for item in value["nodes"]:
        provenance = item["provenance"]
        nodes.append(
            PythonIRNode(
                item["node_id"],
                item["kind"],
                tuple(
                    (key, _freeze_field(field_value))
                    for key, field_value in item["fields"].items()
                ),
                Provenance(
                    provenance["origin_kind"],
                    provenance.get("source_span"),
                    tuple(provenance.get("origin_node_ids", ())),
                ),
            )
        )
    return PythonIRModule(
        value["schema_version"],
        value["document_id"],
        value["root_node_id"],
        tuple(nodes),
    )


def _artifact(prior: StageArtifact, payload: dict[str, object]) -> StageArtifact:
    artifact_fingerprint = fingerprint(
        "stage-artifact",
        {
            "kind": "python_ir",
            "conversion_id": prior.conversion_id,
            "parent": prior.artifact_fingerprint.value,
            "payload": payload,
        },
    )
    return StageArtifact(
        "python_ir",
        "0.4",
        prior.conversion_id,
        prior.artifact_fingerprint,
        MappingProxyType(payload),
        artifact_fingerprint,
    )


class ModuleResolutionStage:
    stage_id = "modules.resolve"
    input_schema = "python-ir-bundle/0.4"
    input_schemas = ("python-ir/0.3", "python-ir-bundle/0.4")
    output_schema = "python-ir/0.4"

    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        request = services.context.canonical.request
        if not supports_modules(request.rule_set_version):
            return StageOutcome(StageTerminal.COMPLETED, artifact)
        if services.context.cancellation.is_canceled:
            return self._canceled()
        try:
            product = ExplicitModuleAnalyzer(
                artifact.payload["python_ir_bundle"],
                artifact.payload["source_bundle"],
                max_import_edges=min(request.resource_policy.max_import_edges, MAX_IMPORT_ITEMS),
                cancellation=services.context.cancellation,
                invalidation_dependency=artifact.artifact_fingerprint.value,
                allow_records=supports_records(request.rule_set_version),
                allow_required_keyword_only=supports_keyword_only_calls(
                    request.rule_set_version
                ),
            ).analyze()
        except ModuleAnalysisCanceled:
            return self._canceled()
        except ModuleResolutionError as exc:
            return StageOutcome(
                StageTerminal.REJECTED,
                diagnostics=(
                    Diagnostic(
                        exc.code,
                        Severity.ERROR,
                        self.stage_id,
                        exc.message,
                        source_span=exc.source_span,
                        related_spans=exc.related_spans,
                        source_module_id=exc.module_id,
                        source_logical_name=exc.logical_name,
                    ),
                ),
            )

        payload: dict[str, object] = {
            "stage_order": tuple(artifact.payload["stage_order"]) + (self.stage_id,),
            "python_ir": product.python_ir,
            "module_bundle": product.module_bundle,
            "module_resolution": product.module_resolution,
            "module_fact_tables": product.module_fact_tables,
            "module_import_node_ids": product.module_import_node_ids,
            "module_function_by_node": product.module_function_by_node,
            "module_bundle_assembly_node_id": product.module_bundle_assembly_node_id,
        }
        if supports_records(request.rule_set_version):
            payload["module_record_by_node"] = product.module_record_by_node
        return StageOutcome(StageTerminal.COMPLETED, _artifact(artifact, payload))

    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        request = services.context.canonical.request
        if not supports_modules(request.rule_set_version):
            return (
                artifact.kind == "python_ir" and artifact.schema_version == "0.3",
                "historical Python IR pass-through changed its contract",
            )
        if artifact.kind != "python_ir" or artifact.schema_version != "0.4":
            return False, "module resolver did not publish python-ir/0.4"
        python_ir = artifact.payload.get("python_ir")
        if not isinstance(python_ir, dict):
            return False, "module resolver omitted flattened Python IR"
        source_documents = frozenset(
            item["document_id"]
            for item in artifact.payload.get("module_bundle", {}).get("documents", ())
        )
        valid, message = validate_python_ir(
            _python_ir_value(python_ir),
            allowed_document_ids=source_documents,
        )
        if not valid:
            return False, message
        table_ids = {
            item.get("table_id") for item in artifact.payload.get("module_fact_tables", ())
        }
        required = {
            "module-identity-facts",
            "module-import-facts",
            "module-function-facts",
            "module-initialization-facts",
            "module-namespace-facts",
            "module-source-facts",
        }
        if not required.issubset(table_ids):
            return False, "module resolver omitted required complete fact tables"
        node_ids = {node["node_id"] for node in python_ir["nodes"]}
        for table in artifact.payload.get("module_fact_tables", ()):
            for record in table.get("records", ()):
                source_ids = record.get("provenance", {}).get("source_node_ids", ())
                if not source_ids or any(node_id not in node_ids for node_id in source_ids):
                    return False, "module fact provenance is missing or references an absent node"
        return True, ""

    def _canceled(self) -> StageOutcome:
        return StageOutcome(
            StageTerminal.CANCELED,
            diagnostics=(
                Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during module resolution",
                ),
            ),
        )
