"""Strict plain-data mapping for converter results and progress."""

from __future__ import annotations

from typing import Any

from pycforge.converter.contracts.versions import RESULT_SCHEMA_VERSION
from pycforge.converter.core.artifact_io import (
    ArtifactCompatibilityError,
    artifact_from_dict,
    artifact_to_dict,
)
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.enums import ResultStatus, Severity
from pycforge.converter.core.fingerprint import Fingerprint, fingerprint
from pycforge.converter.core.progress import ConversionProgress
from pycforge.converter.core.result import ConversionResult
from pycforge.converter.core.stage_artifact import freeze_value

from ._worker_protocol_json import (
    _exact_fields,
    _list,
    _nonempty_string,
    _nonnegative_integer,
    _object,
    _optional_object,
    _string,
    _string_list,
)
from ._worker_protocol_types import MAX_DIAGNOSTICS, WorkerProtocolError


_FINGERPRINT_FIELDS = frozenset(
    {"domain", "schema_version", "canonicalization_version", "algorithm", "value"}
)
_DIAGNOSTIC_FIELDS = frozenset(
    {
        "diagnostic_id",
        "code",
        "severity",
        "stage",
        "message",
        "effect_on_status",
        "source_span",
        "related_spans",
        "causal_diagnostic_id",
        "target_contract",
        "semantic_policy",
        "rule_id",
        "fact_references",
        "obligation_references",
        "explanation",
        "remediation",
        "approximation_code",
        "semantic_delta",
        "source_module_id",
        "source_logical_name",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "generated_c",
        "diagnostics",
        "request_fingerprint",
        "resource_fingerprint",
        "output_fingerprint",
        "last_completed_stage",
        "stage_order",
        "decision_trace",
        "telemetry",
        "stage_artifact",
        "conversion_summary",
    }
)
_PUBLISHABLE_STATUSES = frozenset(
    {
        ResultStatus.CONVERTED,
        ResultStatus.CONVERTED_WITH_WARNINGS,
        ResultStatus.CONVERTED_WITH_APPROXIMATIONS,
    }
)


def _result_to_data(result: ConversionResult) -> dict[str, object]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": result.status.value,
        "generated_c": result.generated_c,
        "diagnostics": [item.to_dict() for item in result.diagnostics],
        "request_fingerprint": (
            None
            if result.request_fingerprint is None
            else result.request_fingerprint.to_dict()
        ),
        "resource_fingerprint": (
            None
            if result.resource_fingerprint is None
            else result.resource_fingerprint.to_dict()
        ),
        "output_fingerprint": (
            None
            if result.output_fingerprint is None
            else result.output_fingerprint.to_dict()
        ),
        "last_completed_stage": result.last_completed_stage,
        "stage_order": list(result.stage_order),
        "decision_trace": result.decision_trace,
        "telemetry": result.telemetry,
        "stage_artifact": (
            None if result.stage_artifact is None else artifact_to_dict(result.stage_artifact)
        ),
        "conversion_summary": result.conversion_summary,
    }


def _result_from_data(value: object) -> ConversionResult:
    data = _object(value, "conversion result")
    _exact_fields(data, _RESULT_FIELDS, "conversion result")
    if data["schema_version"] != RESULT_SCHEMA_VERSION:
        raise WorkerProtocolError("incompatible conversion result schema")
    try:
        status = ResultStatus(data["status"])
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError("unknown conversion result status") from exc
    generated_c = data["generated_c"]
    if generated_c is not None:
        generated_c = _string(generated_c, "generated C")
    raw_diagnostics = _list(data["diagnostics"], "conversion diagnostics")
    if len(raw_diagnostics) > MAX_DIAGNOSTICS:
        raise WorkerProtocolError("conversion diagnostic count exceeds protocol bounds")
    diagnostics = tuple(_diagnostic_from_data(item) for item in raw_diagnostics)
    request_fingerprint = _fingerprint_from_data(
        data["request_fingerprint"], "request", "conversion-request", False
    )
    resource_fingerprint = _fingerprint_from_data(
        data["resource_fingerprint"], "resource", "resource-policy", False
    )
    output_fingerprint = _fingerprint_from_data(
        data["output_fingerprint"], "output", "generated-output", False
    )
    last_completed_stage = data["last_completed_stage"]
    if last_completed_stage is not None:
        last_completed_stage = _nonempty_string(
            last_completed_stage, "last completed stage"
        )
    stage_order = _string_list(data["stage_order"], "stage order")
    decision_trace = _optional_object(data["decision_trace"], "decision trace")
    telemetry = _optional_object(data["telemetry"], "telemetry")
    conversion_summary = _optional_object(
        data["conversion_summary"], "conversion summary"
    )
    artifact_data = data["stage_artifact"]
    if artifact_data is None:
        artifact = None
    else:
        try:
            artifact = artifact_from_dict(
                _object(artifact_data, "stage artifact")
            )
        except ArtifactCompatibilityError as exc:
            raise WorkerProtocolError("conversion stage artifact is invalid") from exc

    if generated_c is None:
        if output_fingerprint is not None:
            raise WorkerProtocolError(
                "unpublished conversion carries an output fingerprint"
            )
        if status in _PUBLISHABLE_STATUSES:
            raise WorkerProtocolError(
                "publishable conversion result lacks generated C"
            )
    else:
        expected_output = fingerprint("generated-output", generated_c)
        if output_fingerprint != expected_output:
            raise WorkerProtocolError("conversion output fingerprint mismatch")
        if status not in _PUBLISHABLE_STATUSES:
            raise WorkerProtocolError(
                "non-publishable conversion carries generated C"
            )
    if artifact is not None:
        artifact_order = artifact.payload.get("stage_order", ())
        if tuple(artifact_order) != stage_order:
            raise WorkerProtocolError("conversion stage order mismatch")
        if (
            request_fingerprint is None
            or artifact.conversion_id != request_fingerprint.value
        ):
            raise WorkerProtocolError("conversion artifact request identity mismatch")
        artifact_c = artifact.payload.get("generated_c")
        if generated_c is not None and artifact_c != generated_c:
            raise WorkerProtocolError("conversion artifact output mismatch")
    elif stage_order:
        raise WorkerProtocolError("conversion without artifact carries stage order")

    return ConversionResult(
        status,
        generated_c,
        diagnostics,
        request_fingerprint,
        resource_fingerprint,
        output_fingerprint,
        last_completed_stage,
        stage_order,
        freeze_value(decision_trace),
        freeze_value(telemetry),
        artifact,
        freeze_value(conversion_summary),
    )


