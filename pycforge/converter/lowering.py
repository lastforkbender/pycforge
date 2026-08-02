from __future__ import annotations
import math
from dataclasses import fields, is_dataclass
from types import MappingProxyType
from typing import Any
from .contracts.configuration import (
    PHASE11_RULE_SET,
    supports_containers,
    supports_conditional_regions,
    supports_functions,
    supports_keyword_calls,
    supports_keyword_only_calls,
    supports_modules,
    supports_numeric,
    supports_records,
)
from .contracts.versions import (
    GENERATED_C_SCHEMA,
    PHASE14C_GENERATED_C_SCHEMA,
    PHASE14B_GENERATED_C_SCHEMA,
    PHASE14A_GENERATED_C_SCHEMA,
    PHASE13_GENERATED_C_SCHEMA,
    PHASE12_GENERATED_C_SCHEMA,
)
from .conditional_regions.lowering import bind_conditional_region_lowerer
from .containers.lowering import ContainerCIRLowerer, ContainerLoweringServices
from .core.diagnostics import Diagnostic
from .core.enums import Severity, StageTerminal
from .core.fingerprint import fingerprint
from .core.stage_artifact import StageArtifact
from .core.stage_outcome import StageOutcome
from .ir.c_ir import (
    CAssignmentStatement,
    CBinaryExpr,
    CBinaryOp,
    CBlock,
    CBooleanLiteral,
    CBreakStatement,
    CCallExpr,
    CContinueStatement,
    CExpressionStatement,
    CFloatLiteral,
    CForStatement,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIdentifierRef,
    CIfStatement,
    CInclude,
    CIntegerLiteral,
    CModuleManifestEntry,
    CParameter,
    CProvenance,
    CQualifier,
    CReturnStatement,
    CStorage,
    CStringLiteral,
    CTranslationUnitBuilder,
    CType,
    CUnaryExpr,
    CUnaryOp,
    CVariableDeclaration,
    CWhileStatement,
    CONDITIONAL_SCHEMA_VERSION,
    CONTAINER_SCHEMA_VERSION,
    MODULE_SCHEMA_VERSION,
    NUMERIC_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    KEYWORD_CALL_SCHEMA_VERSION,
    KEYWORD_ONLY_CALL_SCHEMA_VERSION,
    SCHEMA_VERSION,
    serialize_translation_unit,
    validate_translation_unit,
)
from .modules.lowering import enrich_source_output_mappings, ordered_function_ids
from .records.lowering import RecordCIRLowerer, RecordLoweringServices
from .numeric_semantics import bind_numeric_lowerer
from .keyword_calls.lowering import bind_keyword_call_lowerer
from .keyword_calls.model import CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE, CUMULATIVE_KEYWORD_TARGET_REASON
from .keyword_only_calls.lowering import bind_keyword_only_call_lowerer, lowered_parameter_node_ids, lowering_supports_parameter_shape
from .keyword_only_calls.model import CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE, CUMULATIVE_KEYWORD_ONLY_TARGET_REASON
from .c_output import CRenderer, validate_c_text
from .support_templates import (
    FrozenHelperRegistry,
    HelperRegistryError,
    HelperResolutionCanceled,
    assemble_translation_unit,
    default_helper_registry,
)
def _sid(prefix: str, *parts: str) -> str:
    import hashlib
    return prefix + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]
def _artifact(prior: StageArtifact, payload: dict[str, object], version: str) -> StageArtifact:
    fp = fingerprint("stage-artifact", {"kind": "generated_c", "conversion_id": prior.conversion_id, "parent": prior.artifact_fingerprint.value, "payload": payload})
    return StageArtifact("generated_c", version, prior.conversion_id, prior.artifact_fingerprint, MappingProxyType(payload), fp)
