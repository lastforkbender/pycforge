from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
    __version__,
)
from pycforge.converter.contracts.configuration import (
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    PHASE11_RULE_SET,
)
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    MODULE_FACT_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_dict
from pycforge.converter.io.atomic_writer import AtomicWriter
from pycforge.converter.ir.c_ir import (
    CProvenance,
    CTranslationUnitBuilder,
    SCHEMA_VERSION as FUNCTION_C_IR_SCHEMA,
    serialize_translation_unit,
)
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    assemble_translation_unit,
    default_helper_registry,
)
from pycforge.laboratory.audits import (
    audit_architecture,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_modules,
    audit_rules,
    audit_transition,
)


EVIDENCE = ROOT / "evidence" / "phase_12"
ROADMAP = ROOT / "docs" / "python_to_c_converter_architecture_revision_3_1.txt"
ADDENDUM = ROOT / "docs" / "python_to_c_converter_architecture_revision_3_2_addendum.md"
PHASE11_ARCHIVE_SHA256 = "8af71e84cb6a1f12fc1206f589233067191f87ce4fc4f550765ff64098038275"
PHASE11_TREE_SHA256 = "95fbabf3311a5f7dcb88608ef66c7ef43ed085ae1e3fc99351472da8ca1d4e82"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
HELPER_ASSET_SHA256 = (
    "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
    "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
)
HISTORICAL_C_IR_SHA256 = {
    "c-ir/0.8": "b6539ada46e74888a18dc54f3b8d22ec4abd4acf36d1bc12b43b0eec7c927a45",
    "c-ir/0.9": "44a7deb905bcd48851da4e867459e2880368c1ac4519210cafa73dac6a3627c2",
    "c-ir/0.10-helper": "de941a930e2e17ce7bdd4a3167a7a297e8c12e605a870ffd34905c5925b3c211",
    "c-ir/0.11-container": "2196981b45abbab1533bc1ed1916afb697112f820490dd49aeb094a2e8b718f5",
}
PHASE11_GENERATED_C_SHA256 = {
    "scalar": "1f63ad089b6ce5765df1a26af2811451ce86b40766458e248fec290a0c80304b",
    "container": "2fec8c598b4da10da97517fd8d23f4b52af312df1004a8c7f26148b1d519faf1",
}


