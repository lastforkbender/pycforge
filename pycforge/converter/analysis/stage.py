from __future__ import annotations

from collections import deque
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from pycforge.converter.contracts.configuration import (
    PHASE9_RULE_SET,
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
from pycforge.converter.contracts.versions import (
    CONDITIONAL_FACT_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14B_CONVERSION_PLAN_SCHEMA,
    PHASE14C_CONVERSION_PLAN_SCHEMA,
    PHASE14A_CONVERSION_PLAN_SCHEMA,
    PHASE13_CONVERSION_PLAN_SCHEMA,
    PHASE12_CONVERSION_PLAN_SCHEMA,
    RECORD_FACT_SCHEMA,
)
from pycforge.converter.containers.analysis import BoundedContainerAnalyzer
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.enums import Severity, StageTerminal
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.core.stage_outcome import StageOutcome
from pycforge.converter.records import (
    RecordAnalysisCanceled,
    RecordAnalysisError,
    StaticRecordAnalyzer,
)
from pycforge.converter.numeric_semantics import (
    BoundedNumericAnalyzer,
    NumericAnalysisCanceled,
    NumericAnalysisError,
)
from pycforge.converter.conditional_regions.analysis import ConditionalRegionAnalyzer
from pycforge.converter.conditional_regions.model import (
    CONDITIONAL_REGION_KEY_DOMAIN,
    CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
    CONDITIONAL_REGION_TABLE_DEPENDENCIES,
    CONDITIONAL_REGION_TABLE_ID,
    ConditionalRegionAnalysisCanceled,
    ConditionalRegionAnalysisError,
    ConditionalRegionValidationCanceled,
)
from pycforge.converter.keyword_calls.analysis import KeywordCallAnalyzer
from pycforge.converter.keyword_calls.model import (
    CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE,
    CUMULATIVE_KEYWORD_TARGET_REASON,
    KEYWORD_CALL_KEY_DOMAIN,
    KEYWORD_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_CALL_TABLE_DEPENDENCIES,
    KEYWORD_CALL_TABLE_ID,
    KeywordCallAnalysis,
    KeywordCallAnalysisCanceled,
    KeywordCallAnalysisError,
    KeywordCallRejection,
    KeywordCallValidationCanceled,
)
from pycforge.converter.contracts.versions import KEYWORD_CALL_FACT_SCHEMA
from pycforge.converter.keyword_only_calls.analysis import KeywordOnlyCallAnalyzer
from pycforge.converter.keyword_only_calls.model import (
    CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE,
    CUMULATIVE_KEYWORD_ONLY_TARGET_REASON,
    KEYWORD_ONLY_CALL_KEY_DOMAIN,
    KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
    KEYWORD_ONLY_CALL_TABLE_ID,
    KeywordOnlyCallAnalysis,
    KeywordOnlyCallAnalysisCanceled,
    KeywordOnlyCallAnalysisError,
    KeywordOnlyCallRejection,
    KeywordOnlyCallValidationCanceled,
)
from pycforge.converter.contracts.versions import KEYWORD_ONLY_CALL_FACT_SCHEMA

from .functions import (
    CallTargetFact,
    FunctionAnalysisCanceled,
    FunctionFactsAnalyzer,
)
from .model import Completeness, FactProvenance, FactRecord, FactTable, SupportState, ValueCategory
from .planning import AnalysisCanceled, AnalysisPlanner, RulePlan, default_registry, stable_id
from .symbols import SymbolScopeAnalyzer
from .validation import validate_analysis_payload


def _artifact(prior: StageArtifact, payload: dict[str, object], version: str) -> StageArtifact:
    fp = fingerprint("stage-artifact", {"kind": "conversion_plan", "conversion_id": prior.conversion_id, "parent": prior.artifact_fingerprint.value, "payload": payload})
    return StageArtifact("conversion_plan", version, prior.conversion_id, prior.artifact_fingerprint, MappingProxyType(payload), fp)


def _extend_plan(plan: RulePlan, *, facts: tuple[str, ...] = (), obligations: tuple[str, ...] = (), explanation: tuple[str, ...] = ()) -> RulePlan:
    merged_facts = tuple(sorted(set(plan.facts_used) | set(facts)))
    merged_obligations = tuple(dict.fromkeys(plan.semantic_obligations + obligations))
    return replace(
        plan,
        facts_used=merged_facts,
        semantic_obligations=merged_obligations,
        resolved_obligations=merged_obligations,
        explanation_tokens=plan.explanation_tokens + explanation,
    )


class AnalysisPlanningStage:
    stage_id = "analysis.plan"
    input_schema = "python-ir/0.4"
    input_schemas = ("python-ir/0.3", "python-ir/0.4")
    output_schema = CONVERSION_PLAN_SCHEMA

    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
        module = artifact.payload["python_ir"]
        module_fact_tables = tuple(artifact.payload.get("module_fact_tables", ()))
        module_table_values = {
            table["table_id"]: tuple(record["value"] for record in table.get("records", ()))
            for table in module_fact_tables
        }
        module_imports = module_table_values.get("module-import-facts", ())
        module_functions = module_table_values.get("module-function-facts", ())
        module_identities = module_table_values.get("module-identity-facts", ())
        module_initialization = module_table_values.get("module-initialization-facts", ())
        module_sources = module_table_values.get("module-source-facts", ())
        imports_by_node: dict[str, list[dict[str, Any]]] = {}
        for item in module_imports:
            imports_by_node.setdefault(item.get("import_node_id", ""), []).append(item)
        imports_by_alias = {item.get("alias_node_id"): item for item in module_imports}
        functions_by_node = {item.get("function_node_id"): item for item in module_functions}
        document_plan_nodes = {item.get("document_plan_node_id"): item for item in module_identities}
        initialization_by_node = {item.get("initialization_node_id"): item for item in module_initialization}
        assembly_node_id = artifact.payload.get("module_bundle_assembly_node_id")
        request = services.context.canonical.request
        records_enabled = supports_records(request.rule_set_version)
        numeric_enabled = supports_numeric(request.rule_set_version)
        conditional_enabled = supports_conditional_regions(request.rule_set_version)
        keyword_calls_enabled = supports_keyword_calls(request.rule_set_version)
        keyword_only_calls_enabled = supports_keyword_only_calls(
            request.rule_set_version
        )
        containers_enabled = supports_containers(request.rule_set_version)
        modules_enabled = supports_modules(request.rule_set_version)
        scopes, bindings, scope_for_node = SymbolScopeAnalyzer().analyze(
            module,
            allow_records=records_enabled,
        )
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during symbol analysis"),))
        binding_dicts = tuple(binding.to_dict() for binding in bindings)
        occurrence_bindings = {occurrence: binding.binding_id for binding in bindings for occurrence in binding.occurrence_node_ids}
        binding_by_declaration = {binding.declaration_node_id: binding.binding_id for binding in bindings}
        nodes_by_id = {node["node_id"]: node for node in module["nodes"]}
        binding_categories = self._annotation_categories(module, bindings)
        module_source_by_id = {item.get("module_id"): item for item in module_sources}
        function_records = {
            node_id: {
                **item,
                "logical_name": module_source_by_id.get(item.get("module_id"), {}).get("logical_name", "<memory>"),
            }
            for node_id, item in functions_by_node.items()
        }
        module_records = {
            node_id: {
                **dict(item),
                "binding_id": binding_by_declaration.get(node_id),
                "logical_name": module_source_by_id.get(item.get("module_id"), {}).get("logical_name", "<memory>"),
            }
            for node_id, item in dict(artifact.payload.get("module_record_by_node", {})).items()
        } if records_enabled else {}
        record_class_binding_ids = {
            item["binding_id"] for item in module_records.values() if item.get("binding_id")
        }
        for binding_id in record_class_binding_ids:
            binding_categories[binding_id] = ValueCategory.CALLABLE
        annotation_binding_categories = dict(binding_categories)
        constructor_call_ids = frozenset(
            node["node_id"]
            for node in module["nodes"]
            if node["kind"] == "Call"
            and occurrence_bindings.get(node["fields"].get("func")) in record_class_binding_ids
        )
        try:
            function_analyzer = FunctionFactsAnalyzer(
                module,
                binding_dicts,
                ignored_call_node_ids=constructor_call_ids,
                allow_required_keyword_only=keyword_only_calls_enabled,
                cancellation=services.context.cancellation,
            )
            signatures = function_analyzer.signatures()
        except FunctionAnalysisCanceled:
            return StageOutcome(
                StageTerminal.CANCELED,
                diagnostics=(Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during signature analysis",
                ),),
            )
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during signature analysis"),))
        planner = AnalysisPlanner()
        preliminary_returns = function_analyzer.preliminary_call_returns(signatures)
        preliminary_returns.update({node_id: ValueCategory.RECORD for node_id in constructor_call_ids})
        try:
            categories = planner.analyze_categories(
                module,
                occurrence_bindings,
                binding_categories,
                preliminary_returns,
                services.context.cancellation,
            )
        except AnalysisCanceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
        container_shapes = ()
        container_bindings = ()
        container_accesses = ()
        container_iterations = ()
        access_categories: dict[str, ValueCategory] = {}
        iteration_categories: dict[str, ValueCategory] = {}
        if containers_enabled:
            container_shapes, container_bindings, container_accesses, container_iterations = BoundedContainerAnalyzer(
                module,
                binding_dicts,
                categories,
            ).analyze()
            access_categories = {
                item.subscript_node_id: item.result_category
                for item in container_accesses
                if item.supported
            }
            iteration_categories = {
                item.for_node_id: item.target_category
                for item in container_iterations
                if item.supported
            }
            binding_categories.clear()
            binding_categories.update(annotation_binding_categories)
            try:
                categories = planner.analyze_categories(
                    module,
                    occurrence_bindings,
                    binding_categories,
                    preliminary_returns,
                    services.context.cancellation,
                    access_categories,
                    iteration_categories,
                )
            except AnalysisCanceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
            container_shapes, container_bindings, container_accesses, container_iterations = BoundedContainerAnalyzer(
                module,
                binding_dicts,
                categories,
            ).analyze()
        record_analysis = None
        record_access_categories: dict[str, ValueCategory] = {}
        if records_enabled:
            primary_identity = next(
                (item for item in module_identities if item.get("is_primary")),
                module_identities[0] if module_identities else {},
            )
            try:
                record_analysis = StaticRecordAnalyzer(
                    module,
                    module_records=module_records,
                    function_records=function_records,
                    bindings=binding_dicts,
                    categories=categories,
                    cancellation=services.context.cancellation,
                    default_module_id=str(primary_identity.get("module_id", "__main__")),
                    default_logical_name=str(primary_identity.get("logical_name", "<memory>")),
                ).analyze()
            except RecordAnalysisCanceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during static-record analysis"),))
            except RecordAnalysisError as exc:
                return self._record_rejection(exc)
            record_access_categories = {
                item.access_node_id: item.field_category for item in record_analysis.accesses
            }
            binding_categories.clear()
            binding_categories.update(annotation_binding_categories)
            try:
                categories = planner.analyze_categories(
                    module,
                    occurrence_bindings,
                    binding_categories,
                    preliminary_returns,
                    services.context.cancellation,
                    access_categories,
                    iteration_categories,
                    record_access_categories,
                )
            except AnalysisCanceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
            if containers_enabled:
                container_shapes, container_bindings, container_accesses, container_iterations = BoundedContainerAnalyzer(
                    module,
                    binding_dicts,
                    categories,
                ).analyze()
                access_categories = {
                    item.subscript_node_id: item.result_category
                    for item in container_accesses
                    if item.supported
                }
                iteration_categories = {
                    item.for_node_id: item.target_category
                    for item in container_iterations
                    if item.supported
                }
                binding_categories.clear()
                binding_categories.update(annotation_binding_categories)
                try:
                    categories = planner.analyze_categories(
                        module,
                        occurrence_bindings,
                        binding_categories,
                        preliminary_returns,
                        services.context.cancellation,
                        access_categories,
                        iteration_categories,
                        record_access_categories,
                    )
                except AnalysisCanceled:
                    return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
            try:
                record_analysis = StaticRecordAnalyzer(
                    module,
                    module_records=module_records,
                    function_records=function_records,
                    bindings=binding_dicts,
                    categories=categories,
                    cancellation=services.context.cancellation,
                    default_module_id=str(primary_identity.get("module_id", "__main__")),
                    default_logical_name=str(primary_identity.get("logical_name", "<memory>")),
                ).analyze()
            except RecordAnalysisCanceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during static-record analysis"),))
            except RecordAnalysisError as exc:
                return self._record_rejection(exc)
        keyword_call_analysis = None
        if keyword_calls_enabled:
            try:
                keyword_call_analysis = KeywordCallAnalyzer(
                    module,
                    bindings=binding_dicts,
                    signatures=signatures,
                    categories=categories,
                    cancellation=services.context.cancellation,
                    ignored_call_node_ids=constructor_call_ids,
                ).analyze()
            except KeywordCallAnalysisCanceled:
                return StageOutcome(
                    StageTerminal.CANCELED,
                    diagnostics=(Diagnostic(
                        "PYC1901",
                        Severity.ERROR,
                        self.stage_id,
                        "Conversion canceled during keyword-call analysis",
                    ),),
                )
            except KeywordCallAnalysisError as exc:
                return self._keyword_call_rejection(exc)
        keyword_only_call_analysis = None
        if keyword_only_calls_enabled:
            try:
                keyword_only_call_analysis = KeywordOnlyCallAnalyzer(
                    module,
                    bindings=binding_dicts,
                    signatures=signatures,
                    categories=categories,
                    cancellation=services.context.cancellation,
                    ignored_call_node_ids=constructor_call_ids,
                ).analyze()
            except KeywordOnlyCallAnalysisCanceled:
                return StageOutcome(
                    StageTerminal.CANCELED,
                    diagnostics=(Diagnostic(
                        "PYC1901",
                        Severity.ERROR,
                        self.stage_id,
                        "Conversion canceled during keyword-only call analysis",
                    ),),
                )
            except KeywordOnlyCallAnalysisError as exc:
                return self._keyword_only_call_rejection(exc)
        calls = function_analyzer.calls(signatures, categories)
        if keyword_call_analysis is not None:
            keyword_facts_by_call = keyword_call_analysis.fact_by_call_node_id
            calls = tuple(
                replace(
                    call,
                    argument_node_ids=feature.source_argument_node_ids,
                    argument_categories=tuple(
                        ValueCategory(item)
                        for item in feature.source_argument_categories
                    ),
                    evaluation_order=feature.evaluation_order,
                    arguments_evaluated_once=feature.arguments_evaluated_once,
                    resolution=(
                        "understood-source-function"
                        if feature.supported
                        else "ineligible-source-function"
                    ),
                    supported=feature.supported,
                    diagnostic_code=feature.diagnostic_code,
                    reason=feature.reason,
                )
                if (feature := keyword_facts_by_call.get(call.call_node_id)) is not None
                else call
                for call in calls
            )
        if keyword_only_call_analysis is not None:
            keyword_only_facts_by_call = (
                keyword_only_call_analysis.fact_by_call_node_id
            )
            calls = tuple(
                replace(
                    call,
                    argument_node_ids=feature.source_argument_node_ids,
                    argument_categories=tuple(
                        ValueCategory(item)
                        for item in feature.source_argument_categories
                    ),
                    evaluation_order=feature.evaluation_order,
                    arguments_evaluated_once=feature.arguments_evaluated_once,
                    resolution=(
                        "understood-source-function"
                        if feature.supported
                        else "ineligible-source-function"
                    ),
                    supported=feature.supported,
                    diagnostic_code=feature.diagnostic_code,
                    reason=feature.reason,
                )
                if (
                    feature := keyword_only_facts_by_call.get(call.call_node_id)
                ) is not None
                else call
                for call in calls
            )
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during call analysis"),))
        graph = function_analyzer.call_graph(calls)
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during call-graph analysis"),))
        recursive_calls = set(graph.recursive_call_node_ids)
        if recursive_calls:
            calls = tuple(
                replace(
                    call,
                    resolution="recursive-target",
                    supported=False,
                    diagnostic_code="PYC2920",
                    reason="Direct and mutual recursion are unsupported in Phase 9",
                ) if call.call_node_id in recursive_calls else call
                for call in calls
            )
        numeric_analysis = None
        if numeric_enabled:
            try:
                numeric_analysis = BoundedNumericAnalyzer(
                    module,
                    categories=categories,
                    function_records=function_records,
                    supported_call_node_ids=frozenset(
                        item.call_node_id for item in calls if item.supported
                    ),
                    supported_container_access_node_ids=frozenset(
                        item.subscript_node_id
                        for item in container_accesses
                        if item.supported
                    ),
                    supported_record_access_node_ids=frozenset(
                        item.access_node_id
                        for item in (record_analysis.accesses if record_analysis else ())
                    ),
                    rejected_expression_diagnostics={
                        **{
                            item.call_node_id: (
                                item.diagnostic_code or "PYC2901",
                                item.reason or "Call expression is unsupported",
                            )
                            for item in calls
                            if not item.supported
                        },
                        **{
                            item.subscript_node_id: (
                                item.diagnostic_code or "PYC3404",
                                item.reason or "Container access is unsupported",
                            )
                            for item in container_accesses
                            if not item.supported
                        },
                    },
                    cancellation=services.context.cancellation,
                ).analyze()
            except NumericAnalysisCanceled:
                return StageOutcome(
                    StageTerminal.CANCELED,
                    diagnostics=(Diagnostic(
                        "PYC1901",
                        Severity.ERROR,
                        self.stage_id,
                        "Conversion canceled during bounded numeric analysis",
                    ),),
                )
            except NumericAnalysisError as exc:
                return self._numeric_rejection(exc)
        return_paths = function_analyzer.return_paths(signatures, categories)
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during return-path analysis"),))
        local_facts = function_analyzer.local_declarations(categories, signatures)
        if services.context.cancellation.is_canceled:
            return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled during local-declaration analysis"),))
        owners = function_analyzer.owner_by_node()

        conditional_analysis = None
        if conditional_enabled:
            try:
                conditional_analysis = ConditionalRegionAnalyzer(
                    module,
                    categories=categories,
                    function_records=function_records,
                    owner_by_node=owners,
                    supported_call_node_ids=frozenset(
                        item.call_node_id for item in calls if item.supported
                    ),
                    numeric_operation_node_ids=frozenset(
                        item.binop_node_id
                        for item in (numeric_analysis.operations if numeric_analysis else ())
                    ),
                    supported_container_access_node_ids=frozenset(
                        item.subscript_node_id
                        for item in container_accesses
                        if item.supported
                    ),
                    supported_record_access_node_ids=frozenset(
                        item.access_node_id
                        for item in (record_analysis.accesses if record_analysis else ())
                    ),
                    cancellation=services.context.cancellation,
                    target_contract=request.target_contract,
                ).analyze()
            except ConditionalRegionAnalysisCanceled:
                return StageOutcome(
                    StageTerminal.CANCELED,
                    diagnostics=(Diagnostic(
                        "PYC1901",
                        Severity.ERROR,
                        self.stage_id,
                        "Conversion canceled during conditional-region analysis",
                    ),),
                )
            except ConditionalRegionAnalysisError as exc:
                return self._conditional_rejection(exc)

        signature_by_node = {item.function_node_id: item for item in signatures}
        return_by_function = {item.function_node_id: item for item in return_paths}
        local_by_function = {item.function_node_id: item for item in local_facts}
        try:
            function_eligible = self._cumulative_function_eligibility(
                signature_by_node,
                return_by_function,
                local_by_function,
                calls,
                owners,
                graph,
                services.context.cancellation,
            )
        except AnalysisCanceled:
            return StageOutcome(
                StageTerminal.CANCELED,
                diagnostics=(Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during cumulative function eligibility analysis",
                ),),
            )
        if keyword_call_analysis is not None:
            keyword_call_analysis, calls = self._gate_keyword_calls_by_target(
                keyword_call_analysis,
                calls,
                function_eligible,
                nodes_by_id,
            )
        if keyword_only_call_analysis is not None:
            keyword_only_call_analysis, calls = (
                self._gate_keyword_only_calls_by_target(
                    keyword_only_call_analysis,
                    calls,
                    function_eligible,
                    nodes_by_id,
                )
            )
        call_by_node = {item.call_node_id: item for item in calls}

        if modules_enabled:
            for imported in sorted(module_imports, key=lambda item: item.get("import_item_id", "")):
                target_function_id = imported.get("target_function_node_id")
                if function_eligible.get(target_function_id, False):
                    continue
                alias_node = nodes_by_id.get(imported.get("alias_node_id"), {})
                target_node = nodes_by_id.get(target_function_id, {})
                source_span = alias_node.get("provenance", {}).get("source_span")
                target_span = target_node.get("provenance", {}).get("source_span")
                return StageOutcome(
                    StageTerminal.REJECTED,
                    diagnostics=(Diagnostic(
                        "PYC3505",
                        Severity.ERROR,
                        self.stage_id,
                        f"Imported member {imported.get('target_module_id')}.{imported.get('imported_name')} is not an eligible direct function",
                        source_span=source_span,
                        related_spans=(target_span,) if isinstance(target_span, dict) else (),
                        fact_references=(f"module-import:{imported.get('import_item_id')}", f"module-function:{target_function_id}"),
                        obligation_references=("imported-target-eligible",),
                        explanation="Imported functions must satisfy the cumulative function, call, return, local, and recursion boundaries.",
                    ),),
                )

        registry = default_registry(
            include_records=records_enabled,
            include_numeric=numeric_enabled,
            include_conditional_regions=conditional_enabled,
            include_keyword_calls=keyword_calls_enabled,
            include_keyword_only_calls=keyword_only_calls_enabled,
        )
        target = request.target_contract
        semantics = request.semantic_policy
        ruleset = request.rule_set_version
        plans: list[dict[str, Any]] = []
        support: list[dict[str, Any]] = []
        representations: list[dict[str, Any]] = []
        effects: list[dict[str, Any]] = []
        truthiness: list[dict[str, Any]] = []
        order: list[dict[str, Any]] = []
        shape_by_node = {item.literal_node_id: item for item in container_shapes}
        container_binding_by_assignment = {item.assignment_node_id: item for item in container_bindings}
        container_binding_by_id = {item.binding_id: item for item in container_bindings}
        access_by_node = {item.subscript_node_id: item for item in container_accesses}
        iteration_by_node = {item.for_node_id: item for item in container_iterations}
        record_definition_by_class = {
            item.class_node_id: item for item in (record_analysis.definitions if record_analysis else ())
        }
        record_field_by_declaration = {
            item.declaration_node_id: item for item in (record_analysis.fields if record_analysis else ())
        }
        record_initializer_by_function = {
            item.function_node_id: item for item in (record_analysis.initializers if record_analysis else ())
        }
        record_instance_by_construction = {
            item.construction_node_id: item for item in (record_analysis.instances if record_analysis else ())
        }
        record_instance_by_assignment = {
            item.assignment_node_id: item for item in (record_analysis.instances if record_analysis else ())
        }
        record_binding_by_id = {
            item.binding_id: item for item in (record_analysis.bindings if record_analysis else ())
        }
        record_access_by_node = {
            item.access_node_id: item for item in (record_analysis.accesses if record_analysis else ())
        }
        record_name_node_ids = {
            occurrence
            for binding in binding_dicts
            if binding.get("binding_id") in record_class_binding_ids
            for occurrence in binding.get("occurrence_node_ids", ())
        }
        record_name_node_ids.update(
            occurrence
            for binding in record_binding_by_id.values()
            for occurrence in binding.occurrence_node_ids
        )
        numeric_operation_by_node = {
            item.binop_node_id: item
            for item in (numeric_analysis.operations if numeric_analysis else ())
        }
        conditional_region_by_node = {
            item.region_node_id: item
            for item in (conditional_analysis.regions if conditional_analysis else ())
        }
        keyword_call_by_node = (
            keyword_call_analysis.fact_by_call_node_id
            if keyword_call_analysis is not None
            else {}
        )
        keyword_only_call_by_node = (
            keyword_only_call_analysis.fact_by_call_node_id
            if keyword_only_call_analysis is not None
            else {}
        )

        for ordinal, node in enumerate(sorted(module["nodes"], key=lambda item: item["node_id"])):
            if services.context.cancellation.is_canceled:
                return StageOutcome(StageTerminal.CANCELED, diagnostics=(Diagnostic("PYC1901", Severity.ERROR, self.stage_id, "Conversion canceled"),))
            node_id = node["node_id"]
            decision_key = stable_id("decision-", node_id, scope_for_node.get(node_id, ""), target, semantics, ruleset)
            category = categories[node_id]
            selectable_node = dict(node)
            if node["kind"] == "BinOp":
                op_node = nodes_by_id.get(node["fields"].get("op"))
                selectable_node["op_kind"] = op_node["kind"] if op_node else None
            if node["kind"] == "Call":
                selectable_node["call_target_kind"] = call_by_node.get(node_id).resolution if node_id in call_by_node and call_by_node[node_id].supported else None
            if node["kind"] == "FunctionDef":
                selectable_node["function_eligible"] = function_eligible.get(node_id, False)
            if node["kind"] == "Return":
                owner = owners.get(node_id)
                expected = signature_by_node.get(owner).return_category if owner in signature_by_node else ValueCategory.UNKNOWN
                selectable_node["return_eligible"] = category is expected and expected not in {ValueCategory.UNKNOWN, ValueCategory.CONTRADICTORY}
            if modules_enabled:
                if node_id in document_plan_nodes:
                    selectable_node["module_document_supported"] = True
                if node_id in imports_by_node:
                    selectable_node["module_import_supported"] = all(item.get("supported") for item in imports_by_node[node_id])
                if node_id in imports_by_alias:
                    selectable_node["module_alias_supported"] = bool(imports_by_alias[node_id].get("supported"))
                if node_id in functions_by_node:
                    selectable_node["module_function_supported"] = True
                if node_id in initialization_by_node:
                    selectable_node["module_initialization_supported"] = True
                if node_id == assembly_node_id:
                    selectable_node["module_bundle_assembly_supported"] = True
                if node["kind"] == "Call" and node_id in call_by_node:
                    call = call_by_node[node_id]
                    caller = functions_by_node.get(owners.get(node_id))
                    callee = functions_by_node.get(call.target_function_node_id)
                    selectable_node["cross_module_call_supported"] = bool(
                        call.supported and caller and callee and caller.get("module_id") != callee.get("module_id")
                    )
            if containers_enabled:
                if node_id in shape_by_node:
                    selectable_node["container_shape_supported"] = shape_by_node[node_id].valid
                if node_id in access_by_node:
                    selectable_node["container_access_supported"] = access_by_node[node_id].supported
                if node_id in iteration_by_node:
                    selectable_node["container_iteration_supported"] = iteration_by_node[node_id].supported
                if node_id in container_binding_by_assignment:
                    selectable_node["container_binding_supported"] = container_binding_by_assignment[node_id].valid
                if node["kind"] == "Name":
                    binding_id = occurrence_bindings.get(node_id)
                    container_binding = container_binding_by_id.get(binding_id)
                    selectable_node["container_name_supported"] = bool(
                        container_binding
                        and container_binding.valid
                        and node_id in container_binding.allowed_use_node_ids
                    )
            if records_enabled:
                if node_id in record_definition_by_class:
                    selectable_node["record_class_supported"] = True
                if node_id in record_field_by_declaration:
                    selectable_node["record_field_supported"] = True
                if node_id in record_initializer_by_function:
                    selectable_node["record_initializer_supported"] = True
                if node_id in record_instance_by_construction:
                    selectable_node["record_construction_supported"] = True
                if node_id in record_instance_by_assignment:
                    selectable_node["record_binding_supported"] = True
                if node_id in record_name_node_ids:
                    selectable_node["record_name_supported"] = True
                if node_id in record_access_by_node:
                    selectable_node["record_access_supported"] = True
            if numeric_enabled and node_id in numeric_operation_by_node:
                selectable_node["numeric_operation_supported"] = True
            if conditional_enabled and node_id in conditional_region_by_node:
                region = conditional_region_by_node[node_id]
                selectable_node[
                    "conditional_boolean_region_supported"
                    if region.region_kind.value == "boolean-short-circuit"
                    else "conditional_comparison_region_supported"
                ] = True
            if keyword_calls_enabled and node_id in keyword_call_by_node:
                selectable_node["keyword_call_binding_supported"] = bool(
                    keyword_call_by_node[node_id].supported
                    and call_by_node.get(node_id)
                    and call_by_node[node_id].supported
                )
            if keyword_only_calls_enabled and node_id in keyword_only_call_by_node:
                selectable_node["keyword_only_call_binding_supported"] = bool(
                    keyword_only_call_by_node[node_id].supported
                    and call_by_node.get(node_id)
                    and call_by_node[node_id].supported
                )

            plan = registry.select(selectable_node, categories, decision_key)
            if plan:
                plan = self._phase9_plan(plan, node, signature_by_node, call_by_node, owners, return_by_function, local_by_function)
                if containers_enabled:
                    plan = self._phase11_plan(
                        plan,
                        node,
                        shape_by_node,
                        container_binding_by_assignment,
                        access_by_node,
                        iteration_by_node,
                    )
                if modules_enabled:
                    plan = self._phase12_plan(
                        plan,
                        node,
                        imports_by_node,
                        imports_by_alias,
                        functions_by_node,
                        document_plan_nodes,
                        initialization_by_node,
                        call_by_node,
                        owners,
                        assembly_node_id,
                    )
                if records_enabled:
                    plan = self._phase13_plan(
                        plan,
                        node,
                        record_definition_by_class,
                        record_field_by_declaration,
                        record_initializer_by_function,
                        record_instance_by_construction,
                        record_instance_by_assignment,
                        record_binding_by_id,
                        record_access_by_node,
                        occurrence_bindings,
                    )
                if numeric_enabled:
                    plan = self._phase14_plan(
                        plan,
                        node,
                        numeric_operation_by_node,
                    )
                if conditional_enabled:
                    plan = self._phase14b_plan(
                        plan,
                        node,
                        conditional_region_by_node,
                    )
                if keyword_calls_enabled:
                    plan = self._phase14c_plan(
                        plan,
                        node,
                        keyword_call_by_node,
                    )
                if keyword_only_calls_enabled:
                    plan = self._phase14d_plan(
                        plan,
                        node,
                        keyword_only_call_by_node,
                        signature_by_node,
                        nodes_by_id,
                    )
            state = plan.support_state if plan else SupportState.UNSUPPORTED
            cause = self._unsupported_cause(node, signature_by_node, call_by_node, owners, return_by_function, local_by_function)
            if not plan and containers_enabled:
                if node_id in shape_by_node:
                    cause = shape_by_node[node_id].reason or "Container literal lacks an approved fixed representation"
                elif node_id in access_by_node:
                    cause = access_by_node[node_id].reason or "Container access is not statically proved"
                elif node_id in iteration_by_node:
                    cause = iteration_by_node[node_id].reason or "Container iteration is not bounded"
                elif node_id in container_binding_by_assignment:
                    cause = container_binding_by_assignment[node_id].reason or "Container binding is invalid"
                elif node["kind"] == "Name":
                    binding_id = occurrence_bindings.get(node_id)
                    container_binding = container_binding_by_id.get(binding_id)
                    if container_binding and not container_binding.valid:
                        cause = container_binding.reason
            support.append({"decision_key": decision_key, "node_id": node_id, "state": state.value, "rule_plan_id": plan.plan_id if plan else None, "cause": None if plan else cause})
            if plan:
                plan_dict = plan.to_dict()
                plans.append(plan_dict)
                services.trace.record({"kind": "rule_plan", "stage": self.stage_id, "plan": plan_dict})
            representations.append(planner.representation(decision_key, category).to_dict())
            effects.append({"node_id": node_id, "effects": [effect.value for effect in planner.effects(node)]})
            truthiness.append({"node_id": node_id, "category": category.value, "strategy": self._truthiness_strategy(category)})
            order.append({"node_id": node_id, "ordinal": ordinal, "child_order": list(function_analyzer.index.child_ids(node))})

        fact_tables: list[FactTable] = [
            FactTable("fact-table/0.5", "scope-facts", self.stage_id, "scope-id", Completeness.COMPLETE, (artifact.artifact_fingerprint.value,), tuple(FactRecord(item.scope_id, item, FactProvenance((item.owner_node_id,), ("lexical-structure",))) for item in scopes)),
            FactTable("fact-table/0.5", "binding-facts", self.stage_id, "binding-id", Completeness.COMPLETE, (artifact.artifact_fingerprint.value,), tuple(FactRecord(item.binding_id, item, FactProvenance((item.declaration_node_id,) + item.occurrence_node_ids, ("lexical-binding",))) for item in bindings)),
            FactTable("fact-table/0.5", "value-category-facts", self.stage_id, "python-node-id", Completeness.COMPLETE, ("binding-facts",), tuple(FactRecord(key, value, FactProvenance((key,), ("literal-annotation-call-or-constraint",))) for key, value in sorted(categories.items()))),
        ]
        functions_enabled = supports_functions(ruleset)
        if functions_enabled:
            fact_tables.extend(
                (
                    FactTable("fact-table/0.9", "function-signature-facts", self.stage_id, "function-node-id", Completeness.COMPLETE, ("binding-facts", "value-category-facts"), tuple(FactRecord(item.function_node_id, item, FactProvenance(tuple(filter(None, (item.function_node_id, item.return_annotation_node_id))) + tuple(parameter.parameter_node_id for parameter in item.parameters), ("exact-built-in-annotations", "phase9-signature-policy"))) for item in signatures)),
                    FactTable("fact-table/0.9", "call-target-facts", self.stage_id, "call-node-id", Completeness.COMPLETE, ("function-signature-facts", "binding-facts", "value-category-facts"), tuple(FactRecord(item.call_node_id, item, FactProvenance((item.call_node_id,) + item.argument_node_ids, ("deterministic-target-resolution", "positional-source-order"))) for item in calls)),
                    FactTable("fact-table/0.9", "return-path-facts", self.stage_id, "function-node-id", Completeness.COMPLETE, ("function-signature-facts", "value-category-facts"), tuple(FactRecord(item.function_node_id, item, FactProvenance((item.function_node_id,) + item.return_node_ids, ("reachable-return-analysis", "implicit-none-policy"))) for item in return_paths)),
                    FactTable("fact-table/0.9", "local-declaration-facts", self.stage_id, "function-node-id", Completeness.COMPLETE, ("binding-facts", "evaluation-order-facts"), tuple(FactRecord(item.function_node_id, item, FactProvenance((item.function_node_id,), ("definite-binding-analysis", "loop-target-lifetime"))) for item in local_facts)),
                    FactTable("fact-table/0.9", "call-graph-facts", self.stage_id, "module", Completeness.COMPLETE, ("call-target-facts",), (FactRecord("module-call-graph", graph, FactProvenance((module["root_node_id"],), ("direct-and-mutual-recursion-policy",))),)),
                )
            )
        if containers_enabled:
            fact_tables.extend(
                (
                    FactTable(CONTAINER_FACT_SCHEMA, "container-shape-facts", self.stage_id, "python-container-literal-node-id", Completeness.COMPLETE, ("value-category-facts",), tuple(FactRecord(item.literal_node_id, item, FactProvenance((item.literal_node_id,) + item.element_node_ids + item.key_node_ids + item.value_node_ids, ("fixed-capacity", "homogeneous-representation", "approved-container-profile"))) for item in container_shapes)),
                    FactTable(CONTAINER_FACT_SCHEMA, "container-binding-facts", self.stage_id, "binding-id", Completeness.COMPLETE, ("binding-facts", "container-shape-facts"), tuple(FactRecord(item.binding_id, item, FactProvenance((item.assignment_node_id, item.target_node_id, item.literal_node_id) + item.allowed_use_node_ids + item.invalid_use_node_ids, ("single-local-binding", "no-alias-or-escape"))) for item in container_bindings)),
                    FactTable(CONTAINER_FACT_SCHEMA, "container-access-facts", self.stage_id, "subscript-node-id", Completeness.COMPLETE, ("container-binding-facts",), tuple(FactRecord(item.subscript_node_id, item, FactProvenance(tuple(filter(None, (item.subscript_node_id, item.slice_node_id))), ("static-index-or-key-proof", "fixed-capacity-or-presence-proof"))) for item in container_accesses)),
                    FactTable(CONTAINER_FACT_SCHEMA, "container-iteration-facts", self.stage_id, "for-node-id", Completeness.COMPLETE, ("container-binding-facts",), tuple(FactRecord(item.for_node_id, item, FactProvenance(tuple(filter(None, (item.for_node_id, item.target_node_id))), ("fixed-bound", "source-insertion-order"))) for item in container_iterations)),
                )
            )
        if records_enabled:
            fact_tables.extend(self._record_fact_tables(record_analysis))
        if numeric_enabled:
            fact_tables.append(self._numeric_fact_table(numeric_analysis))
        if conditional_enabled:
            fact_tables.append(self._conditional_fact_table(conditional_analysis))
        if keyword_calls_enabled:
            fact_tables.append(self._keyword_call_fact_table(keyword_call_analysis))
        if keyword_only_calls_enabled:
            fact_tables.append(
                self._keyword_only_call_fact_table(keyword_only_call_analysis)
            )
        if modules_enabled:
            fact_tables.extend(module_fact_tables)

        plan_schema = (
            CONVERSION_PLAN_SCHEMA
            if keyword_only_calls_enabled
            else PHASE14C_CONVERSION_PLAN_SCHEMA
            if keyword_calls_enabled
            else PHASE14B_CONVERSION_PLAN_SCHEMA
            if conditional_enabled
            else PHASE14A_CONVERSION_PLAN_SCHEMA
            if numeric_enabled
            else PHASE13_CONVERSION_PLAN_SCHEMA
            if records_enabled
            else PHASE12_CONVERSION_PLAN_SCHEMA
            if modules_enabled
            else "conversion-plan/0.11"
            if containers_enabled
            else "conversion-plan/0.9"
            if functions_enabled
            else "conversion-plan/0.5"
        )
        artifact_version = "0.14.3" if keyword_only_calls_enabled else "0.14.2" if keyword_calls_enabled else "0.14.1" if conditional_enabled else "0.14" if numeric_enabled else "0.13" if records_enabled else "0.12" if modules_enabled else "0.11" if containers_enabled else "0.9" if functions_enabled else "0.5"
        helper_requirements = sorted(
            {
                requirement
                for plan in plans
                for requirement in plan.get("helper_requirements", ())
            }
        )
        generated_name_inputs = tuple(
            {
                **binding,
                "module_generated_name": bool(
                    functions_by_node.get(binding.get("declaration_node_id"), {}).get("module_generated_name")
                    or module_records.get(binding.get("declaration_node_id"), {}).get("module_generated_name")
                ),
            }
            for binding in binding_dicts
        ) + tuple(
            {
                "binding_id": field.field_id,
                "source_name": field.source_name,
                "binding_kind": "record-layout-field",
                "declaration_node_id": field.declaration_node_id,
                "occurrence_node_ids": (),
            }
            for field in (record_analysis.fields if record_analysis else ())
        )
        payload = {
            "stage_order": tuple(artifact.payload["stage_order"]) + (self.stage_id,),
            "python_ir": module,
            "python_ir_fingerprint": artifact.artifact_fingerprint.value,
            "target_contract": target,
            "semantic_policy": semantics,
            "rule_set_version": ruleset,
            "renderer_version": request.renderer_version,
            "helper_policy_version": request.helper_policy_version,
            "container_policy_version": request.container_policy_version,
            "fact_tables": [table.to_dict() if hasattr(table, "to_dict") else dict(table) for table in fact_tables],
            "evaluation_order_facts": order,
            "effect_facts": effects,
            "truthiness_facts": truthiness,
            "representation_plans": representations,
            "generated_name_plans": [
                item.to_dict()
                for item in planner.generated_names(generated_name_inputs)
            ],
            "support_decisions": support,
            "rule_registry_manifest": list(registry.manifest),
            "rule_plans": plans,
            "helper_requirements": helper_requirements,
            "module_rejection": function_analyzer.module_rejection(
                allow_imports=modules_enabled,
                allow_records=records_enabled,
            ),
            "module_policy_version": request.module_policy_version,
            "schema_version": plan_schema,
        }
        if records_enabled:
            payload["record_policy_version"] = request.record_policy_version
        if numeric_enabled:
            payload["numeric_policy_version"] = request.numeric_policy_version
        if modules_enabled:
            for key in ("module_bundle", "module_resolution", "module_bundle_assembly_node_id"):
                if key in artifact.payload:
                    payload[key] = artifact.payload[key]
        if records_enabled and "module_record_by_node" in artifact.payload:
            payload["module_record_by_node"] = artifact.payload["module_record_by_node"]
        try:
            valid, message = validate_analysis_payload(
                payload,
                cancellation=services.context.cancellation,
            )
        except ConditionalRegionValidationCanceled:
            return StageOutcome(
                StageTerminal.CANCELED,
                diagnostics=(Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during conditional-region validation",
                ),),
            )
        except KeywordCallValidationCanceled:
            return StageOutcome(
                StageTerminal.CANCELED,
                diagnostics=(Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during keyword-call validation",
                ),),
            )
        except KeywordOnlyCallValidationCanceled:
            return StageOutcome(
                StageTerminal.CANCELED,
                diagnostics=(Diagnostic(
                    "PYC1901",
                    Severity.ERROR,
                    self.stage_id,
                    "Conversion canceled during keyword-only call validation",
                ),),
            )
        if not valid:
            return StageOutcome(StageTerminal.INTERNAL_FAILURE, diagnostics=(Diagnostic("PYC9501", Severity.INTERNAL_ERROR, self.stage_id, message),))
        return StageOutcome(StageTerminal.COMPLETED, _artifact(artifact, payload, artifact_version))

    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        if artifact.kind != "conversion_plan":
            return False, "invalid analysis artifact kind"
        try:
            return validate_analysis_payload(
                dict(artifact.payload),
                cancellation=services.context.cancellation,
            )
        except (
            ConditionalRegionValidationCanceled,
            KeywordCallValidationCanceled,
            KeywordOnlyCallValidationCanceled,
        ):
            # The facade checks the token immediately after validation and
            # retires the unpublished successor artifact as Canceled.
            return True, ""

    @staticmethod
    def _cumulative_function_eligibility(
        signatures: dict[str, Any],
        returns: dict[str, Any],
        locals_by_function: dict[str, Any],
        calls: tuple[CallTargetFact, ...],
        owners: dict[str, str],
        graph: Any,
        cancellation: Any,
    ) -> dict[str, bool]:
        calls_by_owner: dict[str, list[CallTargetFact]] = {}
        callers_by_target: dict[str, list[str]] = {}
        for call in calls:
            if bool(getattr(cancellation, "is_canceled", False)):
                raise AnalysisCanceled
            owner = owners.get(call.call_node_id)
            if owner is not None:
                calls_by_owner.setdefault(owner, []).append(call)
                if call.target_function_node_id in signatures:
                    callers_by_target.setdefault(
                        call.target_function_node_id,
                        [],
                    ).append(owner)
        recursive_functions = set(graph.recursive_function_node_ids)
        eligible: dict[str, bool] = {}
        for function_id, signature in signatures.items():
            if bool(getattr(cancellation, "is_canceled", False)):
                raise AnalysisCanceled
            eligible[function_id] = bool(
                signature.eligible
                and returns[function_id].compatible
                and not returns[function_id].fallthrough_possible
                and locals_by_function[function_id].valid
                and function_id not in recursive_functions
                and all(
                    call.supported
                    for call in calls_by_owner.get(function_id, ())
                )
            )
        pending = deque(
            function_id
            for function_id, supported in eligible.items()
            if not supported
        )
        while pending:
            if bool(getattr(cancellation, "is_canceled", False)):
                raise AnalysisCanceled
            target = pending.popleft()
            for caller in callers_by_target.get(target, ()):
                if eligible.get(caller, False):
                    eligible[caller] = False
                    pending.append(caller)
        return eligible

    @staticmethod
    def _gate_keyword_calls_by_target(
        analysis: KeywordCallAnalysis,
        calls: tuple[CallTargetFact, ...],
        function_eligible: dict[str, bool],
        nodes_by_id: dict[str, dict[str, Any]],
    ) -> tuple[KeywordCallAnalysis, tuple[CallTargetFact, ...]]:
        downgraded_call_ids = {
            fact.call_node_id
            for fact in analysis.facts
            if fact.supported
            and not function_eligible.get(fact.target_function_node_id, False)
        }
        if not downgraded_call_ids:
            return analysis, calls
        facts = tuple(
            replace(
                fact,
                runtime_binding_failure="compile-time-rejected",
                supported=False,
                diagnostic_code=CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE,
                reason=CUMULATIVE_KEYWORD_TARGET_REASON,
                rejection_node_id=fact.target_function_node_id,
            )
            if fact.call_node_id in downgraded_call_ids
            else fact
            for fact in analysis.facts
        )
        rejections = tuple(
            KeywordCallRejection(
                fact.call_node_id,
                fact.diagnostic_code or "PYC2910",
                fact.reason or "Unsupported keyword-call binding",
                fact.rejection_node_id or fact.call_node_id,
                nodes_by_id.get(
                    fact.rejection_node_id or fact.call_node_id,
                    {},
                ).get("provenance", {}).get("source_span"),
            )
            for fact in facts
            if not fact.supported
        )
        gated_calls = tuple(
            replace(
                call,
                resolution="ineligible-source-function",
                supported=False,
                diagnostic_code=CUMULATIVE_KEYWORD_TARGET_DIAGNOSTIC_CODE,
                reason=CUMULATIVE_KEYWORD_TARGET_REASON,
            )
            if call.call_node_id in downgraded_call_ids
            else call
            for call in calls
        )
        return KeywordCallAnalysis(facts, rejections), gated_calls

    @staticmethod
    def _gate_keyword_only_calls_by_target(
        analysis: KeywordOnlyCallAnalysis,
        calls: tuple[CallTargetFact, ...],
        function_eligible: dict[str, bool],
        nodes_by_id: dict[str, dict[str, Any]],
    ) -> tuple[KeywordOnlyCallAnalysis, tuple[CallTargetFact, ...]]:
        downgraded_call_ids = {
            fact.call_node_id
            for fact in analysis.facts
            if fact.supported
            and not function_eligible.get(fact.target_function_node_id, False)
        }
        if not downgraded_call_ids:
            return analysis, calls
        facts = tuple(
            replace(
                fact,
                runtime_binding_failure="compile-time-rejected",
                supported=False,
                diagnostic_code=CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE,
                reason=CUMULATIVE_KEYWORD_ONLY_TARGET_REASON,
                rejection_node_id=fact.target_function_node_id,
            )
            if fact.call_node_id in downgraded_call_ids
            else fact
            for fact in analysis.facts
        )
        rejections = tuple(
            KeywordOnlyCallRejection(
                fact.call_node_id,
                fact.diagnostic_code or "PYC2910",
                fact.reason or "Unsupported required keyword-only call",
                fact.rejection_node_id or fact.call_node_id,
                nodes_by_id.get(
                    fact.rejection_node_id or fact.call_node_id,
                    {},
                ).get("provenance", {}).get("source_span"),
            )
            for fact in facts
            if not fact.supported
        )
        gated_calls = tuple(
            replace(
                call,
                resolution="ineligible-source-function",
                supported=False,
                diagnostic_code=CUMULATIVE_KEYWORD_ONLY_TARGET_DIAGNOSTIC_CODE,
                reason=CUMULATIVE_KEYWORD_ONLY_TARGET_REASON,
            )
            if call.call_node_id in downgraded_call_ids
            else call
            for call in calls
        )
        return KeywordOnlyCallAnalysis(facts, rejections), gated_calls

    def _record_rejection(self, exc: RecordAnalysisError) -> StageOutcome:
        return StageOutcome(
            StageTerminal.REJECTED,
            diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                fact_references=(f"python-node:{exc.node_id}",),
                obligation_references=("phase13-static-record-profile",),
                explanation=exc.message,
                remediation="Use the documented immutable, module-local, automatic-record subset.",
                source_module_id=exc.module_id,
                source_logical_name=exc.logical_name,
            ),),
        )

    def _numeric_rejection(self, exc: NumericAnalysisError) -> StageOutcome:
        return StageOutcome(
            StageTerminal.REJECTED,
            diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                fact_references=(f"python-node:{exc.node_id}",),
                obligation_references=("phase14-proved-floor-arithmetic",),
                explanation=exc.message,
                remediation=(
                    "Use exact int operands and a direct signed int64 divisor literal "
                    "other than 0 or -1 inside an understood top-level function."
                ),
            ),),
        )

    def _keyword_call_rejection(self, exc: KeywordCallAnalysisError) -> StageOutcome:
        return StageOutcome(
            StageTerminal.REJECTED,
            diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                fact_references=(f"python-node:{exc.node_id}",),
                obligation_references=("phase14c-exact-keyword-call-profile",),
                explanation=exc.message,
                remediation=(
                    "Use only explicit positional and named arguments that bind "
                    "every required source-function parameter exactly once."
                ),
            ),),
        )

    def _keyword_only_call_rejection(
        self,
        exc: KeywordOnlyCallAnalysisError,
    ) -> StageOutcome:
        return StageOutcome(
            StageTerminal.REJECTED,
            diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                fact_references=(f"python-node:{exc.node_id}",),
                obligation_references=(
                    "phase14d-required-keyword-only-call-profile",
                ),
                explanation=exc.message,
                remediation=(
                    "Use only required, exactly annotated keyword-only "
                    "parameters supplied once by explicit keyword."
                ),
            ),),
        )

    def _conditional_rejection(
        self,
        exc: ConditionalRegionAnalysisError,
    ) -> StageOutcome:
        return StageOutcome(
            StageTerminal.REJECTED,
            diagnostics=(Diagnostic(
                exc.code,
                Severity.ERROR,
                self.stage_id,
                exc.message,
                source_span=exc.source_span,
                fact_references=(f"python-node:{exc.node_id}",),
                obligation_references=("phase14b-conditional-region-profile",),
                explanation=exc.message,
                remediation=(
                    "Keep the conditional expression inside the documented "
                    "already-supported scalar subset, or use an explicit statement."
                ),
            ),),
        )

    def _numeric_fact_table(self, analysis: Any) -> FactTable:
        operations = tuple(
            sorted(analysis.operations, key=lambda item: item.binop_node_id)
        )
        return FactTable(
            NUMERIC_FACT_SCHEMA,
            "numeric-operation-facts",
            self.stage_id,
            "binop-node-id",
            Completeness.COMPLETE,
            ("value-category-facts", "evaluation-order-facts"),
            tuple(
                FactRecord(
                    item.binop_node_id,
                    item,
                    FactProvenance(
                        (
                            item.binop_node_id,
                            item.function_node_id,
                            item.operator_node_id,
                            item.left_node_id,
                            *item.divisor_literal_node_ids,
                        ),
                        (
                            "exact-int64-categories",
                            "direct-safe-divisor-literal",
                            "left-to-right-once-staging",
                            "frozen-floor-helper-contract",
                        ),
                    ),
                )
                for item in operations
            ),
        )

    def _conditional_fact_table(self, analysis: Any) -> FactTable:
        regions = tuple(
            sorted(analysis.regions, key=lambda item: item.region_node_id)
        )
        return FactTable(
            CONDITIONAL_FACT_SCHEMA,
            CONDITIONAL_REGION_TABLE_ID,
            self.stage_id,
            CONDITIONAL_REGION_KEY_DOMAIN,
            Completeness.COMPLETE,
            CONDITIONAL_REGION_TABLE_DEPENDENCIES,
            tuple(
                FactRecord(
                    item.region_node_id,
                    item,
                    FactProvenance(
                        item.provenance_node_ids,
                        CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
                    ),
                )
                for item in regions
            ),
        )

    def _keyword_call_fact_table(self, analysis: Any) -> FactTable:
        facts = tuple(sorted(analysis.facts, key=lambda item: item.call_node_id))
        return FactTable(
            KEYWORD_CALL_FACT_SCHEMA,
            KEYWORD_CALL_TABLE_ID,
            self.stage_id,
            KEYWORD_CALL_KEY_DOMAIN,
            Completeness.COMPLETE,
            KEYWORD_CALL_TABLE_DEPENDENCIES,
            tuple(
                FactRecord(
                    item.call_node_id,
                    item,
                    FactProvenance(
                        item.provenance_node_ids,
                        KEYWORD_CALL_PROVENANCE_EVIDENCE,
                    ),
                )
                for item in facts
            ),
        )

    def _keyword_only_call_fact_table(self, analysis: Any) -> FactTable:
        facts = tuple(sorted(analysis.facts, key=lambda item: item.call_node_id))
        return FactTable(
            KEYWORD_ONLY_CALL_FACT_SCHEMA,
            KEYWORD_ONLY_CALL_TABLE_ID,
            self.stage_id,
            KEYWORD_ONLY_CALL_KEY_DOMAIN,
            Completeness.COMPLETE,
            KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
            tuple(
                FactRecord(
                    item.call_node_id,
                    item,
                    FactProvenance(
                        item.provenance_node_ids,
                        KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
                    ),
                )
                for item in facts
            ),
        )

    def _record_fact_tables(self, analysis: Any) -> tuple[FactTable, ...]:
        definitions = tuple(sorted(analysis.definitions, key=lambda item: item.record_id))
        fields = tuple(sorted(analysis.fields, key=lambda item: item.field_id))
        initializers = tuple(sorted(analysis.initializers, key=lambda item: item.initializer_id))
        instances = tuple(sorted(analysis.instances, key=lambda item: item.instance_id))
        bindings = tuple(sorted(analysis.bindings, key=lambda item: item.binding_id))
        accesses = tuple(sorted(analysis.accesses, key=lambda item: item.access_node_id))
        fields_by_record: dict[str, tuple[Any, ...]] = {}
        for definition in definitions:
            fields_by_record[definition.record_id] = tuple(
                item for item in fields if item.record_id == definition.record_id
            )
        initializer_by_id = {item.initializer_id: item for item in initializers}
        return (
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-definition-facts",
                self.stage_id,
                "record-id",
                Completeness.COMPLETE,
                ("binding-facts", "module-identity-facts"),
                tuple(
                    FactRecord(
                        item.record_id,
                        item,
                        FactProvenance(
                            (item.class_node_id,)
                            + tuple(field.declaration_node_id for field in fields_by_record[item.record_id])
                            + (initializer_by_id[item.initializer_id].function_node_id,),
                            ("closed-class-shape", "automatic-inline-record", "immutable-noalias-noescape"),
                        ),
                    )
                    for item in definitions
                ),
            ),
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-field-facts",
                self.stage_id,
                "record-field-id",
                Completeness.COMPLETE,
                ("record-definition-facts", "binding-facts"),
                tuple(
                    FactRecord(
                        item.field_id,
                        item,
                        FactProvenance(
                            (item.declaration_node_id, item.target_node_id, item.annotation_node_id),
                            ("exact-scalar-annotation", "source-field-order", "immutable-field"),
                        ),
                    )
                    for item in fields
                ),
            ),
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-initializer-facts",
                self.stage_id,
                "record-initializer-id",
                Completeness.COMPLETE,
                ("record-definition-facts", "record-field-facts"),
                tuple(
                    FactRecord(
                        item.initializer_id,
                        item,
                        FactProvenance(
                            (item.function_node_id, item.arguments_node_id, item.self_parameter_node_id)
                            + item.parameter_node_ids
                            + item.assignment_node_ids,
                            ("exact-positional-initializer", "all-fields-once", "left-to-right-field-order"),
                        ),
                    )
                    for item in initializers
                ),
            ),
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-instance-facts",
                self.stage_id,
                "record-instance-id",
                Completeness.COMPLETE,
                ("record-definition-facts", "record-initializer-facts", "value-category-facts"),
                tuple(
                    FactRecord(
                        item.instance_id,
                        item,
                        FactProvenance(
                            (item.assignment_node_id, item.target_node_id, item.construction_node_id)
                            + item.argument_node_ids,
                            ("fresh-function-local", "automatic-storage", "no-allocation-or-cleanup"),
                        ),
                    )
                    for item in instances
                ),
            ),
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-binding-facts",
                self.stage_id,
                "binding-id",
                Completeness.COMPLETE,
                ("record-instance-facts", "binding-facts"),
                tuple(
                    FactRecord(
                        item.binding_id,
                        item,
                        FactProvenance(
                            (item.declaration_node_id,)
                            + item.occurrence_node_ids
                            + item.allowed_field_access_node_ids,
                            ("single-assignment", "no-alias", "no-escape"),
                        ),
                    )
                    for item in bindings
                ),
            ),
            FactTable(
                RECORD_FACT_SCHEMA,
                "record-access-facts",
                self.stage_id,
                "attribute-node-id",
                Completeness.COMPLETE,
                ("record-binding-facts", "record-field-facts"),
                tuple(
                    FactRecord(
                        item.access_node_id,
                        item,
                        FactProvenance(
                            (item.access_node_id,),
                            ("direct-owner-read", "statically-bound-field", "immutable-after-construction"),
                        ),
                    )
                    for item in accesses
                ),
            ),
        )

    @staticmethod
    def _phase13_plan(
        plan: RulePlan,
        node: dict[str, Any],
        definitions: dict[str, Any],
        fields: dict[str, Any],
        initializers: dict[str, Any],
        constructions: dict[str, Any],
        assignments: dict[str, Any],
        bindings: dict[str, Any],
        accesses: dict[str, Any],
        occurrence_bindings: dict[str, str],
    ) -> RulePlan:
        node_id = node["node_id"]
        if node_id in definitions:
            item = definitions[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-definition:{item.record_id}", f"record-layout-fields:{len(item.field_ids)}"),
                obligations=("record-automatic-storage", "record-no-allocation-cleanup-or-null", "record-immutable-noalias-noescape"),
                explanation=("materialized-c-record", item.source_name),
            )
        if node_id in fields:
            item = fields[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-field:{item.field_id}", f"record-field-ordinal:{item.ordinal}", f"record-field-category:{item.category.value}"),
            )
        if node_id in initializers:
            item = initializers[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-initializer:{item.initializer_id}", f"record-definition:{item.record_id}"),
                obligations=("initializer-erased-after-exact-field-copy-proof",),
            )
        if node_id in constructions:
            item = constructions[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-instance:{item.instance_id}", f"record-definition:{item.record_id}"),
                obligations=("constructor-arguments-staged-left-to-right-once", "const-aggregate-initialization"),
            )
        if node_id in assignments:
            item = assignments[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-instance:{item.instance_id}", f"record-binding:{item.binding_id}"),
                obligations=("unique-lexical-owner", "record-binding-single-assignment"),
            )
        if node_id in accesses:
            item = accesses[node_id]
            return _extend_plan(
                plan,
                facts=(f"record-access:{item.access_node_id}", f"record-field:{item.field_id}", f"record-binding:{item.binding_id}"),
                obligations=("direct-member-read", "field-mutation-absent"),
            )
        binding = bindings.get(occurrence_bindings.get(node_id, ""))
        if binding is not None:
            return _extend_plan(
                plan,
                facts=(f"record-binding:{binding.binding_id}", f"record-instance:{binding.instance_id}"),
                obligations=("record-name-use-context-approved",),
            )
        if node["kind"] == "Name" and occurrence_bindings.get(node_id):
            return _extend_plan(
                plan,
                facts=(f"record-class-binding:{occurrence_bindings[node_id]}",),
                obligations=("direct-constructor-name-only",),
            )
        return plan

    @staticmethod
    def _phase14_plan(
        plan: RulePlan,
        node: dict[str, Any],
        operations: dict[str, Any],
    ) -> RulePlan:
        operation = operations.get(node["node_id"])
        if operation is None:
            return plan
        extended = _extend_plan(
            plan,
            facts=(
                f"numeric-operation:{operation.binop_node_id}",
                f"numeric-divisor:{operation.divisor_value}",
                f"numeric-helper:{operation.helper_requirement}",
                f"numeric-target:{operation.target_contract}",
            ),
            obligations=(
                "operands-materialized-left-to-right-once",
                "helper-result-materialized-once",
                "zero-and-negative-one-divisors-excluded",
            ),
            explanation=(
                operation.operator_kind.value,
                "via",
                operation.helper_requirement,
            ),
        )
        return replace(
            extended,
            support_state=SupportState.SUPPORTED_WITH_HELPER,
            helper_requirements=(operation.helper_requirement,),
        )

    @staticmethod
    def _phase14b_plan(
        plan: RulePlan,
        node: dict[str, Any],
        regions: dict[str, Any],
    ) -> RulePlan:
        region = regions.get(node["node_id"])
        if region is None:
            return plan
        return _extend_plan(
            plan,
            facts=region.rule_facts,
            explanation=region.explanation_tokens,
        )

    @staticmethod
    def _phase14c_plan(
        plan: RulePlan,
        node: dict[str, Any],
        bindings: dict[str, Any],
    ) -> RulePlan:
        binding = bindings.get(node["node_id"])
        if binding is None or not binding.supported:
            return plan
        return _extend_plan(
            plan,
            facts=binding.rule_facts,
            explanation=binding.explanation_tokens,
        )

    @staticmethod
    def _phase14d_plan(
        plan: RulePlan,
        node: dict[str, Any],
        bindings: dict[str, Any],
        signatures: dict[str, Any],
        nodes: dict[str, dict[str, Any]],
    ) -> RulePlan:
        binding = bindings.get(node["node_id"])
        if binding is not None and binding.supported:
            return _extend_plan(
                plan,
                facts=binding.rule_facts,
                explanation=binding.explanation_tokens,
            )
        signature = signatures.get(node["node_id"])
        if signature is None or not signature.eligible:
            return plan
        arguments = nodes.get(node.get("fields", {}).get("args"), {})
        fields = arguments.get("fields", {})
        keyword_only_ids = tuple(fields.get("kwonlyargs", ()))
        if (
            not keyword_only_ids
            or tuple(fields.get("kw_defaults", ()))
            != (None,) * len(keyword_only_ids)
            or fields.get("defaults")
            or fields.get("vararg")
            or fields.get("kwarg")
        ):
            return plan
        keyword_only_names = tuple(
            str(nodes.get(parameter_id, {}).get("fields", {}).get("arg", ""))
            for parameter_id in keyword_only_ids
        )
        return _extend_plan(
            plan,
            facts=(
                f"keyword-only-signature:{node['node_id']}",
                f"keyword-only-parameter-count:{len(keyword_only_ids)}",
                "keyword-only-c-interface:mode-erased-after-static-binding",
                *(
                    f"keyword-only-parameter:{ordinal}:{parameter_id}:{name}"
                    for ordinal, (parameter_id, name) in enumerate(
                        zip(keyword_only_ids, keyword_only_names)
                    )
                ),
            ),
            obligations=(
                "required-keyword-only-parameters-exact",
                "keyword-only-parameter-kinds-preserved",
                "c-interface-mode-erasure-after-static-binding",
                "defaults-and-variadics-absent",
            ),
            explanation=(
                "required-keyword-only-signature",
                str(len(keyword_only_ids)),
                "c-interface-mode-erasure",
                "after-static-binding",
            ),
        )

    @staticmethod
    def _phase9_plan(plan: RulePlan, node: dict[str, Any], signatures: dict[str, Any], calls: dict[str, CallTargetFact], owners: dict[str, str], returns: dict[str, Any], locals_by_function: dict[str, Any]) -> RulePlan:
        if node["kind"] == "FunctionDef" and node["node_id"] in signatures:
            signature = signatures[node["node_id"]]
            facts = tuple(filter(None, (f"signature:{signature.function_node_id}", f"return-annotation:{signature.return_annotation_node_id}"))) + tuple(f"parameter-annotation:{item.annotation_node_id}" for item in signature.parameters)
            return _extend_plan(plan, facts=facts, obligations=("prototype-signature-consistent", "all-reachable-returns-compatible", "implicit-none-fallthrough-rejected", "parameter-return-ownership-explicit", "local-declarations-definite", "recursion-policy-explicit"), explanation=("signature", signature.source_name, "uses", "exact-built-in-annotation-evidence"))
        if node["kind"] == "Call" and node["node_id"] in calls:
            call = calls[node["node_id"]]
            facts = (f"call-target:{call.target_binding_id}",) + tuple(f"annotation-evidence:{item}" for item in call.annotation_evidence) + tuple(f"argument-category:{item.value}" for item in call.argument_categories)
            return _extend_plan(plan, facts=facts, obligations=("call-result-representation-known", "source-output-call-mapping-required"), explanation=("resolved-target", call.target_name or "range", "argument-order", *call.evaluation_order))
        if node["kind"] == "Return":
            owner = owners.get(node["node_id"])
            if owner in returns:
                return _extend_plan(plan, facts=(f"return-path:{owner}", f"expected-category:{returns[owner].expected_category.value}"), obligations=("fallthrough-policy-checked", "return-ownership-boundary-explicit"))
        if node["kind"] == "Assign":
            owner = owners.get(node["node_id"])
            if owner in locals_by_function:
                return _extend_plan(plan, facts=(f"local-declarations:{owner}",), obligations=("use-before-binding-absent", "generated-name-collision-absent"))
        return plan

    @staticmethod
    def _phase11_plan(
        plan: RulePlan,
        node: dict[str, Any],
        shapes: dict[str, Any],
        bindings: dict[str, Any],
        accesses: dict[str, Any],
        iterations: dict[str, Any],
    ) -> RulePlan:
        node_id = node["node_id"]
        if node_id in shapes:
            shape = shapes[node_id]
            return _extend_plan(
                plan,
                facts=(
                    f"container-shape:{node_id}",
                    f"container-kind:{shape.container_kind}",
                    f"container-capacity:{shape.capacity}",
                ),
                obligations=(
                    "container-storage-automatic",
                    "container-allocation-failure-absent",
                    "container-cleanup-not-required",
                ),
                explanation=("fixed-container", shape.container_kind, "capacity", str(shape.capacity)),
            )
        if node_id in bindings:
            binding = bindings[node_id]
            return _extend_plan(
                plan,
                facts=(
                    f"container-binding:{binding.binding_id}",
                    f"container-literal:{binding.literal_node_id}",
                ),
                obligations=("container-single-assignment-proved", "container-alias-and-escape-absent"),
            )
        if node_id in accesses:
            access = accesses[node_id]
            return _extend_plan(
                plan,
                facts=(
                    f"container-access:{node_id}",
                    f"container-binding:{access.binding_id}",
                    f"container-offset:{access.resolved_offset}",
                ),
                obligations=("container-access-failure-proved-absent", "container-access-mapping-required"),
            )
        if node_id in iterations:
            iteration = iterations[node_id]
            return _extend_plan(
                plan,
                facts=(
                    f"container-iteration:{node_id}",
                    f"container-binding:{iteration.binding_id}",
                    f"container-capacity:{iteration.capacity}",
                ),
                obligations=("container-iteration-bound-fixed", "container-iteration-order-explicit"),
            )
        return plan

    @staticmethod
    def _phase12_plan(
        plan: RulePlan,
        node: dict[str, Any],
        imports_by_node: dict[str, list[dict[str, Any]]],
        imports_by_alias: dict[str, dict[str, Any]],
        functions_by_node: dict[str, dict[str, Any]],
        document_plan_nodes: dict[str, dict[str, Any]],
        initialization_by_node: dict[str, dict[str, Any]],
        calls: dict[str, CallTargetFact],
        owners: dict[str, str],
        assembly_node_id: str | None,
    ) -> RulePlan:
        node_id = node["node_id"]
        if node_id in document_plan_nodes:
            item = document_plan_nodes[node_id]
            return _extend_plan(
                plan,
                facts=(f"module:{item.get('module_id')}", f"document:{item.get('document_id')}"),
                explanation=("explicit-module-document", str(item.get("module_id"))),
            )
        if node_id in imports_by_node:
            items = imports_by_node[node_id]
            return _extend_plan(
                plan,
                facts=tuple(
                    value
                    for item in items
                    for value in (
                        f"module-import:{item.get('import_item_id')}",
                        f"target-module:{item.get('target_module_id')}",
                        f"target-function:{item.get('target_function_node_id')}",
                    )
                ),
                explanation=("sourcebundle-only-import", *(str(item.get("target_module_id")) for item in items)),
            )
        if node_id in imports_by_alias:
            item = imports_by_alias[node_id]
            return _extend_plan(
                plan,
                facts=(f"module-import:{item.get('import_item_id')}", f"local-import-binding:{item.get('local_name')}"),
            )
        if node_id in functions_by_node:
            item = functions_by_node[node_id]
            return _extend_plan(
                plan,
                facts=(f"module:{item.get('module_id')}", f"module-function:{node_id}", f"linkage:{item.get('linkage')}"),
                explanation=("module-function", str(item.get("source_name")), "generated-as", str(item.get("flattened_name"))),
            )
        if node_id in calls:
            call = calls[node_id]
            caller = functions_by_node.get(owners.get(node_id))
            callee = functions_by_node.get(call.target_function_node_id)
            if caller and callee and caller.get("module_id") != callee.get("module_id"):
                return _extend_plan(
                    plan,
                    facts=(f"caller-module:{caller.get('module_id')}", f"callee-module:{callee.get('module_id')}", f"target-function:{call.target_function_node_id}"),
                    obligations=("cross-module-call-uses-target-binding", "bundle-wide-recursion-policy-explicit"),
                    explanation=("cross-module-direct-call", str(caller.get("module_id")), "to", str(callee.get("module_id"))),
                )
        if node_id in initialization_by_node:
            item = initialization_by_node[node_id]
            return _extend_plan(
                plan,
                facts=tuple(f"module-order:{ordinal}:{module_id}" for ordinal, module_id in enumerate(item.get("module_order", ()))),
                explanation=("compile-time-module-order", *(str(value) for value in item.get("module_order", ()))),
            )
        if node_id == assembly_node_id:
            return _extend_plan(
                plan,
                facts=("translation-unit-count:1", "module-runtime-initializers:0"),
                explanation=("single-c-translation-unit",),
            )
        return plan

    @staticmethod
    def _unsupported_cause(node: dict[str, Any], signatures: dict[str, Any], calls: dict[str, CallTargetFact], owners: dict[str, str], returns: dict[str, Any], locals_by_function: dict[str, Any]) -> str | None:
        if node["kind"] == "Call" and node["node_id"] in calls:
            return calls[node["node_id"]].reason
        if node["kind"] == "FunctionDef" and node["node_id"] in signatures:
            signature = signatures[node["node_id"]]
            if not signature.eligible:
                return signature.rejection_reason
            path = returns.get(node["node_id"])
            if path and (not path.compatible or path.fallthrough_possible):
                return "Return representations are incompatible or a reachable path falls through"
            local = locals_by_function.get(node["node_id"])
            if local and not local.valid:
                return "Local declaration or lifetime policy is not satisfied"
        if node["kind"] == "Return":
            owner = owners.get(node["node_id"])
            path = returns.get(owner)
            if path and not path.compatible:
                return "Return representation is incompatible with the declared signature"
        return None

    @staticmethod
    def _annotation_categories(module: dict[str, Any], bindings: tuple[Any, ...]) -> dict[str, ValueCategory]:
        nodes = {node["node_id"]: node for node in module["nodes"]}
        by_decl = {binding.declaration_node_id: binding.binding_id for binding in bindings}
        result: dict[str, ValueCategory] = {}
        mapping = {"int": ValueCategory.INTEGER, "float": ValueCategory.FLOAT, "bool": ValueCategory.BOOLEAN, "str": ValueCategory.STRING}
        for node_id, binding_id in by_decl.items():
            node = nodes.get(node_id)
            if not node or node["kind"] != "arg":
                continue
            annotation = nodes.get(node["fields"].get("annotation"))
            if annotation and annotation["kind"] == "Name":
                result[binding_id] = mapping.get(annotation["fields"].get("id"), ValueCategory.UNKNOWN)
        return result

    @staticmethod
    def _truthiness_strategy(category: ValueCategory) -> str:
        return {
            ValueCategory.INTEGER: "nonzero",
            ValueCategory.FLOAT: "nonzero",
            ValueCategory.BOOLEAN: "identity",
            ValueCategory.STRING: "nonempty",
            ValueCategory.NONE: "always-false",
        }.get(category, "unresolved")