class FirstSliceLoweringStage:
    """Structured C construction for the cumulative scalar/function/container subset."""
    stage_id = "lowering.first_slice"
    input_schema = "conversion-plan/0.14.3"
    input_schemas = ("conversion-plan/0.5", "conversion-plan/0.9", "conversion-plan/0.11", "conversion-plan/0.12", "conversion-plan/0.13", "conversion-plan/0.14", "conversion-plan/0.14.1", "conversion-plan/0.14.2", "conversion-plan/0.14.3")
    output_schema = GENERATED_C_SCHEMA
    def __init__(self, helper_registry: FrozenHelperRegistry | None = None) -> None:
        self.helper_registry = helper_registry
    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
        registry = None
        try:
            registry = self.helper_registry or default_helper_registry()
            unit, helper_plan = _Lowerer(
                artifact.payload,
                services.context.cancellation,
                registry,
            ).lower()
        except (LoweringCanceled, HelperResolutionCanceled):
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
        except HelperRegistryError as exc:
            requirements = tuple(sorted(artifact.payload.get("helper_requirements", ())))
            manifest = {
                item["reference"]: item
                for item in (registry.manifest if registry is not None else ())
            }
            obligations = tuple(sorted({
                obligation
                for reference in requirements
                for obligation in manifest.get(reference, {}).get("semantic_obligations", ())
            }))
            diagnostic = Diagnostic(
                exc.code,
                Severity.INTERNAL_ERROR,
                self.stage_id,
                exc.message,
                fact_references=tuple(f"helper-requirement:{item}" for item in requirements),
                obligation_references=obligations,
                explanation="The declared helper closure could not be validated and no helper output was published.",
                remediation="Repair the project-owned helper registry or RulePlan requirement before conversion.",
            )
            return StageOutcome(StageTerminal.INTERNAL_FAILURE, diagnostics=(diagnostic,))
        except RecursionError:
            return StageOutcome(StageTerminal.REJECTED, diagnostics=(Diagnostic("PYC2006", Severity.ERROR, self.stage_id, "Structural nesting exceeds the safe lowering and validation ceiling"),))
        except UnsupportedSlice as exc:
            return StageOutcome(StageTerminal.REJECTED, diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                rule_id=exc.rule_id,
                fact_references=exc.fact_references,
                obligation_references=exc.obligation_references,
                explanation=exc.message,
                remediation="Rewrite the source to the documented supported subset or select a future rule set that explicitly supports this form.",
            ),))
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled before C IR validation"),))
        try:
            validation = validate_translation_unit(unit)
            if not validation.accepted:
                return StageOutcome(StageTerminal.INTERNAL_FAILURE, diagnostics=(Diagnostic("PYC9601", Severity.INTERNAL_ERROR, self.stage_id, "; ".join(validation.errors)),))
            if services.context.cancellation.is_canceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled before C rendering"),))
            rendered = CRenderer().render(unit)
            if services.context.cancellation.is_canceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled before generated-text validation"),))
            conformance = validate_c_text(rendered.text)
        except RecursionError:
            return StageOutcome(StageTerminal.REJECTED, diagnostics=(Diagnostic("PYC2006", Severity.ERROR, self.stage_id, "Structural nesting exceeds the safe lowering and validation ceiling"),))
        if not conformance.accepted:
            return StageOutcome(StageTerminal.INTERNAL_FAILURE, diagnostics=(Diagnostic("PYC9602", Severity.INTERNAL_ERROR, self.stage_id, conformance.message),))
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled before generated-C publication"),))
        rule_set = artifact.payload.get("rule_set_version")
        keyword_calls_enabled = supports_keyword_calls(rule_set)
        keyword_only_calls_enabled = supports_keyword_only_calls(rule_set)
        conditional_enabled = supports_conditional_regions(rule_set)
        modules_enabled = supports_modules(rule_set)
        records_enabled = supports_records(rule_set)
        numeric_enabled = supports_numeric(rule_set)
        functions_enabled = supports_functions(rule_set)
        phase11_surface = rule_set == PHASE11_RULE_SET
        generated_schema = (
            GENERATED_C_SCHEMA if keyword_only_calls_enabled
            else PHASE14C_GENERATED_C_SCHEMA if keyword_calls_enabled
            else PHASE14B_GENERATED_C_SCHEMA if conditional_enabled
            else PHASE14A_GENERATED_C_SCHEMA if numeric_enabled
            else PHASE13_GENERATED_C_SCHEMA if records_enabled
            else PHASE12_GENERATED_C_SCHEMA
            if modules_enabled
            else "generated-c/0.11" if phase11_surface
            else "generated-c/0.10" if functions_enabled or helper_plan.assets else "generated-c/0.8"
        )
        payload = dict(artifact.payload)
        payload.update(
            {
                "stage_order": tuple(artifact.payload["stage_order"]) + (self.stage_id,),
                "c_ir": serialize_translation_unit(unit),
                "c_ir_schema": unit.schema_version,
                "generated_c": rendered.text,
                "source_output_mappings": enrich_source_output_mappings(artifact.payload, rendered.mappings),
                "output_fingerprint": fingerprint("generated-output", rendered.text).to_dict(),
                "helper_registry_version": helper_plan.registry_version,
                "helper_registry_fingerprint": helper_plan.registry_fingerprint,
                "helper_manifest": list(helper_plan.manifest_dicts()),
                "helper_manifest_fingerprint": helper_plan.manifest_fingerprint,
                "schema_version": generated_schema,
            }
        )
        services.trace.record({
            "kind": "helper_resolution",
            "stage": self.stage_id,
            "requirements": [item.canonical for item in helper_plan.requirements],
            "helpers": [item.reference.canonical for item in helper_plan.manifest],
            "manifest_fingerprint": helper_plan.manifest_fingerprint,
        })
        services.trace.record({"kind": "c_ir_published", "stage": self.stage_id, "c_ir_node": unit.node_id})
        services.trace.record({"kind": "c_rendered", "stage": self.stage_id, "output_fingerprint": payload["output_fingerprint"]})
        artifact_version = "0.14.3" if keyword_only_calls_enabled else "0.14.2" if keyword_calls_enabled else "0.14.1" if conditional_enabled else "0.14" if numeric_enabled else "0.13" if records_enabled else "0.12" if modules_enabled else "0.11" if phase11_surface else "0.10" if functions_enabled or helper_plan.assets else "0.6"
        return StageOutcome(StageTerminal.COMPLETED, _artifact(artifact, payload, artifact_version))
    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        if artifact.kind != "generated_c" or artifact.schema_version not in {"0.6", "0.9", "0.10", "0.11", "0.12", "0.13", "0.14", "0.14.1", "0.14.2", "0.14.3"}:
            return False, "invalid generated-C artifact identity"
        text = artifact.payload.get("generated_c")
        if not isinstance(text, str) or not text:
            return False, "generated C is absent"
        expected = artifact.payload.get("output_fingerprint")
        if expected != fingerprint("generated-output", text).to_dict():
            return False, "generated-C output fingerprint mismatch"
        conformance = validate_c_text(text)
        return conformance.accepted, conformance.message
