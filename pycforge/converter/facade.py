from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Callable
from .contracts.configuration import (
    supports_conditional_regions,
    supports_keyword_calls,
    supports_keyword_only_calls,
    supports_numeric,
    supports_records,
)
from .contracts.versions import (
    CONVERTER_CONTRACT_VERSION,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    PHASE14_CONVERSION_SUMMARY_SCHEMA,
    PHASE14_DECISION_TRACE_SCHEMA,
    PHASE14B_CONVERSION_SUMMARY_SCHEMA,
    PHASE14B_DECISION_TRACE_SCHEMA,
    PHASE14C_CONVERSION_SUMMARY_SCHEMA,
    PHASE14C_DECISION_TRACE_SCHEMA,
    PHASE13_CONVERSION_SUMMARY_SCHEMA,
    PHASE13_DECISION_TRACE_SCHEMA,
    PHASE12_CONVERSION_SUMMARY_SCHEMA,
    PHASE12_DECISION_TRACE_SCHEMA,
)
from .core.canonicalization import canonicalize
from .core.context import ConversionContext
from .core.diagnostics import DiagnosticCollector, Diagnostic
from .core.cancellation import CancellationToken
from .core.enums import ResultStatus,StageTerminal,Severity
from .core.fingerprint import fingerprint
from .core.pipeline import Pipeline
from .core.progress import ConversionProgress
from .core.request import ConversionRequest,ObservationOptions
from .core.result import ConversionResult
from .core.stage_artifact import StageArtifact, freeze_value
from .decision_trace.recorder import DecisionTraceRecorder
from .frontend.source_document import SourceDocument
from .telemetry.sink import TelemetrySink
@dataclass(slots=True)
class _Services:
    context:ConversionContext; trace:DecisionTraceRecorder; telemetry:TelemetrySink
