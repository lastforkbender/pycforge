"""Authenticated laboratory audit for the bounded Phase 14C keyword slice."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _kind_dicts(value: Any, kind: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("kind") == kind:
            found.append(value)
        for child in value.values():
            found.extend(_kind_dicts(child, kind))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_kind_dicts(child, kind))
    return found


def _table(payload: dict[str, Any], table_id: str) -> dict[str, Any]:
    return next(
        item
        for item in payload.get("fact_tables", ())
        if item.get("table_id") == table_id
    )


def _facts(payload: dict[str, Any], table_id: str) -> list[dict[str, Any]]:
    return [
        item.get("value", {})
        for item in _table(payload, table_id).get("records", ())
    ]


def _lowering_proof(
    payload: dict[str, Any], fact_values: list[dict[str, Any]]
) -> tuple[bool, list[dict[str, Any]]]:
    """Reconstruct source staging and formal-reference order from C IR."""

    c_ir = payload.get("c_ir", {})
    declarations = _kind_dicts(c_ir, "CVariableDeclaration")
    calls = _kind_dicts(c_ir, "CCallExpr")
    evidence: list[dict[str, Any]] = []
    valid = True
    for fact in fact_values:
        call_id = fact.get("call_node_id")
        source_ids = list(fact.get("source_argument_node_ids", ()))
        staged = [
            item
            for item in declarations
            if str(item.get("node_id", "")).startswith("c-arg-temp-")
            and call_id in item.get("provenance", {}).get("source_node_ids", ())
        ]
        staged_source: list[str | None] = []
        staged_bindings: list[str | None] = []
        for declaration in staged:
            matches = [
                source_id
                for source_id in source_ids
                if source_id
                in declaration.get("provenance", {}).get("source_node_ids", ())
            ]
            staged_source.append(matches[0] if len(matches) == 1 else None)
            staged_bindings.append(
                declaration.get("identifier", {}).get("binding_id")
            )
        target_calls = [
            item
            for item in calls
            if call_id in item.get("provenance", {}).get("source_node_ids", ())
        ]
        target_call = target_calls[0] if len(target_calls) == 1 else {}
        actual_formal = [
            item.get("binding_id") for item in target_call.get("arguments", ())
        ]
        permutation = list(fact.get("parameter_to_source_ordinals", ()))
        permutation_valid = (
            len(permutation) == len(staged_bindings)
            and all(
                isinstance(index, int) and 0 <= index < len(staged_bindings)
                for index in permutation
            )
        )
        expected_formal = (
            [staged_bindings[index] for index in permutation]
            if permutation_valid
            else []
        )
        item_valid = (
            staged_source == source_ids
            and len(staged_bindings) == len(source_ids)
            and len(set(staged_bindings)) == len(staged_bindings)
            and len(target_calls) == 1
            and actual_formal == expected_formal
            and all(
                argument.get("kind") == "CIdentifierRef"
                for argument in target_call.get("arguments", ())
            )
        )
        valid = valid and item_valid
        evidence.append(
            {
                "call_node_id": call_id,
                "source_order": staged_source,
                "parameter_to_source_ordinals": permutation,
                "formal_reference_binding_ids": actual_formal,
                "valid": item_valid,
            }
        )
    return valid, evidence


def audit_keyword(root: Path) -> dict[str, Any]:
    """Independently gate direct keyword binding without invoking C tools."""

    from pycforge import (
        ConversionRequest,
        PythonToCConverter,
        ResultStatus,
        SourceBundle,
        SourceDocumentInput,
    )
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.contracts.configuration import (
        PHASE14B_RENDERER,
        PHASE14B_RULE_SET,
        PHASE14C_RENDERER,
        PHASE14C_RULE_SET,
    )
    from pycforge.converter.contracts.versions import (
        KEYWORD_CALL_FACT_SCHEMA,
        PHASE14C_C_IR_SCHEMA,
        PHASE14C_CONVERSION_PLAN_SCHEMA,
        PHASE14C_CONVERSION_SUMMARY_SCHEMA,
        PHASE14C_DECISION_TRACE_SCHEMA,
        PHASE14C_GENERATED_C_SCHEMA,
        RESULT_SCHEMA_VERSION,
    )
    from pycforge.converter.core.request import ObservationOptions
    from pycforge.converter.core.serialization import result_to_json
    from pycforge.converter.keyword_calls import (
        KEYWORD_CALL_KEY_DOMAIN,
        KEYWORD_CALL_LOWERING_SHAPE,
        KEYWORD_CALL_OBLIGATIONS,
        KEYWORD_CALL_PROVENANCE_EVIDENCE,
        KEYWORD_CALL_RULE_ID,
        KEYWORD_CALL_RULE_VERSION,
        KEYWORD_CALL_TABLE_DEPENDENCIES,
        KEYWORD_CALL_TABLE_ID,
        validate_keyword_call_binding_facts,
    )
    from pycforge.converter.support_templates import default_helper_registry

    expected_obligations = (
        "direct-source-target-resolved-once",
        "explicit-keywords-only-no-unpacking",
        "positional-prefix-bound-in-order",
        "keyword-names-bound-to-positional-or-keyword-parameters",
        "parameter-coverage-exact",
        "argument-representations-compatible-after-binding",
        "source-arguments-evaluated-left-to-right-once",
        "argument-temporaries-reordered-only-after-evaluation",
        "c-call-arguments-in-formal-order",
        "parameter-ownership-boundary-explicit",
        "runtime-binding-failure-absent",
        "allocation-and-cleanup-absent",
        "structured-c-ir-only",
        "source-provenance-anchored",
        "cancellation-safe-points-honored",
        "target-contract-exact",
    )
    expected_dependencies = (
        "binding-facts",
        "function-signature-facts",
        "value-category-facts",
        "call-target-facts",
        "evaluation-order-facts",
    )
    expected_provenance = (
        "direct-source-target",
        "exact-explicit-keyword-names",
        "complete-parameter-coverage",
        "source-order-evaluation",
        "formal-order-reference-permutation",
        "single-evaluation",
    )
    source = (
        "def mark_int(value: int) -> int:\n    return value\n\n"
        "def mark_bool(value: bool) -> bool:\n    return value\n\n"
        "def mark_float(value: float) -> float:\n    return value\n\n"
        "def choose(left: int, flag: bool, ratio: float) -> int:\n"
        "    return left\n\n"
        "def direct(x: int, y: bool, z: float) -> int:\n"
        "    return choose(left=x, flag=y, ratio=z)\n\n"
        "def reordered(x: int, y: bool, z: float) -> int:\n"
        "    return choose(ratio=mark_float(z), left=mark_int(x), flag=mark_bool(y))\n"
    )
    cross_primary = (
        "from lib import choose\n\n"
        "def run(value: int, flag: bool, ratio: float) -> int:\n"
        "    return choose(ratio=ratio, flag=flag, left=value)\n"
    )
    cross_companion = (
        "def choose(left: int, flag: bool, ratio: float) -> int:\n"
        "    return left\n"
    )
    sink = "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
    record = (
        "class Sample:\n    count: int\n"
        "    def __init__(self, count: int) -> None:\n"
        "        self.count = count\n\n"
        "def run(value: int) -> int:\n"
        "    sample = Sample(count=value)\n    return value\n"
    )
    rejections = {
        "star-positional": ("PYC2910", "def sink(value: int) -> int:\n    return value\n\ndef run(value: int) -> int:\n    return sink(*value)\n"),
        "star-keyword": ("PYC2910", "def sink(value: int) -> int:\n    return value\n\ndef run(value: int) -> int:\n    return sink(**value)\n"),
        "positional-only-name": ("PYC2912", "def sink(value: int, /, flag: bool) -> int:\n    return value\n\ndef run(value: int, flag: bool) -> int:\n    return sink(value=value, flag=flag)\n"),
        "unknown-name": ("PYC2912", sink + "def run(value: int, flag: bool) -> int:\n    return sink(missing=value, flag=flag)\n"),
        "positional-keyword-collision": ("PYC2912", sink + "def run(value: int, flag: bool) -> int:\n    return sink(value, value=value, flag=flag)\n"),
        "duplicate-keyword": ("PYC2912", sink + "def run(value: int, flag: bool) -> int:\n    return sink(value=value, flag=flag, value=value)\n"),
        "missing-parameter": ("PYC2904", sink + "def run(value: int) -> int:\n    return sink(value=value)\n"),
        "excess-positional": ("PYC2904", sink + "def run(value: int, flag: bool) -> int:\n    return sink(value, flag, value)\n"),
        "mapped-category": ("PYC2905", sink + "def run(value: int, flag: bool) -> int:\n    return sink(flag=value, value=flag)\n"),
        "default-target": ("PYC2911", "def sink(value: int, flag: bool = True) -> int:\n    return value\n\ndef run(value: int, flag: bool) -> int:\n    return sink(flag=flag, value=value)\n"),
        "keyword-only-target": ("PYC2911", "def sink(value: int, *, flag: bool) -> int:\n    return value\n\ndef run(value: int, flag: bool) -> int:\n    return sink(flag=flag, value=value)\n"),
        "variadic-target": ("PYC2911", "def sink(value: int, *rest: int) -> int:\n    return value\n\ndef run(value: int) -> int:\n    return sink(value=value)\n"),
        "range-keyword": ("PYC2842", "def run() -> int:\n    total = 0\n    for item in range(stop=3):\n        total = total + item\n    return total\n"),
        "record-constructor-keyword": ("PYC3605", record),
        "dynamic-target": ("PYC2901", "def run(value: int) -> int:\n    return missing(value=value)\n"),
        "recursive-target": ("PYC2920", "def run(value: int) -> int:\n    return run(value=value)\n"),
    }

    try:
        converter = PythonToCConverter()
        observation = ObservationOptions("Full", False)
        def phase14c_request(text: str) -> ConversionRequest:
            return ConversionRequest.from_source(
                text,
                rule_set_version=PHASE14C_RULE_SET,
                renderer_version=PHASE14C_RENDERER,
            )
        accepted = converter.convert(
            phase14c_request(source), observation=observation
        )
        repeated = converter.convert(
            phase14c_request(source), observation=observation
        )
        if accepted.stage_artifact is None:
            raise ValueError("keyword conversion omitted its final artifact")
        payload = accepted.stage_artifact.payload
        summary = accepted.conversion_summary or {}
        trace = accepted.decision_trace or {}
        active_contracts = {
            "rule_set": PHASE14C_RULE_SET,
            "renderer": PHASE14C_RENDERER,
            "keyword_call_facts": KEYWORD_CALL_FACT_SCHEMA,
            "conversion_plan": PHASE14C_CONVERSION_PLAN_SCHEMA,
            "c_ir": PHASE14C_C_IR_SCHEMA,
            "generated_c": PHASE14C_GENERATED_C_SCHEMA,
            "conversion_summary": PHASE14C_CONVERSION_SUMMARY_SCHEMA,
            "decision_trace": PHASE14C_DECISION_TRACE_SCHEMA,
            "result_serialization": RESULT_SCHEMA_VERSION,
        }
        active_contracts_valid = active_contracts == {
            "rule_set": "phase14-direct-keyword-calls-v0.14.2",
            "renderer": "c-renderer-v0.14.2",
            "keyword_call_facts": "fact-table/0.14.2",
            "conversion_plan": "conversion-plan/0.14.2",
            "c_ir": "c-ir/0.14.2",
            "generated_c": "generated-c/0.14.2",
            "conversion_summary": "pycforge.conversion-summary/0.14.2",
            "decision_trace": "pycforge.decision-trace/0.14.2",
            "result_serialization": "0.5",
        }
        identity_valid = (
            active_contracts_valid
            and accepted.status is ResultStatus.CONVERTED
            and accepted.generated_c is not None
            and accepted.stage_artifact.kind == "generated_c"
            and accepted.stage_artifact.schema_version == "0.14.2"
            and payload.get("schema_version") == PHASE14C_GENERATED_C_SCHEMA
            and payload.get("c_ir_schema") == PHASE14C_C_IR_SCHEMA
            and payload.get("c_ir", {}).get("schema_version") == PHASE14C_C_IR_SCHEMA
            and payload.get("rule_set_version") == PHASE14C_RULE_SET
            and payload.get("renderer_version") == PHASE14C_RENDERER
            and summary.get("schema_version") == PHASE14C_CONVERSION_SUMMARY_SCHEMA
            and trace.get("schema_version") == PHASE14C_DECISION_TRACE_SCHEMA
        )
        constants_valid = (
            KEYWORD_CALL_TABLE_ID == "keyword-call-binding-facts"
            and KEYWORD_CALL_KEY_DOMAIN == "keyword-call-node-id"
            and KEYWORD_CALL_LOWERING_SHAPE
            == "source-order-temporaries-formal-order-references-v1"
            and KEYWORD_CALL_RULE_ID == "phase14.keyword_call.exact_binding"
            and KEYWORD_CALL_RULE_VERSION == "0.14.2"
            and KEYWORD_CALL_OBLIGATIONS == expected_obligations
            and KEYWORD_CALL_TABLE_DEPENDENCIES == expected_dependencies
            and KEYWORD_CALL_PROVENANCE_EVIDENCE == expected_provenance
        )
        fact_table = _table(payload, KEYWORD_CALL_TABLE_ID)
        records = list(fact_table.get("records", ()))
        fact_values = _facts(payload, KEYWORD_CALL_TABLE_ID)
        table_valid = (
            fact_table.get("schema_version") == KEYWORD_CALL_FACT_SCHEMA
            and fact_table.get("producer_stage") == "analysis.plan"
            and fact_table.get("key_domain") == KEYWORD_CALL_KEY_DOMAIN
            and fact_table.get("completeness") == "complete"
            and tuple(fact_table.get("invalidation_dependencies", ()))
            == expected_dependencies
            and len(records) == 2
            and [item.get("key") for item in records]
            == sorted(item.get("key") for item in records)
            and len({item.get("key") for item in records}) == 2
            and all(
                item.get("key") == item.get("value", {}).get("call_node_id")
                and tuple(item.get("provenance", {}).get("evidence", ()))
                == expected_provenance
                for item in records
            )
        )
        independent_valid, independent_reason = validate_keyword_call_binding_facts(
            payload
        )
        direct = next(
            (item for item in fact_values if item.get("keyword_names") == ["left", "flag", "ratio"]),
            {},
        )
        reordered = next(
            (item for item in fact_values if item.get("keyword_names") == ["ratio", "left", "flag"]),
            {},
        )
        facts_valid = (
            direct.get("source_to_parameter_ordinals") == [0, 1, 2]
            and direct.get("parameter_to_source_ordinals") == [0, 1, 2]
            and reordered.get("source_to_parameter_ordinals") == [2, 0, 1]
            and reordered.get("parameter_to_source_ordinals") == [1, 2, 0]
            and all(
                fact.get("target_name") == "choose"
                and fact.get("parameter_names") == ["left", "flag", "ratio"]
                and fact.get("evaluation_order")
                == fact.get("source_argument_node_ids")
                and fact.get("arguments_evaluated_once") is True
                and fact.get("parameter_coverage_exact") is True
                and fact.get("lowering_shape") == KEYWORD_CALL_LOWERING_SHAPE
                and fact.get("allocation_model") == "none"
                and fact.get("cleanup_model") == "none"
                and fact.get("runtime_binding_failure") == "proved-absent"
                and fact.get("supported") is True
                and fact.get("diagnostic_code") is None
                for fact in fact_values
            )
        )
        plans = [
            item
            for item in payload.get("rule_plans", ())
            if item.get("rule_id") == KEYWORD_CALL_RULE_ID
        ]
        plans_valid = (
            len(plans) == 2
            and {item.get("source_node_id") for item in plans}
            == {item.get("call_node_id") for item in fact_values}
            and all(
                item.get("rule_version") == KEYWORD_CALL_RULE_VERSION
                and item.get("support_state") == "SupportedDirect"
                and item.get("helper_requirements") == []
                and item.get("unresolved_obligations") == []
                and item.get("resolved_obligations")
                == item.get("semantic_obligations")
                for item in plans
            )
        )
        lowering_valid, lowering_evidence = _lowering_proof(payload, fact_values)
        observer_valid = (
            summary.get("rule_set_version") == PHASE14C_RULE_SET
            and summary.get("renderer_version") == PHASE14C_RENDERER
            and list(summary.get("keyword_calls", ())) == fact_values
            and trace.get("trace_level") == "Full"
            and trace.get("completeness") == "complete"
            and trace.get("truncated") is False
            and trace.get("observer_failed") is False
            and [
                item
                for item in trace.get("rule_decisions", ())
                if item.get("rule_id") == KEYWORD_CALL_RULE_ID
            ]
            == plans
            and all(
                any(
                    mapping.get("rule_plan_id") == plan.get("plan_id")
                    for mapping in payload.get("source_output_mappings", ())
                )
                for plan in plans
            )
        )
        helper_registry = default_helper_registry()
        helper_valid = (
            not payload.get("helper_manifest")
            and not payload.get("helper_requirements")
            and helper_registry.fingerprint
            == "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
        )
        conformance = validate_c_text(accepted.generated_c or "")
        deterministic = (
            result_to_json(accepted) == result_to_json(repeated)
            and accepted.request_fingerprint == repeated.request_fingerprint
            and accepted.output_fingerprint == repeated.output_fingerprint
            and accepted.stage_artifact.artifact_fingerprint
            == repeated.stage_artifact.artifact_fingerprint
        )
        fresh_code = (
            "import hashlib,json; from pycforge import ConversionRequest,PythonToCConverter; "
            "from pycforge.converter.contracts.configuration import PHASE14C_RENDERER,PHASE14C_RULE_SET; "
            "from pycforge.converter.core.request import ObservationOptions; "
            "from pycforge.converter.core.serialization import result_to_json; "
            f"s={source!r}; "
            "r=PythonToCConverter().convert(ConversionRequest.from_source(s,rule_set_version=PHASE14C_RULE_SET,renderer_version=PHASE14C_RENDERER),observation=ObservationOptions('Full',False)); "
            "print(json.dumps({'serialized_sha256':hashlib.sha256(result_to_json(r).encode()).hexdigest(),"
            "'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
            "'artifact_fingerprint':r.stage_artifact.artifact_fingerprint.value},sort_keys=True))"
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(root)}
        fresh = json.loads(
            subprocess.check_output(
                [sys.executable, "-c", fresh_code], cwd=root, env=env, text=True
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
        fresh_process_valid = fresh == fresh_expected

        cross_request = ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", cross_primary, "app"),
                (SourceDocumentInput("lib.py", cross_companion, "lib"),),
            ),
            rule_set_version=PHASE14C_RULE_SET,
            renderer_version=PHASE14C_RENDERER,
        )
        cross = converter.convert(cross_request, observation=observation)
        cross_repeat = converter.convert(cross_request, observation=observation)
        cross_payload = (
            cross.stage_artifact.payload if cross.stage_artifact is not None else {}
        )
        cross_facts = (
            _facts(cross_payload, KEYWORD_CALL_TABLE_ID) if cross_payload else []
        )
        cross_independent, cross_reason = (
            validate_keyword_call_binding_facts(cross_payload)
            if cross_payload
            else (False, "cross-module conversion omitted its payload")
        )
        module_functions = (
            {
                item.get("value", {}).get("function_node_id"): item.get("value", {})
                for item in _table(
                    cross_payload, "module-function-facts"
                ).get("records", ())
            }
            if cross_payload
            else {}
        )
        cross_lowering, cross_lowering_evidence = _lowering_proof(
            cross_payload, cross_facts
        )
        cross_fact = cross_facts[0] if len(cross_facts) == 1 else {}
        cross_valid = (
            cross.status is ResultStatus.CONVERTED
            and cross.stage_artifact is not None
            and cross.stage_artifact.schema_version == "0.14.2"
            and cross_payload.get("rule_set_version") == PHASE14C_RULE_SET
            and cross_payload.get("renderer_version") == PHASE14C_RENDERER
            and len(cross_facts) == 1
            and cross_fact.get("source_to_parameter_ordinals") == [2, 1, 0]
            and cross_fact.get("parameter_to_source_ordinals") == [2, 1, 0]
            and module_functions.get(
                cross_fact.get("target_function_node_id"), {}
            ).get("module_id")
            == "lib"
            and (cross.conversion_summary or {})
            .get("module_initialization", {})
            .get("module_order")
            == ["lib", "app"]
            and cross_independent
            and cross_lowering
            and result_to_json(cross) == result_to_json(cross_repeat)
            and validate_c_text(cross.generated_c or "").accepted
            and not cross_payload.get("helper_manifest")
        )

        rejected = {
            label: converter.convert(phase14c_request(text))
            for label, (_, text) in rejections.items()
        }
        rejection_codes = {
            label: [item.code for item in result.diagnostics]
            for label, result in rejected.items()
        }
        rejections_valid = all(
            result.status is ResultStatus.REJECTED
            and rejection_codes[label] == [expected_code]
            and result.generated_c is None
            and result.output_fingerprint is None
            and result.stage_artifact is not None
            and "c_ir" not in result.stage_artifact.payload
            and "helper_manifest" not in result.stage_artifact.payload
            for label, (expected_code, _) in rejections.items()
            for result in (rejected[label],)
        )

        historical_source = (
            "def choose(left: int, flag: bool) -> int:\n    return left\n\n"
            "def run(value: int, flag: bool) -> int:\n"
            "    return choose(flag=flag, left=value)\n"
        )
        historical = converter.convert(
            ConversionRequest.from_source(
                historical_source,
                rule_set_version=PHASE14B_RULE_SET,
                renderer_version=PHASE14B_RENDERER,
            ),
            observation=observation,
        )
        historical_payload = (
            historical.stage_artifact.payload
            if historical.stage_artifact is not None
            else {}
        )
        phase14b_exact = (
            historical.status is ResultStatus.REJECTED
            and [item.code for item in historical.diagnostics] == ["PYC2910"]
            and [item.diagnostic_id for item in historical.diagnostics]
            == ["diag-33b10f68721e38b3e960"]
            and historical.request_fingerprint is not None
            and historical.request_fingerprint.value
            == "c447d082bb1b12228b0e7fd80ed17c438063f0591ffee2b4b240031fc6d9187f"
            and historical.stage_artifact is not None
            and historical.stage_artifact.kind == "conversion_plan"
            and historical.stage_artifact.schema_version == "0.14.1"
            and historical.stage_artifact.artifact_fingerprint.value
            == "8daf5c369e7ea4e61521bebbae32efccd4ede450e375b09bc44f37ed9d0540c5"
            and historical_payload.get("schema_version") == "conversion-plan/0.14.1"
            and (historical.conversion_summary or {}).get("schema_version")
            == "pycforge.conversion-summary/0.14.1"
            and (historical.decision_trace or {}).get("schema_version")
            == "pycforge.decision-trace/0.14.1"
            and KEYWORD_CALL_TABLE_ID
            not in {
                item.get("table_id")
                for item in historical_payload.get("fact_tables", ())
            }
            and historical.generated_c is None
            and historical.output_fingerprint is None
        )

        passed = all(
            (
                identity_valid,
                constants_valid,
                table_valid,
                independent_valid,
                facts_valid,
                plans_valid,
                lowering_valid,
                observer_valid,
                helper_valid,
                conformance.accepted,
                deterministic,
                fresh_process_valid,
                cross_valid,
                rejections_valid,
                phase14b_exact,
            )
        )
        return {
            "audit": "keyword",
            "passed": passed,
            "active_contracts": active_contracts,
            "active_contract_identities_valid": identity_valid,
            "keyword_rule_id": KEYWORD_CALL_RULE_ID,
            "keyword_rule_version": KEYWORD_CALL_RULE_VERSION,
            "keyword_fact_schema": KEYWORD_CALL_FACT_SCHEMA,
            "keyword_contract_constants_valid": constants_valid,
            "keyword_fact_count": len(fact_values),
            "keyword_fact_table_valid": table_valid,
            "independent_fact_and_plan_validation": independent_valid,
            "independent_validation_message": independent_reason,
            "direct_source_to_parameter_ordinals": direct.get(
                "source_to_parameter_ordinals"
            ),
            "direct_parameter_to_source_ordinals": direct.get(
                "parameter_to_source_ordinals"
            ),
            "reordered_source_to_parameter_ordinals": reordered.get(
                "source_to_parameter_ordinals"
            ),
            "reordered_parameter_to_source_ordinals": reordered.get(
                "parameter_to_source_ordinals"
            ),
            "keyword_facts_valid": facts_valid,
            "keyword_rule_plan_count": len(plans),
            "keyword_rule_plans_valid": plans_valid,
            "source_order_staging_and_formal_reference_permutation_valid": lowering_valid,
            "lowering_evidence": lowering_evidence,
            "observer_evidence_valid": observer_valid,
            "helper_manifest_empty": not payload.get("helper_manifest"),
            "helper_registry_fingerprint": helper_registry.fingerprint,
            "helper_contract_unchanged": helper_valid,
            "allocation": "none",
            "cleanup": "none",
            "runtime_binding_failure": "proved-absent",
            "generated_c_conformance": conformance.accepted,
            "deterministic": deterministic,
            "fresh_process_deterministic": fresh_process_valid,
            "serialized_sha256": fresh_expected["serialized_sha256"],
            "generated_c_sha256": fresh_expected["generated_sha256"],
            "cross_module_valid": cross_valid,
            "cross_module_source_to_parameter_ordinals": cross_fact.get(
                "source_to_parameter_ordinals"
            ),
            "cross_module_parameter_to_source_ordinals": cross_fact.get(
                "parameter_to_source_ordinals"
            ),
            "cross_module_target_module": module_functions.get(
                cross_fact.get("target_function_node_id"), {}
            ).get("module_id"),
            "cross_module_order": (cross.conversion_summary or {})
            .get("module_initialization", {})
            .get("module_order"),
            "cross_module_independent_validation": cross_independent,
            "cross_module_independent_validation_message": cross_reason,
            "cross_module_lowering_evidence": cross_lowering_evidence,
            "rejection_case_count": len(rejections),
            "rejection_codes": rejection_codes,
            "rejections_exact_and_publish_no_c": rejections_valid,
            "phase14b_exact_keyword_rejection": phase14b_exact,
            "python_subprocess_used_for_determinism_only": True,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    except Exception as exc:
        return {
            "audit": "keyword",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