class UnsupportedSlice(Exception):
    def __init__(self, code: str, message: str, source_span: dict[str, object] | None = None, *, rule_id: str | None = None, fact_references: tuple[str, ...] = (), obligation_references: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source_span = source_span
        self.rule_id = rule_id
        self.fact_references = fact_references
        self.obligation_references = obligation_references
class LoweringCanceled(Exception):
    pass
class _Lowerer:
    def __init__(self, payload: Any, cancellation: Any, helper_registry: FrozenHelperRegistry) -> None:
        self.payload = payload
        self.cancellation = cancellation
        self.helper_registry = helper_registry
        module = payload["python_ir"]
        self.nodes = {node["node_id"]: node for node in module["nodes"]}
        self.document_id = module["document_id"]
        self.root = self.nodes[module["root_node_id"]]
        self.plans = {plan["source_node_id"]: plan for plan in payload["rule_plans"]}
        binding_table = self._table("binding-facts")
        self.bindings = [record["value"] for record in binding_table["records"]]
        self.binding_by_id = {binding["binding_id"]: binding for binding in self.bindings}
        self.binding_by_decl = {binding["declaration_node_id"]: binding for binding in self.bindings}
        self.binding_by_occurrence = {occurrence: binding for binding in self.bindings for occurrence in binding["occurrence_node_ids"]}
        self.names = {plan["binding_id"]: plan["generated_name"] for plan in payload["generated_name_plans"]}
        self.generated_spellings = set(self.names.values())
        self.temporary_spellings: dict[str, str] = {}
        category_table = self._table("value-category-facts")
        self.categories = {record["key"]: record["value"] for record in category_table["records"]}
        self.rule_set = payload.get("rule_set_version", "phase8-control-flow-v0.8")
        self.phase12 = supports_modules(self.rule_set)
        self.phase13 = supports_records(self.rule_set)
        self.phase14 = supports_numeric(self.rule_set)
        self.phase14b = supports_conditional_regions(self.rule_set)
        self.phase14c = supports_keyword_calls(self.rule_set)
        self.phase14d = supports_keyword_only_calls(self.rule_set)
        self.phase11 = supports_containers(self.rule_set)
        self.phase9 = supports_functions(self.rule_set)
        self.keyword_call_lowerer = bind_keyword_call_lowerer(self)
        self.keyword_only_call_lowerer = bind_keyword_only_call_lowerer(self)
        self.target_contract = payload.get("target_contract", "c11-portable-fixed-v1")
        self.signatures = self._optional_values("function-signature-facts", "function_node_id")
        self.calls = self._optional_values("call-target-facts", "call_node_id")
        self.return_paths = self._optional_values("return-path-facts", "function_node_id")
        self.local_facts = self._optional_values("local-declaration-facts", "function_node_id")
        self.container_shapes = self._optional_values("container-shape-facts", "literal_node_id")
        self.container_bindings = self._optional_values("container-binding-facts", "binding_id")
        self.container_binding_by_assignment = {
            item["assignment_node_id"]: item
            for item in self.container_bindings.values()
        }
        self.container_accesses = self._optional_values("container-access-facts", "subscript_node_id")
        self.container_iterations = self._optional_values("container-iteration-facts", "for_node_id")
        self.record_definitions = self._optional_values("record-definition-facts", "record_id")
        self.record_fields = self._optional_values("record-field-facts", "field_id")
        self.record_initializers = self._optional_values("record-initializer-facts", "initializer_id")
        self.record_instances = self._optional_values("record-instance-facts", "instance_id")
        self.record_instance_by_assignment = {item["assignment_node_id"]: item for item in self.record_instances.values()}
        self.record_bindings = self._optional_values("record-binding-facts", "binding_id")
        self.record_accesses = self._optional_values("record-access-facts", "access_node_id")
        self.module_identities = self._optional_values("module-identity-facts", "module_id")
        self.module_functions = self._optional_values("module-function-facts", "function_node_id")
        self.module_sources = self._optional_values("module-source-facts", "module_id")
        module_initialization = self._optional_values("module-initialization-facts", None)
        self.module_initialization = next(iter(module_initialization.values()), {})
        graph_values = self._optional_values("call-graph-facts", None)
        self.call_graph = next(iter(graph_values.values()), {"recursive_function_node_ids": [], "recursive_call_node_ids": []})
        self.control_depth = 0
        self.loop_depth = 0
        self.container_lowerer = ContainerCIRLowerer(
            ContainerLoweringServices(
                nodes=self.nodes,
                shapes=self.container_shapes,
                bindings=self.container_bindings,
                bindings_by_assignment=self.container_binding_by_assignment,
                accesses=self.container_accesses,
                iterations=self.container_iterations,
                source_bindings_by_id=self.binding_by_id,
                source_bindings_by_occurrence=self.binding_by_occurrence,
                generated_names=self.names,
                generated_spellings=self.generated_spellings,
                expression=self._expression,
                temporary=self._temporary,
                category_type=self._category_type,
                identifier=self._identifier,
                provenance=self._prov,
                synthetic_provenance=self._synthetic_prov,
                block_statements=self._block_statements,
                temporary_spelling=self._temporary_spelling,
                reject=self._reject,
                control_depth=lambda: self.control_depth,
            )
        )
        self.record_lowerer = RecordCIRLowerer(
            RecordLoweringServices(
                nodes=self.nodes,
                definitions=self.record_definitions,
                fields=self.record_fields,
                initializers=self.record_initializers,
                instances=self.record_instances,
                bindings=self.record_bindings,
                accesses=self.record_accesses,
                source_bindings_by_id=self.binding_by_id,
                generated_names=self.names,
                expression=self._expression,
                temporary=self._temporary,
                category_type=self._category_type,
                identifier=self._identifier,
                provenance=self._prov,
                synthetic_provenance=self._synthetic_prov,
                reject=self._reject,
                check_cancellation=self._check_cancel,
            )
        ) if self.phase13 else None
        self.numeric_lowerer = bind_numeric_lowerer(self) if self.phase14 else None
        self.conditional_region_lowerer = bind_conditional_region_lowerer(self)
    def _table(self, table_id: str) -> dict[str, Any]:
        return next(table for table in self.payload["fact_tables"] if table["table_id"] == table_id)
    def _optional_values(self, table_id: str, key_field: str | None) -> dict[str, dict[str, Any]]:
        table = next((item for item in self.payload["fact_tables"] if item["table_id"] == table_id), None)
        if not table:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for record in table["records"]:
            value = record["value"]
            result[value[key_field] if key_field else record["key"]] = value
        return result
    def _check_cancel(self) -> None:
        if self.cancellation.is_canceled:
            raise LoweringCanceled
    def _reject(self, code: str, message: str, node: dict[str, Any] | None = None) -> None:
        span = node.get("provenance", {}).get("source_span") if node else None
        plan = self.plans.get(node["node_id"]) if node else None
        facts: tuple[str, ...] = ()
        obligations: tuple[str, ...] = ()
        if plan:
            facts = tuple(plan.get("facts_used", ()))
            obligations = tuple(plan.get("semantic_obligations", ()))
        elif node and node["kind"] == "Call" and node["node_id"] in self.calls:
            facts = (f"call-target-fact:{node['node_id']}",)
        elif node and self.phase11:
            node_id = node["node_id"]
            if node_id in self.container_shapes:
                facts = (f"container-shape:{node_id}",)
                obligations = ("container-shape-and-capacity-proved",)
            elif node_id in self.container_accesses:
                facts = (f"container-access:{node_id}",)
                obligations = ("container-bounds-or-key-presence-proved",)
            elif node_id in self.container_iterations:
                facts = (f"container-iteration:{node_id}",)
                obligations = ("container-iteration-bound-and-order-proved",)
            else:
                related = tuple(
                    sorted(
                        (
                            item
                            for item in self.container_bindings.values()
                            if node_id in {
                                item.get("assignment_node_id"),
                                item.get("literal_node_id"),
                                item.get("rejection_node_id"),
                            }
                            or node_id in item.get("invalid_use_node_ids", ())
                        ),
                        key=lambda item: item["binding_id"],
                    )
                )
                if related:
                    facts = tuple(f"container-binding:{item['binding_id']}" for item in related)
                    obligations = ("container-single-binding-no-alias-or-escape",)
        raise UnsupportedSlice(code, message, span, rule_id=plan.get("rule_id") if plan else None, fact_references=facts, obligation_references=obligations)
    def lower(self):
        self._check_cancel()
        body_ids = self.root["fields"].get("body", [])
        if self.phase9:
            module_rejection = self.payload.get("module_rejection")
            if module_rejection:
                rejection_node = self.nodes.get(module_rejection[2], self.root) if len(module_rejection) > 2 else self.root
                self._reject(module_rejection[0], module_rejection[1], rejection_node)
            function_ids, invalid_top_level = ordered_function_ids(
                self.payload,
                self.root,
                self.nodes,
                imports_allowed=self.phase12,
                records_allowed=self.phase13,
            )
            if not function_ids or invalid_top_level:
                self._reject("PYC2902", "Phase 9 requires one or more top-level function definitions", self.nodes.get(invalid_top_level, self.root))
            if self.phase11:
                self._validate_phase11_facts()
            self._validate_phase9_facts(function_ids)
            record_declarations = self.record_lowerer.definitions() if self.record_lowerer else ()
            functions = tuple(self._function(self.nodes[node_id]) for node_id in function_ids)
            prototypes = tuple(self._prototype(self.nodes[node_id]) for node_id in function_ids)
            declarations = record_declarations + prototypes + functions
            schema = KEYWORD_ONLY_CALL_SCHEMA_VERSION if self.phase14d else KEYWORD_CALL_SCHEMA_VERSION if self.phase14c else CONDITIONAL_SCHEMA_VERSION if self.phase14b else NUMERIC_SCHEMA_VERSION if self.phase14 else RECORD_SCHEMA_VERSION if self.phase13 else MODULE_SCHEMA_VERSION if self.phase12 else CONTAINER_SCHEMA_VERSION if self.phase11 else SCHEMA_VERSION
        else:
            if len(body_ids) != 1 or self.nodes[body_ids[0]]["kind"] != "FunctionDef":
                self._reject("PYC2601", "The legacy Phase 6/8 rule set supports exactly one annotated top-level function", self.root)
            declarations = (self._function(self.nodes[body_ids[0]]),)
            schema = "c-ir/0.8"
        manifest: tuple[CModuleManifestEntry, ...] = ()
        module_order: tuple[str, ...] = ()
        module_dependencies: tuple[tuple[str, str], ...] = ()
        if self.phase12:
            module_order = tuple(self.module_initialization.get("module_order", ()))
            manifest = tuple(
                CModuleManifestEntry(
                    module_id,
                    self.module_identities[module_id]["document_id"],
                    self.module_identities[module_id]["logical_name"],
                    self.module_identities[module_id]["bundle_ordinal"],
                    self.module_identities[module_id]["is_primary"],
                )
                for module_id in module_order
            )
            module_dependencies = tuple(
                (item["importer_module_id"], item["target_module_id"])
                for item in self.module_initialization.get("dependency_edges", ())
            )
        builder = CTranslationUnitBuilder(
            self.target_contract,
            node_id=_sid("c-tu-", self.root["node_id"]),
            provenance=self._prov(self.root),
            schema_version=schema,
            module_manifest=manifest,
            module_order=module_order,
            module_dependencies=module_dependencies,
        )
        if self._uses_base(declarations, "int64_t"):
            builder.add_include(CInclude(_sid("c-inc-", "stdint.h"), "stdint.h", True, CProvenance("synthetic")))
        if self._uses_base(declarations, "bool") or self._contains_instance(declarations, CBooleanLiteral):
            builder.add_include(CInclude(_sid("c-inc-", "stdbool.h"), "stdbool.h", True, CProvenance("synthetic")))
        for declaration in declarations:
            builder.add_declaration(declaration)
        source_unit = builder.build()
        expected_helper_policy = self.payload.get("helper_policy_version")
        if expected_helper_policy != self.helper_registry.registry_version:
            raise HelperRegistryError(
                "PYC3305",
                "conversion plan and helper registry policy identities disagree",
            )
        helper_plan = self.helper_registry.resolve(
            self.payload.get("helper_requirements", ()),
            target_contract=self.target_contract,
            cancellation=self.cancellation,
        )
        return assemble_translation_unit(source_unit, helper_plan), helper_plan
    def _validate_phase11_facts(self) -> None:
        """Reject the earliest unsupported container boundary before generic lowering."""
        candidates: list[tuple[tuple[int, str], int, str, str, dict[str, Any]]] = []
        def add(node_id: str | None, priority: int, code: str | None, reason: str | None) -> None:
            node = self.nodes.get(node_id or "")
            if node is None:
                return
            candidates.append(
                (
                    self._source_ordinal(node["node_id"]),
                    priority,
                    code or "PYC3403",
                    reason or "Unsupported fixed-container form",
                    node,
                )
            )
        bound_literals = {
            item["literal_node_id"]
            for item in self.container_bindings.values()
        }
        for shape in self.container_shapes.values():
            if not shape["valid"]:
                add(shape["literal_node_id"], 0, shape.get("diagnostic_code"), shape.get("reason"))
            elif shape["literal_node_id"] not in bound_literals:
                add(
                    shape["literal_node_id"],
                    4,
                    "PYC3403",
                    "A supported container literal must be assigned once to a direct function-local name",
                )
        for binding in self.container_bindings.values():
            if not binding["valid"]:
                add(binding.get("rejection_node_id") or binding["assignment_node_id"], 1, binding.get("diagnostic_code"), binding.get("reason"))
        for access in self.container_accesses.values():
            if not access["supported"]:
                add(access["subscript_node_id"], 2, access.get("diagnostic_code"), access.get("reason"))
            elif not self.container_bindings.get(access.get("binding_id"), {}).get("valid"):
                add(access["subscript_node_id"], 2, "PYC3403", "Container access depends on an invalid fixed binding")
        for iteration in self.container_iterations.values():
            if not iteration["supported"]:
                add(iteration["for_node_id"], 2, iteration.get("diagnostic_code"), iteration.get("reason"))
            elif not self.container_bindings.get(iteration.get("binding_id"), {}).get("valid"):
                add(iteration["for_node_id"], 2, "PYC3403", "Container iteration depends on an invalid fixed binding")
        if candidates:
            _, _, code, reason, node = min(
                candidates,
                key=lambda item: (item[0], item[1], item[2], item[3]),
            )
            self._reject(code, reason, node)
    def _validate_phase9_facts(self, body_ids: list[str]) -> None:
        recursive = set(self.call_graph.get("recursive_function_node_ids", []))
        # Signature shape is authoritative for calls found in defaults,
        # decorators, or annotations: those forms reject as signature-policy
        # violations rather than as misleading dynamic calls.
        for function_id in body_ids:
            node = self.nodes[function_id]
            signature = self.signatures.get(function_id)
            if not signature:
                self._reject("PYC2932", "Function signature facts are missing", node)
            if not signature["eligible"]:
                reason = signature.get("rejection_reason") or "Function signature is unsupported"
                code = "PYC2911" if any(word in reason for word in ("default", "variadic", "keyword-only", "duplicate positional parameter")) else "PYC2914" if "decorated" in reason else "PYC2902" if "rebound" in reason else "PYC2932"
                self._reject(code, reason, node)
        # Preserve the root unsupported call diagnostic before a containing
        # return is rejected merely because that call's result category is
        # intentionally unknown.
        for call in sorted(self.calls.values(), key=lambda item: self._source_ordinal(item["call_node_id"])):
            cumulative_keyword_target = (call.get("diagnostic_code"), call.get("reason")) in {
                (CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE, CUMULATIVE_KEYWORD_TARGET_REASON),
                (CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE, CUMULATIVE_KEYWORD_ONLY_TARGET_REASON),
            }
            if not call["supported"] and not cumulative_keyword_target:
                self._reject(call.get("diagnostic_code") or "PYC2901", call.get("reason") or "Unsupported call", self.nodes[call["call_node_id"]])
        for function_id in body_ids:
            node = self.nodes[function_id]
            local = self.local_facts.get(function_id)
            if local:
                if local["use_before_binding_node_ids"]:
                    self._reject("PYC2940", "Local name may be used before its first binding", self.nodes[local["use_before_binding_node_ids"][0]])
                if local["loop_target_escape_node_ids"]:
                    self._reject("PYC2941", "A loop-local target is used outside its valid C lifetime", self.nodes[local["loop_target_escape_node_ids"][0]])
                if local["first_definitions_in_control_node_ids"]:
                    self._reject("PYC2870", "Bindings first defined inside a branch or loop remain unsupported", self.nodes[local["first_definitions_in_control_node_ids"][0]])
                if local.get("representation_conflict_node_ids"):
                    self._reject("PYC2943", "A binding is assigned incompatible C representations", self.nodes[local["representation_conflict_node_ids"][0]])
                if local.get("loop_target_rebind_node_ids"):
                    self._reject("PYC2944", "Reusing a parameter, local, or earlier loop target as a range target is unsupported", self.nodes[local["loop_target_rebind_node_ids"][0]])
                if local.get("loop_target_mutation_node_ids"):
                    self._reject("PYC2847", "Mutating the active range loop target would change Python iteration semantics", self.nodes[local["loop_target_mutation_node_ids"][0]])
            path = self.return_paths.get(function_id)
            if path and path["fallthrough_possible"]:
                self._reject("PYC2931", "A reachable function path falls through to implicit None", node)
            if not path or not path["compatible"]:
                self._reject("PYC2930", "Every explicit return must match the declared return representation", node)
            if function_id in recursive:
                self._reject("PYC2920", "Direct and mutual recursion are unsupported in Phase 9", node)
    def _signature(self, node: dict[str, Any]) -> dict[str, Any]:
        if node["node_id"] in self.signatures:
            return self.signatures[node["node_id"]]
        args_node = self.nodes[node["fields"]["args"]]
        arg_ids = lowered_parameter_node_ids(args_node["fields"], include_required_keyword_only=self.phase14d)
        parameters = []
        for ordinal, arg_id in enumerate(arg_ids):
            self._check_cancel()
            arg = self.nodes[arg_id]
            binding = self.binding_by_decl.get(arg_id)
            category = self._annotation_category(arg["fields"].get("annotation"))
            parameters.append({"parameter_node_id": arg_id, "binding_id": binding["binding_id"] if binding else "", "source_name": arg["fields"].get("arg", ""), "ordinal": ordinal, "category": category, "c_type": self._category_type_name(category)})
        return_category = self._annotation_category(node["fields"].get("returns"))
        binding = self.binding_by_decl.get(node["node_id"])
        return {"function_node_id": node["node_id"], "binding_id": binding["binding_id"] if binding else None, "source_name": node["fields"].get("name", ""), "parameters": parameters, "return_category": return_category, "return_c_type": self._category_type_name(return_category), "eligible": True}
    def _prototype(self, node: dict[str, Any]) -> CFunctionPrototype:
        signature = self._signature(node)
        binding = self.binding_by_decl.get(node["node_id"])
        if not binding:
            self._reject("PYC2603", "Function binding could not be resolved", node)
        parameters = tuple(self._parameter(self.nodes[item["parameter_node_id"]], prototype=True, function_node=node) for item in signature["parameters"])
        module_function = self.module_functions.get(node["node_id"], {})
        return CFunctionPrototype(
            _sid("c-prototype-", node["node_id"]),
            self._identifier(binding, node),
            self._type_from_name(signature["return_c_type"]),
            parameters,
            CStorage.NONE,
            self._synthetic_prov((node["node_id"],), node["node_id"]),
            owner_module_id=module_function.get("module_id"),
            owner_document_id=module_function.get("document_id"),
            bundle_function_ordinal=module_function.get("bundle_function_ordinal"),
        )
    def _function(self, node: dict[str, Any]) -> CFunctionDefinition:
        self._check_cancel()
        fields = node["fields"]
        if fields.get("decorator_list") or fields.get("type_params"):
            self._reject("PYC2914" if self.phase9 else "PYC2602", "Decorated or generic functions are outside the selected subset", node)
        binding = self.binding_by_decl.get(node["node_id"])
        if not binding:
            self._reject("PYC2603", "Function binding could not be resolved", node)
        args_node = self.nodes[fields["args"]]
        if not lowering_supports_parameter_shape(args_node["fields"], allow_required_keyword_only=self.phase14d):
            message = "Only annotated positional and required keyword-only parameters without defaults are supported; variadics and all defaults are unsupported" if self.phase14d else "Only positional annotated parameters without defaults are supported"
            self._reject("PYC2911" if self.phase9 else "PYC2604", message, node)
        signature = self._signature(node)
        parameters = tuple(self._parameter(self.nodes[item["parameter_node_id"]], prototype=False, function_node=node) for item in signature["parameters"])
        statements = tuple(item for statement_id in fields.get("body", []) for item in self._statements(self.nodes[statement_id]))
        module_function = self.module_functions.get(node["node_id"], {})
        return CFunctionDefinition(
            _sid("c-fn-", node["node_id"]),
            self._identifier(binding, node),
            self._type_from_name(signature["return_c_type"]),
            parameters,
            CBlock(_sid("c-block-", node["node_id"]), statements, self._prov(node)),
            CStorage.NONE,
            self._prov(node),
            owner_module_id=module_function.get("module_id"),
            owner_document_id=module_function.get("document_id"),
            bundle_function_ordinal=module_function.get("bundle_function_ordinal"),
        )
    def _parameter(self, node: dict[str, Any], *, prototype: bool, function_node: dict[str, Any]) -> CParameter:
        self._check_cancel()
        binding = self.binding_by_decl.get(node["node_id"])
        if not binding:
            self._reject("PYC2605", "Parameter binding could not be resolved", node)
        category = self._annotation_category(node["fields"].get("annotation"))
        if category == "unknown":
            self._reject("PYC2932" if self.phase9 else "PYC2632", f"Unsupported annotation for parameter {node['fields'].get('arg')}", node)
        prefix = "c-proto-param-" if prototype else "c-param-"
        provenance = self._prov(node, fallback_plan_node=function_node["node_id"])
        return CParameter(_sid(prefix, node["node_id"]), self._identifier(binding, node), self._category_type(category), provenance)
    def _block_statements(self, node_ids: list[str], *, loop: bool = False) -> tuple[Any, ...]:
        self.control_depth += 1
        if loop: self.loop_depth += 1
        try:
            return tuple(item for node_id in node_ids for item in self._statements(self.nodes[node_id]))
        finally:
            if loop: self.loop_depth -= 1
            self.control_depth -= 1
    def _statements(self, node: dict[str, Any]) -> tuple[Any, ...]:
        self._check_cancel()
        kind = node["kind"]
        fields = node["fields"]
        if kind == "Return":
            value_id = fields.get("value")
            if not value_id:
                self._reject("PYC2930" if self.phase9 else "PYC2821", "Bare return is unsupported for an annotated non-None signature", node)
            prelude, value = self._expression(self.nodes[value_id])
            return prelude + (CReturnStatement(_sid("c-ret-", node["node_id"]), value, self._prov(node)),)
        if kind == "Assign":
            if self.phase13 and node["node_id"] in self.record_instance_by_assignment:
                if self.control_depth:
                    self._reject("PYC3605", "Static-record construction must be direct in a function body", node)
                return self.record_lowerer.construction(node)
            if self.phase11 and node["node_id"] in self.container_binding_by_assignment:
                return self.container_lowerer.declaration(node)
            targets = fields.get("targets", [])
            if len(targets) != 1 or self.nodes[targets[0]]["kind"] != "Name":
                self._reject("PYC2810", "Only single-name assignment is supported", node)
            target = self.nodes[targets[0]]
            binding = self.binding_by_occurrence.get(target["node_id"])
            if not binding:
                self._reject("PYC2811", "Assignment target binding could not be resolved", target)
            prelude, value = self._expression(self.nodes[fields["value"]])
            if binding["declaration_node_id"] == target["node_id"]:
                if self.control_depth:
                    self._reject("PYC2870", "Bindings first defined inside a branch or loop are unsupported", target)
                category = self.categories.get(fields["value"], "unknown")
                declaration = CVariableDeclaration(_sid("c-var-", node["node_id"]), self._identifier(binding, target), self._category_type(category), value, CStorage.NONE, self._prov(node))
                return prelude + (declaration,)
            assignment = CAssignmentStatement(_sid("c-assign-", node["node_id"]), self._ref(binding, target, "c-target-"), value, self._prov(node))
            return prelude + (assignment,)
        if kind == "Expr":
            value_node = self.nodes[fields["value"]]
            if value_node["kind"] == "Call":
                prelude, call = self._call(value_node, materialize=False)
                return prelude + (CExpressionStatement(_sid("c-expr-stmt-", node["node_id"]), call, self._prov(node)),)
            self._reject("PYC2812", "Only understood call expressions may be used as expression statements", node)
        if kind == "If":
            prelude, condition = self._truthy(self.nodes[fields["test"]])
            body = CBlock(_sid("c-if-body-", node["node_id"]), self._block_statements(fields.get("body", [])), self._prov(node))
            other_ids = fields.get("orelse", [])
            other = CBlock(_sid("c-if-else-", node["node_id"]), self._block_statements(other_ids), self._prov(node)) if other_ids else None
            statement = CIfStatement(_sid("c-if-", node["node_id"]), condition, body, other, self._prov(node))
            return prelude + (statement,)
        if kind == "While":
            if fields.get("orelse"):
                self._reject("PYC2830", "while else is not supported", node)
            condition_prelude, condition = self._truthy(self.nodes[fields["test"]])
            source_body = self._block_statements(fields.get("body", []), loop=True)
            if condition_prelude:
                negated = CUnaryExpr(_sid("c-while-not-", node["node_id"]), CUnaryOp.LOGICAL_NOT, condition, self._synthetic_prov((fields["test"],), node["node_id"]))
                guard = CIfStatement(
                    _sid("c-while-guard-", node["node_id"]),
                    negated,
                    CBlock(_sid("c-while-guard-body-", node["node_id"]), (CBreakStatement(_sid("c-while-guard-break-", node["node_id"]), self._synthetic_prov((node["node_id"],), node["node_id"])),), self._synthetic_prov((node["node_id"],), node["node_id"])),
                    None,
                    self._synthetic_prov((node["node_id"],), node["node_id"]),
                )
                body = CBlock(_sid("c-while-body-", node["node_id"]), condition_prelude + (guard,) + source_body, self._prov(node))
                condition = CBooleanLiteral(_sid("c-while-true-", node["node_id"]), True, self._synthetic_prov((node["node_id"],), node["node_id"]))
            else:
                body = CBlock(_sid("c-while-body-", node["node_id"]), source_body, self._prov(node))
            return (CWhileStatement(_sid("c-while-", node["node_id"]), condition, body, self._prov(node)),)
        if kind == "For":
            if self.phase11 and node["node_id"] in self.container_iterations:
                return self.container_lowerer.iteration(node)
            return self._for_range(node)
        if kind == "Break":
            if not self.loop_depth: self._reject("PYC2871", "break requires an enclosing supported loop", node)
            return (CBreakStatement(_sid("c-break-", node["node_id"]), self._prov(node)),)
        if kind == "Continue":
            if not self.loop_depth: self._reject("PYC2872", "continue requires an enclosing supported loop", node)
            return (CContinueStatement(_sid("c-continue-", node["node_id"]), self._prov(node)),)
        if kind in {"FunctionDef", "AsyncFunctionDef"}:
            self._reject("PYC2915", "Nested functions and closures are unsupported in Phase 9", node)
        self._reject("PYC2812", f"Unsupported statement in the selected subset: {kind}", node)
    def _for_range(self, node: dict[str, Any]) -> tuple[Any, ...]:
        fields = node["fields"]
        if fields.get("orelse"):
            self._reject("PYC2840", "for else is not supported", node)
        target = self.nodes[fields["target"]]
        iterator = self.nodes[fields["iter"]]
        if target["kind"] != "Name" or iterator["kind"] != "Call":
            self._reject("PYC2841", "for supports only a single name over range(...) ", node)
        function = self.nodes[iterator["fields"]["func"]]
        args = iterator["fields"].get("args", [])
        function_binding = self.binding_by_occurrence.get(function["node_id"])
        recognized_builtin = bool(function_binding and function_binding["binding_kind"] == "implicit-global")
        call_fact = self.calls.get(iterator["node_id"])
        if self.phase9 and (not call_fact or call_fact.get("resolution") != "recognized-range"):
            recognized_builtin = False
        if function["kind"] != "Name" or function["fields"].get("id") != "range" or not recognized_builtin or iterator["fields"].get("keywords") or not 1 <= len(args) <= 3:
            self._reject("PYC2842", "for supports only positional range(stop), range(start, stop), or range(start, stop, step)", iterator)
        if any(self.categories.get(arg_id) != "integer-like" for arg_id in args):
            self._reject("PYC2846", "range arguments require stable integer representations", iterator)
        step_sign = 1
        if len(args) == 3:
            step_sign = self._literal_integer_sign(self.nodes[args[2]])
            if step_sign == 0:
                self._reject("PYC2843", "range step cannot be zero", self.nodes[args[2]])
            if step_sign is None:
                self._reject("PYC2845", "Phase 8/9 range step must be a nonzero integer literal", self.nodes[args[2]])
        prelude: list[Any] = []
        argument_refs: list[Any] = []
        for ordinal, argument_id in enumerate(args):
            expression_prelude, expression = self._expression(self.nodes[argument_id])
            prelude.extend(expression_prelude)
            declaration, reference = self._temporary("range", iterator, ordinal, CType("int64_t"), expression, (argument_id,))
            prelude.append(declaration)
            argument_refs.append(reference)
        zero = CIntegerLiteral(_sid("c-range-zero-", node["node_id"]), 0, "LL", self._synthetic_prov((node["node_id"],), node["node_id"]))
        one = CIntegerLiteral(_sid("c-range-one-", node["node_id"]), 1, "LL", self._synthetic_prov((node["node_id"],), node["node_id"]))
        start, stop, step = (zero, argument_refs[0], one) if len(args) == 1 else ((argument_refs[0], argument_refs[1], one) if len(args) == 2 else tuple(argument_refs))
        binding = self.binding_by_occurrence.get(target["node_id"])
        if not binding:
            self._reject("PYC2844", "Loop target binding could not be resolved", target)
        identifier = self._identifier(binding, target)
        initializer = CVariableDeclaration(_sid("c-for-init-", node["node_id"]), identifier, CType("int64_t"), start, CStorage.NONE, self._prov(target, fallback_plan_node=node["node_id"]))
        condition = CBinaryExpr(_sid("c-for-cond-", node["node_id"]), CBinaryOp.GREATER if step_sign < 0 else CBinaryOp.LESS, self._ref(binding, target, "c-for-cond-ref-"), stop, self._prov(node))
        increment = CBinaryExpr(_sid("c-for-inc-expr-", node["node_id"]), CBinaryOp.ADD, self._ref(binding, target, "c-for-inc-left-"), step, self._prov(node))
        update = CAssignmentStatement(_sid("c-for-update-", node["node_id"]), self._ref(binding, target, "c-for-update-target-"), increment, self._prov(node))
        body = CBlock(_sid("c-for-body-", node["node_id"]), self._block_statements(fields.get("body", []), loop=True), self._prov(node))
        return tuple(prelude) + (CForStatement(_sid("c-for-", node["node_id"]), initializer, condition, update, body, self._prov(node)),)
    def _expression(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        self._check_cancel()
        kind = node["kind"]
        provenance = self._prov(node)
        if kind == "Attribute" and self.phase13 and node["node_id"] in self.record_accesses:
            return self.record_lowerer.access(node)
        if kind == "Subscript" and self.phase11:
            return self.container_lowerer.access(node)
        if kind == "Name":
            binding = self.binding_by_occurrence.get(node["node_id"])
            if not binding:
                self._reject("PYC2820", f"Unresolved name: {node['fields'].get('id')}", node)
            if binding["binding_kind"] in {"function", "nested-function"}:
                self._reject("PYC2901", "First-class function values are unsupported; use a direct understood call", node)
            if binding["binding_id"] in self.container_bindings:
                self._reject("PYC3403", "A fixed container name is valid only as a proved access base or bounded iterable", node)
            if binding["binding_id"] in self.record_bindings:
                self._reject("PYC3606", "A static-record name is valid only as a proved direct field receiver", node)
            return (), self._ref(binding, node, "c-ref-")
        if kind == "Constant":
            value = node["fields"].get("value")
            if isinstance(value,(list,tuple)) and len(value)>=2 and tuple(value[:2]) == ("unsupported-python-value","float-nonfinite"):
                self._reject("PYC2822", "Non-finite floating literals are unsupported", node)
            if isinstance(value, bool): return (), CBooleanLiteral(_sid("c-bool-", node["node_id"]), value, provenance)
            if isinstance(value, int):
                if value < 0 or value > 2**63-1: self._reject("PYC2822", "Integer literal is outside the supported non-negative int64_t literal domain", node)
                return (), CIntegerLiteral(_sid("c-int-", node["node_id"]), value, "LL", provenance)
            if isinstance(value, float):
                if not math.isfinite(value): self._reject("PYC2822", "Non-finite floating literals are unsupported", node)
                return (), CFloatLiteral(_sid("c-float-", node["node_id"]), value, provenance)
            if isinstance(value, str):
                if "\x00" in value: self._reject("PYC2821", "Embedded NUL string literals are unsupported", node)
                return (), CStringLiteral(_sid("c-str-", node["node_id"]), value, "utf-8", provenance)
            self._reject("PYC2821", f"Unsupported literal: {type(value).__name__}", node)
        if kind == "UnaryOp":
            operator_kind = self.nodes[node["fields"]["op"]]["kind"]
            if operator_kind == "Not":
                truth_prelude, truth = self._truthy(self.nodes[node["fields"]["operand"]])
                return truth_prelude, CUnaryExpr(_sid("c-not-", node["node_id"]), CUnaryOp.LOGICAL_NOT, truth, provenance)
            prelude, operand = self._expression(self.nodes[node["fields"]["operand"]])
            if operator_kind == "USub": return prelude, CUnaryExpr(_sid("c-neg-", node["node_id"]), CUnaryOp.NEGATE, operand, provenance)
            if operator_kind == "UAdd": return prelude, operand
            self._reject("PYC2827", f"Unsupported unary operator: {operator_kind}", node)
        if kind == "Call":
            return self._call(node, materialize=True)
        if kind in {"List", "Tuple", "Dict", "ListComp", "DictComp", "GeneratorExp"}:
            shape = self.container_shapes.get(node["node_id"])
            self._reject(
                shape.get("diagnostic_code") if shape else "PYC3403",
                shape.get("reason") if shape else "Container literals require an approved fixed local binding",
                node,
            )
        if kind == "BoolOp":
            return self.conditional_region_lowerer.boolean(node)
        if kind == "Compare":
            return self.conditional_region_lowerer.comparison(node)
        if kind == "BinOp":
            operator_kind = self.nodes[node["fields"]["op"]]["kind"]
            if operator_kind in {"FloorDiv", "Mod"} and self.phase14:
                return self.numeric_lowerer.operation(node)
            operators = {"Add": CBinaryOp.ADD, "Sub": CBinaryOp.SUBTRACT, "Mult": CBinaryOp.MULTIPLY, "Div": CBinaryOp.DIVIDE}
            if operator_kind not in operators:
                self._reject("PYC2622", f"Unsupported arithmetic operator: {operator_kind}", node)
            category = self.categories.get(node["node_id"], "unknown")
            if category == "string-like": self._reject("PYC2823", "String concatenation remains outside the literal-only string boundary", node)
            if category not in {"integer-like", "floating-like"}: self._reject("PYC2824", "Arithmetic operands do not have a supported stable representation", node)
            if operator_kind == "Div" and category != "floating-like": self._reject("PYC2824", "Python division is supported only for floating-represented operands", node)
            left_prelude, left = self._expression(self.nodes[node["fields"]["left"]])
            right_prelude, right = self._expression(self.nodes[node["fields"]["right"]])
            return left_prelude + right_prelude, CBinaryExpr(_sid("c-bin-", node["node_id"]), operators[operator_kind], left, right, provenance)
        self._reject("PYC2825", f"Unsupported expression in the selected subset: {kind}", node)
    def _call(self, node: dict[str, Any], *, materialize: bool) -> tuple[tuple[Any, ...], Any]:
        fact = self.calls.get(node["node_id"])
        feature_keyword_only_call = bool(self.phase14d and self.keyword_only_call_lowerer.has_fact(node["node_id"]))
        feature_keyword_call = bool(
            not feature_keyword_only_call
            and self.phase14c
            and node.get("fields", {}).get("keywords")
            and self.keyword_call_lowerer.has_fact(node["node_id"])
        )
        signature = (
            self.signatures.get(fact.get("target_function_node_id"))
            if fact
            else None
        )
        if feature_keyword_only_call and signature is not None:
            prelude_values, argument_values = self.keyword_only_call_lowerer.arguments(node, signature)
            prelude = list(prelude_values)
            arguments = list(argument_values)
        elif feature_keyword_call and signature is not None:
            prelude_values, argument_values = self.keyword_call_lowerer.arguments(
                node,
                signature,
            )
            prelude = list(prelude_values)
            arguments = list(argument_values)
        else:
            prelude = []
            arguments = []
        if not fact or not fact.get("supported") or fact.get("resolution") != "understood-source-function":
            code = fact.get("diagnostic_code") if fact else "PYC2901"
            reason = fact.get("reason") if fact else "Call target is not an understood source-defined function"
            self._reject(code or "PYC2901", reason or "Unsupported call", node)
        if signature is None:
            self._reject("PYC2901", "Resolved call target signature is absent", node)
        if not (feature_keyword_only_call or feature_keyword_call):
            for ordinal, (argument_id, parameter) in enumerate(zip(fact["argument_node_ids"], signature["parameters"])):
                expression_prelude, expression = self._expression(self.nodes[argument_id])
                prelude.extend(expression_prelude)
                declaration, reference = self._temporary("arg", node, ordinal, self._type_from_name(parameter["c_type"]), expression, (argument_id, node["node_id"]))
                prelude.append(declaration)
                arguments.append(reference)
        target_binding = self.binding_by_id.get(fact["target_binding_id"])
        if not target_binding:
            self._reject("PYC2901", "Resolved call target binding is absent", node)
        callee_node = self.nodes[node["fields"]["func"]]
        callee = self._ref(target_binding, callee_node, "c-callee-", fallback_plan_node=node["node_id"])
        call = CCallExpr(_sid("c-call-", node["node_id"]), callee, tuple(arguments), self._prov(node))
        if not materialize:
            return tuple(prelude), call
        declaration, reference = self._temporary("call", node, 0, self._type_from_name(signature["return_c_type"]), call, (node["node_id"],))
        prelude.append(declaration)
        return tuple(prelude), reference
    def _truthy(self, node: dict[str, Any]) -> tuple[tuple[Any, ...], Any]:
        category = self.categories.get(node["node_id"], "unknown")
        prelude, expression = self._expression(node)
        if category == "boolean-like": return prelude, expression
        if category in {"integer-like", "floating-like"}:
            zero = CFloatLiteral(_sid("c-zero-", node["node_id"]), 0.0, self._prov(node)) if category == "floating-like" else CIntegerLiteral(_sid("c-zero-", node["node_id"]), 0, "LL", self._prov(node))
            return prelude, CBinaryExpr(_sid("c-truth-", node["node_id"]), CBinaryOp.NOT_EQUAL, expression, zero, self._prov(node))
        self._reject("PYC2850", f"No supported truthiness representation for {category}", node)
    def _temporary(self, purpose: str, owner: dict[str, Any], ordinal: int, type_ref: CType, initializer: Any, origin_ids: tuple[str, ...]) -> tuple[CVariableDeclaration, CIdentifierRef]:
        binding_id = _sid(f"bind-{purpose}-", owner["node_id"], str(ordinal), *origin_ids)
        spelling = self._temporary_spelling(purpose, binding_id)
        provenance = self._synthetic_prov(origin_ids, owner["node_id"])
        identifier = CIdentifier(binding_id, spelling, provenance)
        declaration = CVariableDeclaration(_sid(f"c-{purpose}-temp-", owner["node_id"], str(ordinal), *origin_ids), identifier, type_ref, initializer, CStorage.NONE, provenance)
        reference = CIdentifierRef(_sid(f"c-{purpose}-ref-", owner["node_id"], str(ordinal), *origin_ids), binding_id, provenance)
        return declaration, reference
    def _temporary_spelling(self, purpose: str, binding_id: str) -> str:
        existing = self.temporary_spellings.get(binding_id)
        if existing:
            return existing
        base = f"pycf_{purpose}_{binding_id[-12:]}"
        candidate = base
        suffix = 1
        while candidate in self.generated_spellings:
            suffix += 1
            candidate = f"{base}_{suffix}"
        self.generated_spellings.add(candidate)
        self.temporary_spellings[binding_id] = candidate
        return candidate
    def _literal_integer_sign(self, node: dict[str, Any]) -> int | None:
        if node["kind"] == "Constant" and isinstance(node["fields"].get("value"), int) and not isinstance(node["fields"].get("value"), bool):
            value = node["fields"]["value"]
            return 1 if value > 0 else -1 if value < 0 else 0
        if node["kind"] == "UnaryOp":
            operator = self.nodes[node["fields"]["op"]]["kind"]
            operand = self.nodes[node["fields"]["operand"]]
            if operand["kind"] == "Constant" and isinstance(operand["fields"].get("value"), int) and not isinstance(operand["fields"].get("value"), bool):
                value = operand["fields"]["value"]
                if operator == "USub": value = -value
                elif operator != "UAdd": return None
                return 1 if value > 0 else -1 if value < 0 else 0
        return None
    def _annotation_category(self, node_id: str | None) -> str:
        if not node_id or node_id not in self.nodes: return "unknown"
        node = self.nodes[node_id]
        if node["kind"] != "Name": return "unknown"
        return {"int": "integer-like", "float": "floating-like", "bool": "boolean-like", "str": "string-like"}.get(node["fields"].get("id"), "unknown")
    @staticmethod
    def _category_type_name(category: str) -> str | None:
        return {"integer-like": "int64_t", "floating-like": "double", "boolean-like": "bool", "string-like": "const char *"}.get(category)
    def _category_type(self, category: str) -> CType:
        name = self._category_type_name(category)
        if not name: self._reject("PYC2633", f"No C representation for {category}")
        return self._type_from_name(name)
    @staticmethod
    def _type_from_name(name: str | None) -> CType:
        if name == "int64_t": return CType("int64_t")
        if name == "double": return CType("double")
        if name == "bool": return CType("bool")
        if name == "const char *": return CType("char", (CQualifier.CONST,), 1)
        raise ValueError(f"unsupported planned C type: {name}")
    def _identifier(self, binding: dict[str, Any], node: dict[str, Any]) -> CIdentifier:
        spelling = self.names.get(binding["binding_id"])
        if not spelling: self._reject("PYC2942", "Generated identifier plan is missing", node)
        return CIdentifier(binding["binding_id"], spelling, self._prov(node))
    def _ref(self, binding: dict[str, Any], node: dict[str, Any], prefix: str, *, fallback_plan_node: str | None = None) -> CIdentifierRef:
        return CIdentifierRef(_sid(prefix, node["node_id"], binding["binding_id"]), binding["binding_id"], self._prov(node, fallback_plan_node=fallback_plan_node))
    def _prov(self, node: dict[str, Any], *, fallback_plan_node: str | None = None) -> CProvenance:
        provenance = node.get("provenance", {})
        span = provenance.get("source_span")
        document_id = span.get("document_id") if isinstance(span, dict) else self.document_id
        return CProvenance("direct-source-conversion", document_id, (node["node_id"],), span, self._plan_id(node["node_id"]) or self._plan_id(fallback_plan_node))
    def _synthetic_prov(self, origin_ids: tuple[str, ...], plan_node_id: str | None) -> CProvenance:
        first = self.nodes.get(origin_ids[0]) if origin_ids else None
        span = first.get("provenance", {}).get("source_span") if first else None
        document_id = span.get("document_id") if isinstance(span, dict) else self.document_id
        return CProvenance("synthetic", document_id, origin_ids, span, self._plan_id(plan_node_id))
    def _plan_id(self, node_id: str | None) -> str | None:
        plan = self.plans.get(node_id) if node_id else None
        return plan["plan_id"] if plan else None
    def _source_ordinal(self, node_id: str) -> tuple[int, str]:
        span = self.nodes[node_id].get("provenance", {}).get("source_span") or {}
        start = span.get("start", {})
        offset = start.get("offset")
        return (offset if isinstance(offset, int) else 2**63 - 1, node_id)
    @classmethod
    def _uses_base(cls, value: Any, base: str) -> bool:
        if isinstance(value, CType): return value.base == base
        if isinstance(value, tuple): return any(cls._uses_base(item, base) for item in value)
        if is_dataclass(value): return any(cls._uses_base(getattr(value, field.name), base) for field in fields(value))
        return False
    @classmethod
    def _contains_instance(cls, value: Any, expected: type) -> bool:
        if isinstance(value, expected): return True
        if isinstance(value, tuple): return any(cls._contains_instance(item, expected) for item in value)
        if is_dataclass(value): return any(cls._contains_instance(getattr(value, field.name), expected) for field in fields(value))
        return False
