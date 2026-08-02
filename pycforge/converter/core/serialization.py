from __future__ import annotations
import json
from typing import Any
from .result import ConversionResult
from pycforge.converter.contracts.versions import RESULT_SCHEMA_VERSION

def result_to_dict(result: ConversionResult, *, include_observers: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {"schema_version": RESULT_SCHEMA_VERSION, **result.semantic_dict()}
    if include_observers:
        data["decision_trace"] = result.decision_trace
        data["telemetry"] = result.telemetry
    return data

def result_to_json(result: ConversionResult, *, include_observers: bool = True) -> str:
    return json.dumps(result_to_dict(result, include_observers=include_observers), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"

def result_to_text(result: ConversionResult) -> str:
    lines = [f"status: {result.status.value}"]
    lines.append(f"last_completed_stage: {result.last_completed_stage or '-'}")
    lines.append("stage_order: " + (", ".join(result.stage_order) if result.stage_order else "-"))
    if result.request_fingerprint:
        lines.append(f"request_fingerprint: {result.request_fingerprint.value}")
    if result.output_fingerprint:
        lines.append(f"output_fingerprint: {result.output_fingerprint.value}")
    lines.append(f"generated_c: {'available' if result.generated_c is not None else 'not-published'}")
    lines.append(f"diagnostics: {len(result.diagnostics)}")
    if result.conversion_summary is not None:
        lines.append(f"functions: {len(result.conversion_summary.get('functions',()))}")
        lines.append(f"calls: {len(result.conversion_summary.get('calls',()))}")
        lines.append(f"containers: {len(result.conversion_summary.get('containers',()))}")
        lines.append(f"records: {len(result.conversion_summary.get('records',()))}")
        lines.append(f"helpers: {len(result.conversion_summary.get('helpers',()))}")
        lines.append(f"rule_set: {result.conversion_summary.get('rule_set_version')}")
    for item in result.diagnostics:
        lines.append(f"  {item.code} [{item.severity.value}] {item.stage}: {item.message}")
    return "\n".join(lines) + "\n"