def _diagnostic_from_data(value: object) -> Diagnostic:
    data = _object(value, "diagnostic")
    _exact_fields(data, _DIAGNOSTIC_FIELDS, "diagnostic")
    try:
        severity = Severity(data["severity"])
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError("diagnostic severity is invalid") from exc
    for key in ("code", "stage", "message"):
        _nonempty_string(data[key], f"diagnostic {key}")
    if not isinstance(data["effect_on_status"], bool):
        raise WorkerProtocolError("diagnostic effect_on_status must be Boolean")
    source_span = data["source_span"]
    if source_span is not None:
        source_span = _object(source_span, "diagnostic source span")
    raw_related = _list(data["related_spans"], "diagnostic related spans")
    related = tuple(_object(item, "diagnostic related span") for item in raw_related)
    optional_strings = {}
    for key in (
        "causal_diagnostic_id",
        "target_contract",
        "semantic_policy",
        "rule_id",
        "explanation",
        "remediation",
        "approximation_code",
        "semantic_delta",
        "source_module_id",
        "source_logical_name",
    ):
        raw = data[key]
        optional_strings[key] = (
            None if raw is None else _string(raw, f"diagnostic {key}")
        )
    diagnostic = Diagnostic(
        code=data["code"],
        severity=severity,
        stage=data["stage"],
        message=data["message"],
        effect_on_status=data["effect_on_status"],
        source_span=source_span,
        related_spans=related,
        causal_diagnostic_id=optional_strings["causal_diagnostic_id"],
        target_contract=optional_strings["target_contract"],
        semantic_policy=optional_strings["semantic_policy"],
        rule_id=optional_strings["rule_id"],
        fact_references=_string_list(
            data["fact_references"], "diagnostic fact references"
        ),
        obligation_references=_string_list(
            data["obligation_references"], "diagnostic obligation references"
        ),
        explanation=optional_strings["explanation"],
        remediation=optional_strings["remediation"],
        approximation_code=optional_strings["approximation_code"],
        semantic_delta=optional_strings["semantic_delta"],
        source_module_id=optional_strings["source_module_id"],
        source_logical_name=optional_strings["source_logical_name"],
    )
    supplied_id = _nonempty_string(data["diagnostic_id"], "diagnostic ID")
    if supplied_id != diagnostic.diagnostic_id:
        raise WorkerProtocolError("diagnostic identity mismatch")
    return diagnostic


def _fingerprint_from_data(
    value: object,
    role: str,
    domain: str,
    required: bool,
) -> Fingerprint | None:
    if value is None:
        if required:
            raise WorkerProtocolError(f"missing {role} fingerprint")
        return None
    data = _object(value, f"{role} fingerprint")
    _exact_fields(data, _FINGERPRINT_FIELDS, f"{role} fingerprint")
    if not all(isinstance(item, str) for item in data.values()):
        raise WorkerProtocolError(f"{role} fingerprint fields must be strings")
    result = Fingerprint(**data)
    if (
        result.domain != domain
        or result.schema_version != "0.1"
        or result.canonicalization_version != "canonical-json-v1"
        or result.algorithm != "sha256"
        or len(result.value) != 64
        or any(character not in "0123456789abcdef" for character in result.value)
    ):
        raise WorkerProtocolError(f"{role} fingerprint metadata is incompatible")
    return result


def _progress_from_data(value: object) -> ConversionProgress:
    data = _object(value, "conversion progress")
    _exact_fields(
        data,
        {"state", "stage_id", "completed_stages", "total_stages"},
        "conversion progress",
    )
    state = _nonempty_string(data["state"], "conversion progress state")
    stage_id = data["stage_id"]
    if stage_id is not None:
        stage_id = _nonempty_string(stage_id, "conversion progress stage")
    completed = _nonnegative_integer(
        data["completed_stages"], "completed conversion stages"
    )
    total = _nonnegative_integer(data["total_stages"], "total conversion stages")
    try:
        return ConversionProgress(state, stage_id, completed, total)
    except ValueError as exc:
        raise WorkerProtocolError("conversion progress is inconsistent") from exc


def _mappings_from_data(value: object) -> tuple[dict[str, Any], ...]:
    items = _list(value, "source/output mappings")
    return tuple(
        freeze_value(_object(item, "source/output mapping")) for item in items
    )


def _validate_result_mappings(
    result: ConversionResult,
    mappings: tuple[dict[str, Any], ...],
) -> None:
    artifact = result.stage_artifact
    if artifact is None:
        if mappings:
            raise WorkerProtocolError("conversion without artifact carries mappings")
        return
    raw = artifact.payload.get("source_output_mappings", ())
    if not isinstance(raw, (tuple, list)) or tuple(raw) != mappings:
        raise WorkerProtocolError("terminal source/output mappings mismatch")