class PythonToCConverter:
    def __init__(self,pipeline:Pipeline|None=None)->None:self.pipeline=pipeline or Pipeline()
    def convert(self,request:ConversionRequest,*,observation:ObservationOptions|None=None,cancellation:CancellationToken|None=None,progress:Callable[[ConversionProgress],None]|None=None,inject_trace_failure:bool=False,inject_telemetry_failure:bool=False)->ConversionResult:
        progress_failed=False
        def report_progress(event:ConversionProgress)->None:
            nonlocal progress_failed
            if progress is None or progress_failed:
                return
            try:
                progress(event)
            except Exception:
                progress_failed=True
        if observation is not None and (
            not isinstance(observation, ObservationOptions)
            or observation.trace_level not in {"None", "Summary", "Decisions", "Full"}
            or not isinstance(observation.telemetry_enabled, bool)
        ):
            diagnostic=Diagnostic("PYC1012",Severity.ERROR,"request","observation must use a declared trace level and Boolean telemetry flag")
            return ConversionResult(ResultStatus.REJECTED,None,(diagnostic,),None,None,None,None,())
        if cancellation is not None and not isinstance(cancellation, CancellationToken):
            diagnostic=Diagnostic("PYC1013",Severity.ERROR,"request","cancellation must be CancellationToken")
            return ConversionResult(ResultStatus.REJECTED,None,(diagnostic,),None,None,None,None,())
        observation=observation or ObservationOptions()
        try:
            canonical,initial_diags=canonicalize(request)
        except Exception:
            diagnostic=Diagnostic("PYC1000",Severity.ERROR,"request","Request could not be canonicalized")
            return ConversionResult(ResultStatus.REJECTED,None,(diagnostic,),None,None,None,None,())
        if canonical is None:
            return ConversionResult(ResultStatus.REJECTED,None,initial_diags,None,None,None,None,())
        request=canonical.request
        source_inputs=(request.source_bundle.primary,)+request.source_bundle.companions
        document_order=tuple(SourceDocument.create(item.logical_name,item.text).document_id for item in source_inputs)
        source_metadata={document_id:(item.module_id,item.logical_name) for document_id,item in zip(document_order,source_inputs)}
        collector=DiagnosticCollector(request.resource_policy.max_diagnostics,document_order)
        token=cancellation or CancellationToken()
        trace=DecisionTraceRecorder(observation.trace_level,request.resource_policy.max_trace_events,inject_trace_failure)
        telemetry=TelemetrySink(observation.telemetry_enabled,request.resource_policy.max_telemetry_events,inject_telemetry_failure)
        services=_Services(ConversionContext(canonical,collector,token),trace,telemetry)
        artifact=StageArtifact.initial(canonical.request_fingerprint.value); last=None
        total_stages=len(self.pipeline.stages)
        report_progress(ConversionProgress("pipeline-ready",None,0,total_stages))
        def add_diagnostic(diagnostic: Diagnostic) -> None:
            span=diagnostic.source_span or {}
            document_id=span.get("document_id") if isinstance(span,dict) else None
            module_id,logical_name=source_metadata.get(document_id,(None,None))
            collector.add(replace(
                diagnostic,
                target_contract=diagnostic.target_contract or request.target_contract,
                semantic_policy=diagnostic.semantic_policy or request.semantic_policy,
                source_module_id=diagnostic.source_module_id or module_id,
                source_logical_name=diagnostic.source_logical_name or logical_name,
            ))
        try:
            for stage_ordinal,stage in enumerate(self.pipeline.stages):
                report_progress(ConversionProgress("stage-entered",stage.stage_id,stage_ordinal,total_stages))
                trace.record({"kind":"stage_enter","stage":stage.stage_id})
                telemetry.record({"kind":"stage_enter","stage":stage.stage_id})
                identity=f"{artifact.kind.replace('_','-')}/{artifact.schema_version}"
                accepted=tuple(getattr(stage,"input_schemas",(stage.input_schema,)))
                if identity not in accepted:
                    add_diagnostic(Diagnostic("PYC9004",Severity.INTERNAL_ERROR,stage.stage_id,f"Stage input contract mismatch: {identity}"))
                    return self._result(ResultStatus.INTERNAL_FAILURE,canonical,collector,artifact,last,trace,telemetry)
                outcome=stage.run(artifact,services)
                for d in outcome.diagnostics:add_diagnostic(d)
                if not outcome.completed:
                    status={StageTerminal.REJECTED:ResultStatus.REJECTED,StageTerminal.INTERNAL_FAILURE:ResultStatus.INTERNAL_FAILURE,StageTerminal.CANCELED:ResultStatus.CANCELED}[outcome.terminal]
                    return self._result(status,canonical,collector,artifact,last,trace,telemetry)
                if token.is_canceled:
                    add_diagnostic(Diagnostic("PYC1901",Severity.ERROR,stage.stage_id,"Conversion canceled before stage publication"))
                    return self._result(ResultStatus.CANCELED,canonical,collector,artifact,last,trace,telemetry)
                valid,message=stage.validate(outcome.artifact,services)
                if not valid:
                    add_diagnostic(Diagnostic("PYC9002",Severity.INTERNAL_ERROR,stage.stage_id,message))
                    return self._result(ResultStatus.INTERNAL_FAILURE,canonical,collector,artifact,last,trace,telemetry)
                if token.is_canceled:
                    add_diagnostic(Diagnostic("PYC1901",Severity.ERROR,stage.stage_id,"Conversion canceled during stage validation"))
                    return self._result(ResultStatus.CANCELED,canonical,collector,artifact,last,trace,telemetry)
                artifact=outcome.artifact; last=stage.stage_id
                trace.record({"kind":"stage_completed","stage":stage.stage_id,"artifact":artifact.artifact_fingerprint.value})
                report_progress(ConversionProgress("stage-completed",stage.stage_id,stage_ordinal+1,total_stages))
            return self._result(ResultStatus.CONVERTED,canonical,collector,artifact,last,trace,telemetry)
        except Exception:
            add_diagnostic(Diagnostic("PYC9001",Severity.INTERNAL_ERROR,"facade","Internal converter invariant failed"))
            return self._result(ResultStatus.INTERNAL_FAILURE,canonical,collector,artifact,last,trace,telemetry)
    def _result(self,status,canonical,collector,artifact,last,trace,telemetry):
        order=tuple(artifact.payload.get("stage_order",()))
        publishable={ResultStatus.CONVERTED,ResultStatus.CONVERTED_WITH_WARNINGS,ResultStatus.CONVERTED_WITH_APPROXIMATIONS}
        generated_c=artifact.payload.get("generated_c") if status in publishable else None
        output_fp=fingerprint("generated-output",generated_c) if generated_c is not None else None
        summary=freeze_value(self._conversion_summary(artifact))
        diagnostics=collector.snapshot()
        trace_snapshot=self._decision_trace_snapshot(canonical,artifact,diagnostics,output_fp,trace.snapshot())
        telemetry_snapshot=self._telemetry_snapshot(canonical,telemetry.snapshot())
        return ConversionResult(status,generated_c,diagnostics,canonical.request_fingerprint,canonical.resource_fingerprint,output_fp,last,order,freeze_value(trace_snapshot),freeze_value(telemetry_snapshot),artifact,summary)

    @staticmethod
    def _decision_trace_snapshot(canonical, artifact, diagnostics, output_fp, raw):
        request=canonical.request
        configuration={
            "python_version":request.python_version,
            "target_contract":request.target_contract,
            "semantic_policy":request.semantic_policy,
            "approximation_allowlist":list(request.approximation_allowlist),
            "rule_set_version":request.rule_set_version,
            "renderer_version":request.renderer_version,
            "helper_policy_version":request.helper_policy_version,
            "container_policy_version":request.container_policy_version,
            "module_policy_version":request.module_policy_version,
            **(
                {"record_policy_version": request.record_policy_version}
                if supports_records(request.rule_set_version)
                else {}
            ),
            **(
                {"numeric_policy_version": request.numeric_policy_version}
                if supports_numeric(request.rule_set_version)
                else {}
            ),
        }
        events=list(raw["events"])
        stage_summaries=[event for event in events if event.get("kind") in {"stage_enter","stage_completed"}]
        rule_decisions=[event["plan"] for event in events if event.get("kind")=="rule_plan"]
        trace_diagnostics=[item.to_dict() for item in diagnostics]
        if raw["truncated"]:
            trace_diagnostics.append(Diagnostic(
                "PYC8001",Severity.WARNING,"observation","Decision trace deterministically truncated at its declared event budget",
                effect_on_status=False,target_contract=request.target_contract,semantic_policy=request.semantic_policy,
            ).to_dict())
        if raw["observer_failed"]:
            trace_diagnostics.append(Diagnostic(
                "PYC8002",Severity.WARNING,"observation","Decision trace observer failed without affecting conversion",
                effect_on_status=False,target_contract=request.target_contract,semantic_policy=request.semantic_policy,
            ).to_dict())
        payload=artifact.payload
        fact_tables={item.get("table_id"):item for item in payload.get("fact_tables",())}
        initialization_records=fact_tables.get("module-initialization-facts",{}).get("records",())
        module_initialization=initialization_records[0]["value"] if initialization_records else None
        module_order={module_id:ordinal for ordinal,module_id in enumerate((module_initialization or {}).get("module_order",()))}
        module_manifest=sorted(
            (record["value"] for record in fact_tables.get("module-identity-facts",{}).get("records",())),
            key=lambda item:(module_order.get(item.get("module_id"),2**31-1),item.get("module_id","")),
        )
        module_imports=sorted(
            (record["value"] for record in fact_tables.get("module-import-facts",{}).get("records",())),
            key=lambda item:(module_order.get(item.get("importer_module_id"),2**31-1),item.get("source_ordinal",2**31-1),item.get("import_item_id","")),
        )
        record={
            "schema_version":(
                DECISION_TRACE_SCHEMA
                if supports_keyword_only_calls(request.rule_set_version)
                else PHASE14C_DECISION_TRACE_SCHEMA
                if supports_keyword_calls(request.rule_set_version)
                else PHASE14B_DECISION_TRACE_SCHEMA
                if supports_conditional_regions(request.rule_set_version)
                else PHASE14_DECISION_TRACE_SCHEMA
                if supports_numeric(request.rule_set_version)
                else PHASE13_DECISION_TRACE_SCHEMA
                if supports_records(request.rule_set_version)
                else PHASE12_DECISION_TRACE_SCHEMA
            ),
            "converter_version":CONVERTER_CONTRACT_VERSION,
            "trace_level":raw["level"],
            "input_fingerprint":canonical.request_fingerprint.value,
            "configuration_fingerprint":fingerprint("conversion-configuration",configuration).value,
            "resource_policy_fingerprint":canonical.resource_fingerprint.value,
            "stage_summaries":stage_summaries,
            "rule_decisions":rule_decisions,
            "diagnostics":trace_diagnostics,
            "output_fingerprint":None if output_fp is None else output_fp.value,
            "source_output_mappings":list(payload.get("source_output_mappings",())) if raw["level"]=="Full" else [],
            "generated_artifact":{
                "kind":artifact.kind,
                "schema_version":artifact.schema_version,
                "artifact_fingerprint":artifact.artifact_fingerprint.value,
                "parent_fingerprint":None if artifact.parent_fingerprint is None else artifact.parent_fingerprint.value,
            },
            "target_contract":request.target_contract,
            "semantic_policy":request.semantic_policy,
            "approximation_allowlist":list(request.approximation_allowlist),
            "rule_set_version":request.rule_set_version,
            "renderer_version":request.renderer_version,
            "helper_policy_version":request.helper_policy_version,
            "container_policy_version":request.container_policy_version,
            "module_policy_version":request.module_policy_version,
            **(
                {"record_policy_version": request.record_policy_version}
                if supports_records(request.rule_set_version)
                else {}
            ),
            **(
                {"numeric_policy_version": request.numeric_policy_version}
                if supports_numeric(request.rule_set_version)
                else {}
            ),
            "rule_manifest_fingerprint":fingerprint("rule-registry-manifest",list(payload.get("rule_registry_manifest",()))).value,
            "helper_registry_fingerprint":payload.get("helper_registry_fingerprint"),
            "helper_manifest":list(payload.get("helper_manifest",())),
            "helper_manifest_fingerprint":payload.get("helper_manifest_fingerprint") or fingerprint("helper-manifest",[]).value,
            "module_manifest":module_manifest,
            "module_imports":module_imports,
            "module_initialization":module_initialization,
            "completeness":"observer-failed" if raw["observer_failed"] else ("deterministically-truncated" if raw["truncated"] else "complete"),
            "events":events,
            "truncated":raw["truncated"],
            "observer_failed":raw["observer_failed"],
        }
        record["trace_fingerprint"]=fingerprint("decision-trace",record).value
        return record

    @staticmethod
    def _telemetry_snapshot(canonical, raw):
        return {
            "schema_version":"pycforge.telemetry/0.9",
            "conversion_observation_id":fingerprint("conversion-observation",canonical.request_fingerprint.value).value,
            "measurements":list(raw["events"]),
            "drop_count":raw["dropped"],
            "truncated":raw["dropped"]>0,
            "observer_failed":raw["observer_failed"],
            "events":list(raw["events"]),
            "dropped":raw["dropped"],
        }

    @staticmethod
    def _conversion_summary(artifact: StageArtifact) -> dict[str, object] | None:
        payload=artifact.payload
        tables={item.get("table_id"):item for item in payload.get("fact_tables",())}
        signature_table=tables.get("function-signature-facts")
        call_table=tables.get("call-target-facts")
        shape_table=tables.get("container-shape-facts")
        container_binding_table=tables.get("container-binding-facts")
        access_table=tables.get("container-access-facts")
        iteration_table=tables.get("container-iteration-facts")
        module_identity_table=tables.get("module-identity-facts")
        module_import_table=tables.get("module-import-facts")
        module_function_table=tables.get("module-function-facts")
        module_initialization_table=tables.get("module-initialization-facts")
        module_source_table=tables.get("module-source-facts")
        record_definition_table=tables.get("record-definition-facts")
        record_field_table=tables.get("record-field-facts")
        record_initializer_table=tables.get("record-initializer-facts")
        record_instance_table=tables.get("record-instance-facts")
        record_binding_table=tables.get("record-binding-facts")
        record_access_table=tables.get("record-access-facts")
        numeric_operation_table=tables.get("numeric-operation-facts")
        conditional_region_table=tables.get("conditional-region-facts")
        keyword_call_table=tables.get("keyword-call-binding-facts")
        keyword_only_call_table=tables.get("keyword-only-call-binding-facts")
        if not signature_table:
            return None
        names={item["binding_id"]:item["generated_name"] for item in payload.get("generated_name_plans",())}
        module_functions={record["value"].get("function_node_id"):record["value"] for record in (module_function_table or {}).get("records",())}
        module_sources={record["value"].get("module_id"):record["value"] for record in (module_source_table or {}).get("records",())}
        functions=[]
        for record in signature_table["records"]:
            value=record["value"]
            module_function=module_functions.get(value["function_node_id"],{})
            module_source=module_sources.get(module_function.get("module_id"),{})
            functions.append({
                "source_name":module_function.get("source_name",value["source_name"]),
                "flattened_source_name":value["source_name"],
                "generated_name":names.get(value.get("binding_id")),
                "function_node_id":value["function_node_id"],
                "module_id":module_function.get("module_id"),
                "document_id":module_function.get("document_id"),
                "logical_source_name":module_source.get("logical_name"),
                "linkage":module_function.get("linkage"),
                "parameters":[{
                    "source_name":item["source_name"],
                    "annotation":item["annotation_spelling"],
                    "annotation_node_id":item["annotation_node_id"],
                    "c_type":item["c_type"],
                    "passing":item["passing"],
                    "ownership":item["ownership"],
                    "lifetime":item["lifetime"],
                } for item in value["parameters"]],
                "return_annotation":value["return_annotation_spelling"],
                "return_annotation_node_id":value["return_annotation_node_id"],
                "return_c_type":value["return_c_type"],
                "return_passing":value["return_passing"],
                "return_ownership":value["return_ownership"],
                "return_lifetime":value["return_lifetime"],
                "eligible":value["eligible"],
            })
        functions.sort(key=lambda item:(module_functions.get(item["function_node_id"],{}).get("bundle_function_ordinal",2**31-1),item["function_node_id"]))
        calls=[]
        if call_table:
            for record in call_table["records"]:
                value=record["value"]
                calls.append({
                    "call_node_id":value["call_node_id"],
                    "target_name":value["target_name"],
                    "resolution":value["resolution"],
                    "argument_categories":list(value["argument_categories"]),
                    "parameter_categories":list(value["parameter_categories"]),
                    "evaluation_order":list(value["evaluation_order"]),
                    "arguments_evaluated_once":value["arguments_evaluated_once"],
                    "ownership_boundary":list(value["ownership_boundary"]),
                    "annotation_evidence":list(value["annotation_evidence"]),
                    "supported":value["supported"],
                    "target_function_node_id":value.get("target_function_node_id"),
                    "target_module_id":module_functions.get(value.get("target_function_node_id"),{}).get("module_id"),
                })
        shapes = {
            record["value"]["literal_node_id"]: record["value"]
            for record in (shape_table or {}).get("records", ())
        }
        containers=[]
        for record in (container_binding_table or {}).get("records", ()):
            value=record["value"]
            shape=shapes.get(value["literal_node_id"], {})
            containers.append({
                "binding_id":value["binding_id"],
                "source_name":value["source_name"],
                "container_kind":value["container_kind"],
                "capacity":value["capacity"],
                "element_category":value["element_category"],
                "key_category":value["key_category"],
                "value_category":value["value_category"],
                "storage_model":shape.get("storage_model"),
                "mutable":shape.get("mutable"),
                "allocation":"none",
                "cleanup":"not-required",
                "valid":value["valid"],
            })
        accesses=[record["value"] for record in (access_table or {}).get("records", ())]
        iterations=[record["value"] for record in (iteration_table or {}).get("records", ())]
        initialization=(module_initialization_table or {}).get("records", ())
        initialization_value=initialization[0]["value"] if initialization else None
        module_order={module_id:ordinal for ordinal,module_id in enumerate((initialization_value or {}).get("module_order",()))}
        modules=sorted(
            (record["value"] for record in (module_identity_table or {}).get("records", ())),
            key=lambda item:(module_order.get(item.get("module_id"),2**31-1),item.get("module_id","")),
        )
        imports=sorted(
            (record["value"] for record in (module_import_table or {}).get("records", ())),
            key=lambda item:(module_order.get(item.get("importer_module_id"),2**31-1),item.get("source_ordinal",2**31-1),item.get("import_item_id","")),
        )
        records=[record["value"] for record in (record_definition_table or {}).get("records", ())]
        record_fields=[record["value"] for record in (record_field_table or {}).get("records", ())]
        record_initializers=[record["value"] for record in (record_initializer_table or {}).get("records", ())]
        record_instances=[record["value"] for record in (record_instance_table or {}).get("records", ())]
        record_bindings=[record["value"] for record in (record_binding_table or {}).get("records", ())]
        record_accesses=[record["value"] for record in (record_access_table or {}).get("records", ())]
        numeric_operations=[record["value"] for record in (numeric_operation_table or {}).get("records", ())]
        conditional_regions=[record["value"] for record in (conditional_region_table or {}).get("records", ())]
        keyword_calls=[record["value"] for record in (keyword_call_table or {}).get("records", ())]
        keyword_only_calls=[record["value"] for record in (keyword_only_call_table or {}).get("records", ())]
        records_enabled=supports_records(payload.get("rule_set_version", ""))
        numeric_enabled=supports_numeric(payload.get("rule_set_version", ""))
        conditional_enabled=supports_conditional_regions(payload.get("rule_set_version", ""))
        keyword_calls_enabled=supports_keyword_calls(payload.get("rule_set_version", ""))
        keyword_only_calls_enabled=supports_keyword_only_calls(payload.get("rule_set_version", ""))
        return {
            "schema_version":CONVERSION_SUMMARY_SCHEMA if keyword_only_calls_enabled else PHASE14C_CONVERSION_SUMMARY_SCHEMA if keyword_calls_enabled else PHASE14B_CONVERSION_SUMMARY_SCHEMA if conditional_enabled else PHASE14_CONVERSION_SUMMARY_SCHEMA if numeric_enabled else PHASE13_CONVERSION_SUMMARY_SCHEMA if records_enabled else PHASE12_CONVERSION_SUMMARY_SCHEMA,
            "target_contract":payload.get("target_contract"),
            "semantic_policy":payload.get("semantic_policy"),
            "rule_set_version":payload.get("rule_set_version"),
            "renderer_version":payload.get("renderer_version"),
            "helper_policy_version":payload.get("helper_policy_version"),
            "container_policy_version":payload.get("container_policy_version"),
            "module_policy_version":payload.get("module_policy_version"),
            **(
                {"record_policy_version": payload.get("record_policy_version")}
                if records_enabled
                else {}
            ),
            **(
                {"numeric_policy_version": payload.get("numeric_policy_version")}
                if numeric_enabled
                else {}
            ),
            "helper_registry_fingerprint":payload.get("helper_registry_fingerprint"),
            "helper_manifest_fingerprint":payload.get("helper_manifest_fingerprint"),
            "helpers":list(payload.get("helper_manifest",())),
            "functions":functions,
            "calls":calls,
            "containers":containers,
            "container_accesses":accesses,
            "container_iterations":iterations,
            "modules":modules,
            "module_imports":imports,
            "module_initialization":initialization_value,
            **(
                {
                    "records": records,
                    "record_fields": record_fields,
                    "record_initializers": record_initializers,
                    "record_instances": record_instances,
                    "record_bindings": record_bindings,
                    "record_accesses": record_accesses,
                }
                if records_enabled
                else {}
            ),
            **(
                {"numeric_operations": numeric_operations}
                if numeric_enabled
                else {}
            ),
            **(
                {"conditional_regions": conditional_regions}
                if conditional_enabled
                else {}
            ),
            **(
                {"keyword_calls": keyword_calls}
                if keyword_calls_enabled
                else {}
            ),
            **(
                {"keyword_only_calls": keyword_only_calls}
                if keyword_only_calls_enabled
                else {}
            ),
            "translation_unit_count":1,
        }
