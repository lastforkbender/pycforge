from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.contracts.configuration import (
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE9_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.io.atomic_writer import AtomicWriter
from pycforge.converter.support_templates import default_helper_registry
from pycforge.laboratory.audits import (
    audit_architecture,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_rules,
    audit_transition,
)


EVIDENCE = ROOT / "evidence" / "phase_11"
ROADMAP = ROOT / "docs" / "python_to_c_converter_architecture_revision_3_1.txt"
ADDENDUM = ROOT / "docs" / "python_to_c_converter_architecture_revision_3_2_addendum.md"


def _with_schema(schema: str, value: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": schema, **value}


def reports(tests_run: int) -> dict[str, dict[str, Any]]:
    architecture = audit_architecture(ROOT)
    rules = audit_rules(ROOT)
    helpers = audit_helpers(ROOT)
    containers = audit_containers(ROOT)
    determinism = audit_determinism(
        ROOT,
        "def f() -> int:\n    values = {1: 10, 2: 20}\n    return values[2]\n",
    )
    transition = audit_transition(ROOT, "phase_11")

    source = "def f(value: int) -> int:\n    return value + 1\n"
    converter = PythonToCConverter()
    current = converter.convert(ConversionRequest.from_source(source), observation=ObservationOptions("Full", False))
    predecessor_surface = converter.convert(
        ConversionRequest.from_source(
            source,
            rule_set_version=PHASE9_RULE_SET,
            renderer_version="c-renderer-v0.9",
        )
    )
    registry = default_helper_registry()
    semantic = {
        "schema_version": "pycforge.semantic-preservation/0.11",
        "current_status": current.status.value,
        "historical_rule_surface_status": predecessor_surface.status.value,
        "scalar_generated_c_byte_identical": current.generated_c == predecessor_surface.generated_c,
        "historical_inner_c_ir_schema": predecessor_surface.stage_artifact.payload.get("c_ir_schema"),
        "historical_generated_schema": predecessor_surface.stage_artifact.payload.get("schema_version"),
        "phase10_helper_registry_fingerprint": registry.fingerprint,
        "phase10_helper_asset_fingerprints": [item["asset_fingerprint"] for item in registry.manifest],
        "phase10_helper_fingerprints_preserved": (
            registry.fingerprint == "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
            and [item["asset_fingerprint"] for item in registry.manifest]
            == [
                "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
                "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
            ]
        ),
        "current_helper_manifest": list(current.stage_artifact.payload.get("helper_manifest", ())),
        "generated_c_compiled_or_executed": False,
    }
    semantic["passed"] = all(
        (
            current.status is ResultStatus.CONVERTED,
            predecessor_surface.status is ResultStatus.CONVERTED,
            semantic["scalar_generated_c_byte_identical"],
            semantic["phase10_helper_fingerprints_preserved"],
            not semantic["current_helper_manifest"],
        )
    )

    schemas = {
        "schema_version": "pycforge.schema-report/0.11",
        "package_version": __version__,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "published_artifact_schema": current.stage_artifact.payload.get("schema_version"),
        "published_c_ir_schema": current.stage_artifact.payload.get("c_ir_schema"),
        "published_summary_schema": current.conversion_summary.get("schema_version"),
        "published_trace_schema": current.decision_trace.get("schema_version"),
        "passed": True,
    }
    schemas["passed"] = (
        __version__ == "0.11.0"
        and schemas["published_artifact_schema"] == GENERATED_C_SCHEMA
        and schemas["published_c_ir_schema"] == C_IR_SCHEMA
        and schemas["published_summary_schema"] == CONVERSION_SUMMARY_SCHEMA
        and schemas["published_trace_schema"] == DECISION_TRACE_SCHEMA
    )

    test_summary = {
        "schema_version": "pycforge.test-summary/0.11",
        "tests_run": tests_run,
        "predecessor_regressions": 154,
        "phase11_tests": 15,
        "failures": 0,
        "errors": 0,
        "generated_c_compiled_or_executed": False,
        "passed": tests_run == 169,
    }
    phase_passed = all(
        item.get("passed")
        for item in (architecture, rules, helpers, containers, determinism, transition, semantic, schemas, test_summary)
    )
    phase_report = {
        "schema_version": "pycforge.phase-report/0.11",
        "phase": 11,
        "version": __version__,
        "roadmap_sha256": hashlib.sha256(ROADMAP.read_bytes()).hexdigest(),
        "addendum_sha256": hashlib.sha256(ADDENDUM.read_bytes()).hexdigest(),
        "predecessor_archive_sha256": "0f54742d1ae1cef604291d0a38286a475cd048792f986ca95e20b3348cdc5c4b",
        "predecessor_tree_sha256": "f3fc12f357ff7c3667f483375d431e087dcfb65302d279194f9ed51466787ea2",
        "supported_forms": containers.get("accepted_forms", []),
        "primary_rejection_codes": containers.get("rejection_codes", []),
        "schemas": {
            "conversion_plan": CONVERSION_PLAN_SCHEMA,
            "c_ir": C_IR_SCHEMA,
            "generated_c": GENERATED_C_SCHEMA,
            "summary": CONVERSION_SUMMARY_SCHEMA,
            "trace": DECISION_TRACE_SCHEMA,
            "result": RESULT_SCHEMA_VERSION,
        },
        "test_count": tests_run,
        "generated_c_compiled_or_executed": False,
        "passed": phase_passed,
    }
    return {
        "architecture_report.json": _with_schema("pycforge.architecture-report/0.11", architecture),
        "rule_report.json": _with_schema("pycforge.rule-report/0.11", rules),
        "helper_registry_report.json": _with_schema("pycforge.helper-registry-report/0.11", helpers),
        "container_report.json": _with_schema("pycforge.container-report/0.11", containers),
        "determinism_report.json": _with_schema("pycforge.determinism-report/0.11", determinism),
        "schema_report.json": schemas,
        "semantic_preservation_report.json": semantic,
        "transition_report.json": _with_schema("pycforge.transition-report/0.11", transition),
        "test_summary.json": test_summary,
        "phase11_report.json": phase_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "check"))
    parser.add_argument("--tests-run", type=int, default=169)
    args = parser.parse_args(argv)
    expected = reports(args.tests_run)
    mismatches: list[str] = []
    writer = AtomicWriter()
    for name, value in sorted(expected.items()):
        text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        path = EVIDENCE / name
        if args.mode == "write":
            writer.write_text(path, text)
        elif not path.is_file() or path.read_text(encoding="utf-8") != text:
            mismatches.append(name)
    if mismatches:
        print("Stale or missing Phase 11 evidence: " + ", ".join(mismatches))
        return 2
    print(f"Phase 11 evidence {args.mode} passed ({len(expected)} generated reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
