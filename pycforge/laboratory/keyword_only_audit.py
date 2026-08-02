"""Authenticated laboratory audit for required keyword-only direct calls."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .keyword_audit import _facts, _lowering_proof, _table


def audit_keyword_only(root: Path) -> dict[str, Any]:
    """Gate the bounded Phase 14D profile without invoking a C toolchain."""

    from pycforge import (
        ConversionRequest,
        PythonToCConverter,
        ResultStatus,
        SourceBundle,
        SourceDocumentInput,
    )
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.contracts.configuration import (
        DEFAULT_RENDERER,
        DEFAULT_RULE_SET,
        PHASE14C_RENDERER,
        PHASE14C_RULE_SET,
    )
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        CONVERSION_SUMMARY_SCHEMA,
        DECISION_TRACE_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_SUMMARY_SCHEMA,
        PHASE14C_DECISION_TRACE_SCHEMA,
    )
    from pycforge.converter.core.request import ObservationOptions
    from pycforge.converter.core.serialization import result_to_json
    from pycforge.converter.keyword_only_calls import (
        KEYWORD_ONLY_CALL_KEY_DOMAIN,
        KEYWORD_ONLY_CALL_LOWERING_SHAPE,
        KEYWORD_ONLY_CALL_OBLIGATIONS,
        KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
        KEYWORD_ONLY_CALL_RULE_ID,
        KEYWORD_ONLY_CALL_RULE_VERSION,
        KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
        KEYWORD_ONLY_CALL_TABLE_ID,
        validate_keyword_only_call_binding_facts,
    )
    from pycforge.converter.support_templates import default_helper_registry

    source = (
        "def mark_int(value: int) -> int:\n    return value\n\n"
        "def mark_bool(value: bool) -> bool:\n    return value\n\n"
        "def mark_float(value: float) -> float:\n    return value\n\n"
        "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
        "    return left\n\n"
        "def run(x: int, y: bool, z: float) -> int:\n"
        "    return choose(ratio=mark_float(z), left=mark_int(x), flag=mark_bool(y))\n"
    )
    cross_primary = (
        "from lib import choose\n\n"
        "def run(value: int, flag: bool, ratio: float) -> int:\n"
        "    return choose(ratio=ratio, flag=flag, left=value)\n"
    )
    cross_companion = (
        "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
        "    return left\n"
    )
    required_sink = (
        "def sink(value: int, *, flag: bool) -> int:\n"
        "    return value\n\n"
    )
    rejections = {
        "missing-keyword": (
            "PYC2904",
            required_sink
            + "def run(value: int) -> int:\n    return sink(value)\n",
        ),
        "keyword-only-positional": (
            "PYC2904",
            required_sink
            + "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value, flag)\n",
        ),
        "unknown-keyword": (
            "PYC2912",
            required_sink
            + "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value=value, missing=flag)\n",
        ),
        "duplicate-binding": (
            "PYC2912",
            required_sink
            + "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value, value=value, flag=flag)\n",
        ),
        "keyword-unpacking": (
            "PYC2910",
            required_sink
            + "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value=value, **flag)\n",
        ),
        "mapped-category": (
            "PYC2905",
            required_sink
            + "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value=flag, flag=value)\n",
        ),
        "defaulted-keyword-only": (
            "PYC2911",
            "def sink(value: int, *, flag: bool = True) -> int:\n"
            "    return value\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value=value, flag=flag)\n",
        ),
        "variadic-target": (
            "PYC2911",
            "def sink(value: int, *rest: int, flag: bool) -> int:\n"
            "    return value\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return sink(value=value, flag=flag)\n",
        ),
        "recursive-target": (
            "PYC2920",
            "def run(value: int, *, flag: bool) -> int:\n"
            "    return run(value=value, flag=flag)\n",
        ),
    }
    expected_contracts = {
        "rule_set": "phase14-required-keyword-only-calls-v0.14.3",
        "renderer": "c-renderer-v0.14.3",
        "keyword_only_call_facts": "fact-table/0.14.3",
        "conversion_plan": "conversion-plan/0.14.3",
        "c_ir": "c-ir/0.14.3",
        "generated_c": "generated-c/0.14.3",
        "conversion_summary": "pycforge.conversion-summary/0.14.3",
        "decision_trace": "pycforge.decision-trace/0.14.3",
    }

    try:
        converter = PythonToCConverter()
        observation = ObservationOptions("Full", False)
        accepted = converter.convert(
            ConversionRequest.from_source(source),
            observation=observation,
        )
        repeated = converter.convert(
            ConversionRequest.from_source(source),
            observation=observation,
        )
        if accepted.stage_artifact is None:
            raise ValueError("keyword-only conversion omitted its final artifact")
        payload = accepted.stage_artifact.payload
        summary = accepted.conversion_summary or {}
        trace = accepted.decision_trace or {}
        contracts = {
            "rule_set": DEFAULT_RULE_SET,
            "renderer": DEFAULT_RENDERER,
            "keyword_only_call_facts": KEYWORD_ONLY_CALL_FACT_SCHEMA,
            "conversion_plan": CONVERSION_PLAN_SCHEMA,
            "c_ir": C_IR_SCHEMA,
            "generated_c": GENERATED_C_SCHEMA,
            "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
            "decision_trace": DECISION_TRACE_SCHEMA,
        }
        identity_valid = (
            contracts == expected_contracts
            and accepted.status is ResultStatus.CONVERTED
            and accepted.stage_artifact.kind == "generated_c"
            and accepted.stage_artifact.schema_version == "0.14.3"
            and payload.get("schema_version") == GENERATED_C_SCHEMA
            and payload.get("c_ir_schema") == C_IR_SCHEMA
            and payload.get("rule_set_version") == DEFAULT_RULE_SET
            and payload.get("renderer_version") == DEFAULT_RENDERER
            and summary.get("schema_version") == CONVERSION_SUMMARY_SCHEMA
            and trace.get("schema_version") == DECISION_TRACE_SCHEMA
        )
        table = _table(payload, KEYWORD_ONLY_CALL_TABLE_ID)
        records = list(table.get("records", ()))
        facts = _facts(payload, KEYWORD_ONLY_CALL_TABLE_ID)
        fact = facts[0] if len(facts) == 1 else {}
        constants_valid = (
            KEYWORD_ONLY_CALL_TABLE_ID == "keyword-only-call-binding-facts"
            and KEYWORD_ONLY_CALL_KEY_DOMAIN == "keyword-only-call-node-id"
            and KEYWORD_ONLY_CALL_RULE_ID
            == "phase14.keyword_only_call.exact_binding"
            and KEYWORD_ONLY_CALL_RULE_VERSION == "0.14.3"
            and KEYWORD_ONLY_CALL_LOWERING_SHAPE
            == "source-order-actual-temporaries-formal-order-references-v1"
        )
        table_valid = (
            table.get("schema_version") == KEYWORD_ONLY_CALL_FACT_SCHEMA
            and table.get("producer_stage") == "analysis.plan"
            and table.get("key_domain") == KEYWORD_ONLY_CALL_KEY_DOMAIN
            and table.get("completeness") == "complete"
            and tuple(table.get("invalidation_dependencies", ()))
            == KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES
            and len(records) == 1
            and records[0].get("key") == fact.get("call_node_id")
            and tuple(records[0].get("provenance", {}).get("evidence", ()))
            == KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE
        )
        fact_valid = (
            fact.get("supported") is True
            and fact.get("parameter_names") == ["left", "flag", "ratio"]
            and fact.get("parameter_kinds")
            == ["positional-or-keyword", "keyword-only", "keyword-only"]
            and fact.get("keyword_names") == ["ratio", "left", "flag"]
            and fact.get("source_to_parameter_ordinals") == [2, 0, 1]
            and fact.get("parameter_to_source_ordinals") == [1, 2, 0]
            and fact.get("evaluation_order")
            == fact.get("source_argument_node_ids")
            and fact.get("arguments_evaluated_once") is True
            and fact.get("parameter_coverage_exact") is True
            and fact.get("keyword_only_coverage_exact") is True
            and fact.get("lowering_shape") == KEYWORD_ONLY_CALL_LOWERING_SHAPE
            and fact.get("allocation_model") == "none"
            and fact.get("cleanup_model") == "none"
            and fact.get("runtime_binding_failure") == "proved-absent"
        )
        independent_valid, independent_reason = (
            validate_keyword_only_call_binding_facts(payload)
        )
        plans = [
            item
            for item in payload.get("rule_plans", ())
            if item.get("rule_id") == KEYWORD_ONLY_CALL_RULE_ID
        ]
        plan_valid = (
            len(plans) == 1
            and plans[0].get("source_node_id") == fact.get("call_node_id")
            and plans[0].get("rule_version") == KEYWORD_ONLY_CALL_RULE_VERSION
            and plans[0].get("support_state") == "SupportedDirect"
            and plans[0].get("helper_requirements") == []
            and plans[0].get("semantic_obligations")[: len(KEYWORD_ONLY_CALL_OBLIGATIONS)]
            == list(KEYWORD_ONLY_CALL_OBLIGATIONS)
            and plans[0].get("resolved_obligations")
            == plans[0].get("semantic_obligations")
            and plans[0].get("unresolved_obligations") == []
        )
        lowering_valid, lowering_evidence = _lowering_proof(payload, facts)
        observer_valid = (
            list(summary.get("keyword_only_calls", ())) == facts
            and [
                item
                for item in trace.get("rule_decisions", ())
                if item.get("rule_id") == KEYWORD_ONLY_CALL_RULE_ID
            ]
            == plans
            and trace.get("trace_level") == "Full"
            and trace.get("completeness") == "complete"
            and trace.get("truncated") is False
            and trace.get("observer_failed") is False
        )
        helper_registry = default_helper_registry()
        helper_valid = (
            payload.get("helper_manifest") == []
            and payload.get("helper_requirements") == []
            and helper_registry.fingerprint
            == "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
        )
        deterministic = (
            result_to_json(accepted) == result_to_json(repeated)
            and accepted.request_fingerprint == repeated.request_fingerprint
            and accepted.output_fingerprint == repeated.output_fingerprint
            and accepted.stage_artifact.artifact_fingerprint
            == repeated.stage_artifact.artifact_fingerprint
        )
        fresh_code = (
            "import hashlib,json; "
            "from pycforge import ConversionRequest,PythonToCConverter; "
            "from pycforge.converter.core.request import ObservationOptions; "
            "from pycforge.converter.core.serialization import result_to_json; "
            f"s={source!r}; "
            "r=PythonToCConverter().convert(ConversionRequest.from_source(s),"
            "observation=ObservationOptions('Full',False)); "
            "print(json.dumps({'serialized_sha256':hashlib.sha256(result_to_json(r).encode()).hexdigest(),"
            "'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
            "'artifact_fingerprint':r.stage_artifact.artifact_fingerprint.value},sort_keys=True))"
        )
        fresh = json.loads(
            subprocess.check_output(
                [sys.executable, "-c", fresh_code],
                cwd=root,
                env={**__import__("os").environ, "PYTHONPATH": str(root)},
                text=True,
            )
        )
        fresh_expected = {
            "serialized_sha256": hashlib.sha256(
                result_to_json(accepted).encode()
            ).hexdigest(),
            "generated_sha256": hashlib.sha256(
                (accepted.generated_c or "").encode()
            ).hexdigest(),
            "artifact_fingerprint": accepted.stage_artifact.artifact_fingerprint.value,
        }
        fresh_valid = fresh == fresh_expected

        cross_request = ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", cross_primary, "app"),
                (SourceDocumentInput("lib.py", cross_companion, "lib"),),
            )
        )
        cross = converter.convert(cross_request, observation=observation)
        cross_repeated = converter.convert(cross_request, observation=observation)
        cross_payload = (
            cross.stage_artifact.payload if cross.stage_artifact is not None else {}
        )
        cross_facts = (
            _facts(cross_payload, KEYWORD_ONLY_CALL_TABLE_ID)
            if cross_payload
            else []
        )
        cross_fact = cross_facts[0] if len(cross_facts) == 1 else {}
        cross_independent, cross_reason = (
            validate_keyword_only_call_binding_facts(cross_payload)
            if cross_payload
            else (False, "cross-module conversion omitted its payload")
        )
        cross_lowering, cross_lowering_evidence = _lowering_proof(
            cross_payload,
            cross_facts,
        )
        cross_valid = (
            cross.status is ResultStatus.CONVERTED
            and cross.stage_artifact is not None
            and cross.stage_artifact.schema_version == "0.14.3"
            and cross_fact.get("source_to_parameter_ordinals") == [2, 1, 0]
            and cross_fact.get("parameter_to_source_ordinals") == [2, 1, 0]
            and (cross.conversion_summary or {})
            .get("module_initialization", {})
            .get("module_order")
            == ["lib", "app"]
            and cross_independent
            and cross_lowering
            and result_to_json(cross) == result_to_json(cross_repeated)
            and validate_c_text(cross.generated_c or "").accepted
            and cross_payload.get("helper_manifest") == []
        )

        rejected = {
            label: converter.convert(ConversionRequest.from_source(text))
            for label, (_, text) in rejections.items()
        }
        rejection_codes = {
            label: [item.code for item in result.diagnostics]
            for label, result in rejected.items()
        }
        rejections_valid = all(
            result.status is ResultStatus.REJECTED
            and rejection_codes[label] == [code]
            and result.generated_c is None
            and result.output_fingerprint is None
            and result.stage_artifact is not None
            and "c_ir" not in result.stage_artifact.payload
            and "helper_manifest" not in result.stage_artifact.payload
            for label, (code, _) in rejections.items()
            for result in (rejected[label],)
        )

        historical = converter.convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE14C_RULE_SET,
                renderer_version=PHASE14C_RENDERER,
            ),
            observation=observation,
        )
        historical_payload = (
            historical.stage_artifact.payload
            if historical.stage_artifact is not None
            else {}
        )
        historical_exact = (
            historical.status is ResultStatus.REJECTED
            and [item.code for item in historical.diagnostics] == ["PYC2911"]
            and historical.stage_artifact is not None
            and historical.stage_artifact.kind == "conversion_plan"
            and historical.stage_artifact.schema_version == "0.14.2"
            and historical_payload.get("schema_version")
            == PHASE14C_CONVERSION_PLAN_SCHEMA
            and (historical.conversion_summary or {}).get("schema_version")
            == PHASE14C_CONVERSION_SUMMARY_SCHEMA
            and (historical.decision_trace or {}).get("schema_version")
            == PHASE14C_DECISION_TRACE_SCHEMA
            and KEYWORD_ONLY_CALL_TABLE_ID
            not in {
                item.get("table_id")
                for item in historical_payload.get("fact_tables", ())
            }
            and historical.generated_c is None
            and historical.output_fingerprint is None
        )
        generated_conformance = validate_c_text(accepted.generated_c or "").accepted
        passed = all(
            (
                identity_valid,
                constants_valid,
                table_valid,
                fact_valid,
                independent_valid,
                plan_valid,
                lowering_valid,
                observer_valid,
                helper_valid,
                generated_conformance,
                deterministic,
                fresh_valid,
                cross_valid,
                rejections_valid,
                historical_exact,
            )
        )
        return {
            "audit": "keyword-only",
            "passed": passed,
            "active_contracts": contracts,
            "active_contract_identities_valid": identity_valid,
            "keyword_only_rule_id": KEYWORD_ONLY_CALL_RULE_ID,
            "keyword_only_rule_version": KEYWORD_ONLY_CALL_RULE_VERSION,
            "keyword_only_fact_schema": KEYWORD_ONLY_CALL_FACT_SCHEMA,
            "keyword_only_contract_constants_valid": constants_valid,
            "keyword_only_fact_count": len(facts),
            "keyword_only_fact_table_valid": table_valid,
            "keyword_only_facts_valid": fact_valid,
            "keyword_only_rule_plan_count": len(plans),
            "keyword_only_rule_plans_valid": plan_valid,
            "independent_fact_and_plan_validation": independent_valid,
            "independent_validation_message": independent_reason,
            "source_to_parameter_ordinals": fact.get(
                "source_to_parameter_ordinals"
            ),
            "parameter_to_source_ordinals": fact.get(
                "parameter_to_source_ordinals"
            ),
            "source_order_staging_and_formal_reference_permutation_valid": lowering_valid,
            "lowering_evidence": lowering_evidence,
            "observer_evidence_valid": observer_valid,
            "cross_module_valid": cross_valid,
            "cross_module_independent_validation": cross_independent,
            "cross_module_independent_validation_message": cross_reason,
            "cross_module_lowering_evidence": cross_lowering_evidence,
            "rejection_codes": rejection_codes,
            "rejections_exact_and_publish_no_c": rejections_valid,
            "historical_phase14c_exact_rejection": historical_exact,
            "helper_manifest_empty": payload.get("helper_manifest") == [],
            "helper_registry_fingerprint": helper_registry.fingerprint,
            "helper_contract_unchanged": helper_valid,
            "allocation": "none",
            "cleanup": "none",
            "runtime_binding_failure": "proved-absent",
            "generated_c_conformance": generated_conformance,
            "deterministic": deterministic,
            "fresh_process_deterministic": fresh_valid,
            "serialized_sha256": fresh_expected["serialized_sha256"],
            "generated_c_sha256": fresh_expected["generated_sha256"],
            "python_subprocess_used_for_determinism_only": True,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    except Exception as exc:
        return {
            "audit": "keyword-only",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "python_subprocess_used_for_determinism_only": True,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }


__all__ = ["audit_keyword_only"]