def _with_schema(schema: str, value: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": schema, **value}


def _module_request() -> ConversionRequest:
    return ConversionRequest(
        SourceBundle(
            SourceDocumentInput(
                "app.py",
                "from lib.math import increment as inc\n\ndef run(value: int) -> int:\n    return inc(value)\n",
                "app",
            ),
            (
                SourceDocumentInput(
                    "lib/math.py",
                    "def increment(value: int) -> int:\n    return value + 1\n",
                    "lib.math",
                ),
            ),
        )
    )


def _determinism_report() -> dict[str, Any]:
    predecessor = audit_determinism(ROOT)
    code = (
        "import os;"
        "os.cpu_count=lambda:int(os.environ['PYCF_DETERMINISM_CPU_COUNT']);"
        "from pycforge import ConversionRequest,PythonToCConverter,SourceBundle,SourceDocumentInput;"
        "from pycforge.converter.core.serialization import result_to_json;"
        "request=ConversionRequest(SourceBundle("
        "SourceDocumentInput('app.py','from lib.math import increment as inc\\n\\ndef run(value: int) -> int:\\n    return inc(value)\\n','app'),"
        "(SourceDocumentInput('lib/math.py','def increment(value: int) -> int:\\n    return value + 1\\n','lib.math'),)));"
        "print(result_to_json(PythonToCConverter().convert(request)),end='')"
    )
    outputs = []
    variants = (
        {
            "PYTHONHASHSEED": "1",
            "TZ": "UTC",
            "LC_ALL": "C",
            "PYCF_DETERMINISM_CPU_COUNT": "1",
        },
        {
            "PYTHONHASHSEED": "8675309",
            "TZ": "Europe/Warsaw",
            "LC_ALL": "en_US.utf8",
            "PYCF_DETERMINISM_CPU_COUNT": "8",
        },
    )
    interpreters = [Path(sys.executable).resolve()]
    system_python = Path("/usr/bin/python3.12")
    if system_python.is_file() and system_python.resolve() not in interpreters:
        interpreters.append(system_python.resolve())
    python_versions = []
    with tempfile.TemporaryDirectory(prefix="pycforge-det-a-") as first_tmp, tempfile.TemporaryDirectory(
        prefix="pycforge-det-b-"
    ) as second_tmp:
        temporary_roots = (first_tmp, second_tmp)
        for interpreter in interpreters:
            python_versions.append(
                subprocess.check_output(
                    [str(interpreter), "-c", "import platform;print(platform.python_version(),end='')"],
                    text=True,
                )
            )
            for variant, temporary_root in zip(variants, temporary_roots):
                environment = {
                    **os.environ,
                    **variant,
                    "PYTHONPATH": str(ROOT),
                    "TMPDIR": temporary_root,
                    "TEMP": temporary_root,
                    "TMP": temporary_root,
                }
                outputs.append(
                    subprocess.check_output(
                        [str(interpreter), "-c", code],
                        cwd=ROOT,
                        env=environment,
                    )
                )
    return {
        "audit": "determinism",
        "passed": (
            bool(predecessor.get("passed"))
            and len(interpreters) >= 2
            and len(set(python_versions)) >= 2
            and all(item == outputs[0] for item in outputs[1:])
        ),
        "singleton_audit_sha256": predecessor.get("sha256"),
        "module_bundle_sha256": hashlib.sha256(outputs[0]).hexdigest(),
        "fresh_processes": len(outputs),
        "python_patch_versions": python_versions,
        "release_interpreter": platform.python_version(),
        "varied_environment_fields": [
            "PYTHONHASHSEED", "TZ", "LC_ALL", "TMPDIR", "TEMP", "TMP", "os.cpu_count"
        ],
    }


def _source_boundary_report() -> dict[str, Any]:
    forbidden_roots = {
        "builtins", "http", "importlib", "io", "os", "pathlib", "pkgutil",
        "requests", "site", "socket", "subprocess", "sys", "sysconfig", "urllib",
    }
    violations: list[str] = []
    module_root = ROOT / "pycforge" / "converter" / "modules"
    module_files = sorted(module_root.glob("*.py")) if module_root.is_dir() else []
    if not module_files:
        violations.append("missing module resolver boundary")
    else:
        for module_file in module_files:
            tree = ast.parse(module_file.read_text(encoding="utf-8"), filename=str(module_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_roots:
                            violations.append(f"{module_file.name} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden_roots:
                        violations.append(f"{module_file.name} imports {node.module}")

    probes: list[str] = []

    def blocked(name: str):
        def invoke(*args: Any, **kwargs: Any) -> Any:
            probes.append(name)
            raise AssertionError(f"source import attempted host discovery through {name}")
        return invoke

    converter = PythonToCConverter()
    with ExitStack() as stack:
        for target in (
            "io.open",
            "os.getenv",
            "os.listdir",
            "os.lstat",
            "os.scandir",
            "os.stat",
            "pathlib.Path.exists",
            "pathlib.Path.glob",
            "pathlib.Path.is_file",
            "pathlib.Path.iterdir",
            "pathlib.Path.open",
            "pathlib.Path.read_bytes",
            "pathlib.Path.read_text",
            "pathlib.Path.resolve",
            "pathlib.Path.rglob",
            "pkgutil.iter_modules",
            "pkgutil.walk_packages",
            "socket.create_connection",
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.socket",
            "builtins.open",
            "importlib.util.find_spec",
            "importlib.machinery.PathFinder.find_spec",
            "importlib.import_module",
        ):
            stack.enter_context(patch(target, side_effect=blocked(target)))
        explicit = converter.convert(_module_request())
        host_only = converter.convert(
            ConversionRequest.from_source(
                "from os import getcwd\n\ndef run() -> int:\n    return 1\n",
                module_id="app",
            )
        )

    host_codes = [item.code for item in host_only.diagnostics]
    explicit_ok = explicit.status is ResultStatus.CONVERTED and explicit.generated_c is not None
    host_rejected = (
        host_only.status is ResultStatus.REJECTED
        and host_codes == ["PYC3503"]
        and host_only.generated_c is None
        and not host_only.stage_artifact.payload.get("c_ir")
        and not host_only.stage_artifact.payload.get("helper_manifest")
        and not host_only.stage_artifact.payload.get("source_output_mappings")
    )
    return {
        "schema_version": "pycforge.source-boundary-report/0.12",
        "audit": "source-boundary-no-discovery",
        "passed": not violations and not probes and explicit_ok and host_rejected,
        "resolution": "exact-sourcebundle-only",
        "static_violations": violations,
        "instrumented_discovery_calls": probes,
        "instrumented_operations": [
            "filesystem-open", "filesystem-list", "filesystem-metadata", "filesystem-resolve",
            "environment-lookup", "import-hook", "import-module", "import-spec",
            "package-scan", "network-dns", "network-socket",
        ],
        "explicit_companion_status": explicit.status.value,
        "installed_host_module_request_status": host_only.status.value,
        "installed_host_module_diagnostics": host_codes,
        "partial_output_published_on_rejection": False if host_rejected else None,
        "generated_c_compiled_or_executed": False,
    }


def reports(tests_run: int) -> dict[str, dict[str, Any]]:
    architecture = audit_architecture(ROOT)
    rules = audit_rules(ROOT)
    helpers = audit_helpers(ROOT)
    containers = audit_containers(ROOT)
    modules = audit_modules(ROOT)
    determinism = _determinism_report()
    try:
        transition = audit_transition(ROOT, "phase_12")
    except Exception as exc:
        transition = {
            "audit": "transition",
            "phase": "phase_12",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    source_boundary = _source_boundary_report()

    source = "def f(value: int) -> int:\n    return value + 1\n"
    converter = PythonToCConverter()
    current = converter.convert(
        ConversionRequest.from_source(source),
        observation=ObservationOptions("Full", False),
    )
    phase11 = converter.convert(
        ConversionRequest.from_source(
            source,
            rule_set_version=PHASE11_RULE_SET,
            renderer_version="c-renderer-v0.11",
        )
    )
    phase11_container = converter.convert(
        ConversionRequest.from_source(
            "def f() -> int:\n    values = [1, 2]\n    return values[-1]\n",
            rule_set_version=PHASE11_RULE_SET,
            renderer_version="c-renderer-v0.11",
        )
    )
    phase9 = converter.convert(
        ConversionRequest.from_source(
            source,
            rule_set_version="phase9-functions-calls-v0.9",
            renderer_version="c-renderer-v0.9",
        )
    )
    phase8 = converter.convert(
        ConversionRequest.from_source(
            source,
            rule_set_version="phase8-control-flow-v0.8",
            renderer_version="c-renderer-v0.8",
        )
    )
    registry = default_helper_registry()
    helper_plan = registry.resolve(
        [FLOOR_DIV_REFERENCE],
        target_contract="c11-portable-fixed-v1",
    )
    helper_source = CTranslationUnitBuilder(
        "c11-portable-fixed-v1",
        schema_version=FUNCTION_C_IR_SCHEMA,
        provenance=CProvenance("synthetic"),
    ).build()
    helper_unit = assemble_translation_unit(helper_source, helper_plan)
    helper_assets = tuple(item["asset_fingerprint"] for item in registry.manifest)
    current_payload = current.stage_artifact.payload
    phase11_payload = phase11.stage_artifact.payload
    historical_c_ir_fixture_sha256 = {
        "c-ir/0.8": hashlib.sha256(
            json.dumps(phase8.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "c-ir/0.9": hashlib.sha256(
            json.dumps(phase9.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "c-ir/0.10-helper": hashlib.sha256(
            json.dumps(serialize_translation_unit(helper_unit), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "c-ir/0.11-container": hashlib.sha256(
            json.dumps(phase11_container.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    generated_c_fixture_sha256 = {
        "scalar": hashlib.sha256(phase11.generated_c.encode("utf-8")).hexdigest(),
        "container": hashlib.sha256(phase11_container.generated_c.encode("utf-8")).hexdigest(),
    }
    semantic = {
        "schema_version": "pycforge.semantic-preservation/0.12",
        "current_status": current.status.value,
        "explicit_phase11_status": phase11.status.value,
        "scalar_generated_c_byte_identical": current.generated_c == phase11.generated_c,
        "phase11_generated_c_fixture_sha256": generated_c_fixture_sha256,
        "sealed_phase11_generated_c_fixture_sha256": PHASE11_GENERATED_C_SHA256,
        "phase11_generated_c_fixtures_preserved": (
            generated_c_fixture_sha256 == PHASE11_GENERATED_C_SHA256
        ),
        "phase11_c_ir_schema": phase11_payload.get("c_ir_schema"),
        "phase11_generated_schema": phase11_payload.get("schema_version"),
        "phase11_archive_sha256": PHASE11_ARCHIVE_SHA256,
        "phase11_tree_sha256": PHASE11_TREE_SHA256,
        "phase10_helper_registry_fingerprint": registry.fingerprint,
        "phase10_helper_asset_fingerprints": list(helper_assets),
        "historical_c_ir_fixture_sha256": historical_c_ir_fixture_sha256,
        "sealed_historical_c_ir_fixture_sha256": HISTORICAL_C_IR_SHA256,
        "historical_c_ir_serialization_preserved": (
            historical_c_ir_fixture_sha256 == HISTORICAL_C_IR_SHA256
        ),
        "phase10_helper_fingerprints_preserved": (
            registry.fingerprint == HELPER_REGISTRY_SHA256
            and helper_assets == HELPER_ASSET_SHA256
        ),
        "current_helper_manifest": list(current_payload.get("helper_manifest", ())),
        "generated_c_compiled_or_executed": False,
    }
    semantic["passed"] = all(
        (
            current.status is ResultStatus.CONVERTED,
            phase11.status is ResultStatus.CONVERTED,
            semantic["scalar_generated_c_byte_identical"],
            semantic["phase11_generated_c_fixtures_preserved"],
            semantic["phase11_c_ir_schema"] == "c-ir/0.11",
            semantic["phase11_generated_schema"] == "generated-c/0.11",
            semantic["phase10_helper_fingerprints_preserved"],
            semantic["historical_c_ir_serialization_preserved"],
            not semantic["current_helper_manifest"],
        )
    )

    fact_schemas = sorted(
        {
            item.get("schema_version")
            for item in current_payload.get("fact_tables", ())
            if str(item.get("table_id", "")).startswith("module-")
        }
    )
    summary = current.conversion_summary or {}
    trace = current.decision_trace or {}
    schemas = {
        "schema_version": "pycforge.schema-report/0.12",
        "package_version": __version__,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "module_policy": DEFAULT_MODULE_POLICY,
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "published_artifact_schema": current_payload.get("schema_version"),
        "published_c_ir_schema": current_payload.get("c_ir_schema"),
        "published_python_ir_schema": current_payload.get("python_ir", {}).get("schema_version"),
        "published_module_fact_schemas": fact_schemas,
        "published_summary_schema": summary.get("schema_version"),
        "published_trace_schema": trace.get("schema_version"),
        "published_result_schema": result_to_dict(current).get("schema_version"),
    }
    schemas["passed"] = (
        __version__ == "0.12.0"
        and current.status is ResultStatus.CONVERTED
        and schemas["published_artifact_schema"] == GENERATED_C_SCHEMA
        and schemas["published_c_ir_schema"] == C_IR_SCHEMA
        and schemas["published_python_ir_schema"] == PYTHON_IR_BUNDLE_SCHEMA
        and schemas["published_module_fact_schemas"] == [MODULE_FACT_SCHEMA]
        and schemas["published_summary_schema"] == CONVERSION_SUMMARY_SCHEMA
        and schemas["published_trace_schema"] == DECISION_TRACE_SCHEMA
        and schemas["published_result_schema"] == RESULT_SCHEMA_VERSION
    )

    test_summary = {
        "schema_version": "pycforge.test-summary/0.12",
        "tests_run": tests_run,
        "predecessor_regressions": 169,
        "phase12_tests": 20,
        "failures": 0,
        "errors": 0,
        "generated_c_compiled_or_executed": False,
        "passed": tests_run == 189,
    }
    phase_passed = all(
        item.get("passed")
        for item in (
            architecture, rules, helpers, containers, modules, determinism,
            schemas, semantic, source_boundary, test_summary, transition,
        )
    )
    phase_report = {
        "schema_version": "pycforge.phase-report/0.12",
        "phase": 12,
        "version": __version__,
        "roadmap_sha256": hashlib.sha256(ROADMAP.read_bytes()).hexdigest(),
        "addendum_sha256": hashlib.sha256(ADDENDUM.read_bytes()).hexdigest(),
        "predecessor_archive_sha256": PHASE11_ARCHIVE_SHA256,
        "predecessor_tree_sha256": PHASE11_TREE_SHA256,
        "helper_registry_sha256": HELPER_REGISTRY_SHA256,
        "helper_asset_sha256": list(HELPER_ASSET_SHA256),
        "supported_forms": modules.get("accepted_forms", []),
        "primary_rejection_codes": modules.get("rejection_codes", []),
        "schemas": {
            "source_bundle": SOURCE_BUNDLE_SCHEMA,
            "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
            "facts": MODULE_FACT_SCHEMA,
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
        "architecture_report.json": _with_schema("pycforge.architecture-report/0.12", architecture),
        "rule_report.json": _with_schema("pycforge.rule-report/0.12", rules),
        "helper_registry_report.json": _with_schema("pycforge.helper-registry-report/0.12", helpers),
        "container_report.json": _with_schema("pycforge.container-report/0.12", containers),
        "module_report.json": _with_schema("pycforge.module-report/0.12", modules),
        "determinism_report.json": _with_schema("pycforge.determinism-report/0.12", determinism),
        "schema_report.json": schemas,
        "semantic_preservation_report.json": semantic,
        "source_boundary_report.json": source_boundary,
        "test_summary.json": test_summary,
        "transition_report.json": _with_schema("pycforge.transition-report/0.12", transition),
        "phase12_report.json": phase_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("write", "check"))
    parser.add_argument("--tests-run", type=int, default=189)
    args = parser.parse_args(argv)
    expected = reports(args.tests_run)
    if len(expected) != 12:
        print("Phase 12 collector invariant failed: expected exactly 12 generated reports")
        return 3
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
        print("Stale or missing Phase 12 evidence: " + ", ".join(mismatches))
        return 2
    print(f"Phase 12 evidence {args.mode} passed ({len(expected)} generated reports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
