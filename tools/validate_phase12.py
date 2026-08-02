from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


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
from pycforge.converter.ir.c_ir import (
    CProvenance,
    CTranslationUnitBuilder,
    HELPER_SCHEMA_VERSION,
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


FINGERPRINT = Path("transition/phase_12/baseline_fingerprint.json")
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
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
REPORTS = (
    "phase12_report.json",
    "architecture_report.json",
    "rule_report.json",
    "helper_registry_report.json",
    "container_report.json",
    "module_report.json",
    "determinism_report.json",
    "schema_report.json",
    "semantic_preservation_report.json",
    "source_boundary_report.json",
    "test_summary.json",
    "transition_report.json",
)
REQUIRED_RELEASE_FILES = {
    "PyCForge_Phase_12_v0_12_0_Project_Handoff.txt",
    "pycforge/converter/modules/analysis.py",
    "pycforge/converter/modules/lowering.py",
    "tests/test_phase12.py",
    "tools/collect_phase12_evidence.py",
    "tools/validate_phase12.py",
    *(f"evidence/phase_12/{name}" for name in REPORTS),
    "evidence/phase_12/package_report.json",
}


def included_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative == FINGERPRINT:
            continue
        if (
            "__pycache__" in path.parts
            or ".pytest_cache" in path.parts
            or "build" in path.parts
            or "dist" in path.parts
            or path.name.endswith(".pyc")
        ):
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(ROOT).as_posix())


def tree_hash() -> str:
    digest = hashlib.sha256()
    for path in included_files():
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def fail(message: str, code: int) -> int:
    print(message)
    return code


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


def _kind_dicts(value: Any, kinds: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("kind") in kinds:
            result.append(value)
        for item in value.values():
            result.extend(_kind_dicts(item, kinds))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_kind_dicts(item, kinds))
    return result


def _predecessor_archive(argument: str | None) -> Path | None:
    if argument:
        return Path(argument).resolve()
    name = "pycforge_phase_11_v0_11_0.tar.gz"
    for candidate in (ROOT / name, ROOT.parent / name, ROOT.parents[1] / name):
        if candidate.is_file():
            return candidate
    return None


def _wheel_file(argument: str | None, expected_name: str) -> Path | None:
    if argument:
        return Path(argument).resolve()
    for candidate in (
        ROOT / "dist" / expected_name,
        ROOT / expected_name,
        ROOT.parent / expected_name,
        ROOT.parents[1] / "release" / expected_name,
    ):
        if candidate.is_file():
            return candidate
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor-archive")
    parser.add_argument("--wheel")
    args = parser.parse_args(argv)

    manifest_path = ROOT / "transition/phase_12/manifest.json"
    fingerprint_path = ROOT / FINGERPRINT
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fingerprint_record = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    if manifest.get("phase") != 12 or manifest.get("version") != "0.12.0":
        return fail("Phase 12 manifest identity mismatch", 2)
    if manifest.get("status") != "promoted":
        return fail("Phase 12 manifest is not promoted", 2)
    if (
        fingerprint_record.get("algorithm") != "sha256"
        or fingerprint_record.get("domain") != "pycforge-phase-12-tree"
        or fingerprint_record.get("status") != "promoted"
        or fingerprint_record.get("predecessor_tree_sha256") != PHASE11_TREE_SHA256
        or not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint_record.get("value", "")))
    ):
        return fail("Phase 12 baseline fingerprint record is not promoted or complete", 2)
    current_state = (ROOT / "CURRENT_STATE.md").read_text(encoding="utf-8")
    if "Current release: `0.12.0` / Phase 12" not in current_state or "Release status: promoted" not in current_state:
        return fail("CURRENT_STATE.md does not identify the promoted Phase 12 release", 2)
    if __version__ != "0.12.0" or 'version = "0.12.0"' not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        return fail("Phase 12 package identity mismatch", 3)
    if (
        manifest.get("required_tests") != 189
        or manifest.get("predecessor_regression_tests") != 169
        or manifest.get("phase_tests") != 20
    ):
        return fail("Phase 12 test-count contract mismatch", 4)

    declared_files = set(manifest.get("required_contract_files", ())) | set(manifest.get("required_files", ()))
    required_files = declared_files | REQUIRED_RELEASE_FILES
    missing = sorted(name for name in required_files if not (ROOT / name).is_file())
    if missing:
        return fail("Missing Phase 12 files: " + ", ".join(missing), 5)

    if (
        manifest.get("predecessor_archive_sha256") != PHASE11_ARCHIVE_SHA256
        or manifest.get("predecessor_tree_sha256") != PHASE11_TREE_SHA256
    ):
        return fail("Sealed Phase 11 rollback identity mismatch", 6)
    phase11_record = json.loads((ROOT / "transition/phase_11/baseline_fingerprint.json").read_text(encoding="utf-8"))
    if phase11_record.get("value") != PHASE11_TREE_SHA256:
        return fail("Recorded sealed Phase 11 tree fingerprint changed", 6)
    predecessor = _predecessor_archive(args.predecessor_archive)
    if args.predecessor_archive and (predecessor is None or not predecessor.is_file()):
        return fail("Requested predecessor archive is absent", 6)
    if predecessor is not None and hashlib.sha256(predecessor.read_bytes()).hexdigest() != PHASE11_ARCHIVE_SHA256:
        return fail("Sealed Phase 11 archive hash mismatch", 6)

    roadmap = ROOT / "docs/python_to_c_converter_architecture_revision_3_1.txt"
    addendum = ROOT / "docs/python_to_c_converter_architecture_revision_3_2_addendum.md"
    if hashlib.sha256(roadmap.read_bytes()).hexdigest() != ROADMAP_SHA256:
        return fail("Architecture Revision 3.1 hash mismatch", 7)
    if hashlib.sha256(addendum.read_bytes()).hexdigest() != ADDENDUM_SHA256:
        return fail("Architecture Revision 3.2 addendum hash mismatch", 7)

    expected_schemas = {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "fact_tables": MODULE_FACT_SCHEMA,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "module_policy": DEFAULT_MODULE_POLICY,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "target_contract": "c11-portable-fixed-v1",
    }
    manifest_schemas = manifest.get("schemas", {})
    if any(manifest_schemas.get(key) != value for key, value in expected_schemas.items()):
        return fail("Phase 12 manifest schema/configuration contract mismatch", 8)
    if manifest.get("document_limit") != 64 or manifest.get("import_item_limit") != 4096:
        return fail("Phase 12 resource ceiling contract mismatch", 8)
    expected_diagnostics = [f"PYC35{ordinal:02d}" for ordinal in range(1, 11)]
    if manifest.get("required_primary_diagnostics") != expected_diagnostics:
        return fail("Phase 12 primary diagnostic contract mismatch", 8)
    contract_text = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8").lower()
        for relative in (
            "specifications/source_bundle.md",
            "specifications/module_bundles.md",
            "transition/phase_12/module_bundle_decisions.md",
        )
    )
    for term in (
        "sourcebundle", "exact", "dependency-first", "cycle",
        "external linkage", "single-translation-unit", "no source-controlled include",
        "filesystem", "environment", "network", "installed", "pyc3510",
    ):
        if term not in contract_text:
            return fail(f"Phase 12 module contract omits {term}", 8)

    converter = PythonToCConverter()
    scalar = "def f(value: int) -> int:\n    return value + 1\n"
    current = converter.convert(
        ConversionRequest.from_source(scalar),
        observation=ObservationOptions("Full", False),
    )
    phase11 = converter.convert(
        ConversionRequest.from_source(
            scalar,
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
            scalar,
            rule_set_version="phase9-functions-calls-v0.9",
            renderer_version="c-renderer-v0.9",
        )
    )
    phase8 = converter.convert(
        ConversionRequest.from_source(
            scalar,
            rule_set_version="phase8-control-flow-v0.8",
            renderer_version="c-renderer-v0.8",
        )
    )
    historical = (phase11, phase11_container, phase9, phase8)
    if current.status is not ResultStatus.CONVERTED or any(item.status is not ResultStatus.CONVERTED for item in historical):
        return fail("Current or historical compatibility conversion failed", 9)
    if current.generated_c != phase11.generated_c:
        return fail("Phase 12 changed explicit Phase 11 singleton generated-C bytes", 9)
    generated_fixture_hashes = {
        "scalar": hashlib.sha256(phase11.generated_c.encode("utf-8")).hexdigest(),
        "container": hashlib.sha256(phase11_container.generated_c.encode("utf-8")).hexdigest(),
    }
    if generated_fixture_hashes != PHASE11_GENERATED_C_SHA256:
        return fail("Sealed Phase 11 generated-C fixture bytes changed", 9)

    current_payload = current.stage_artifact.payload
    if (
        current.stage_artifact.schema_version != "0.12"
        or current_payload.get("schema_version") != GENERATED_C_SCHEMA
        or current_payload.get("c_ir_schema") != C_IR_SCHEMA
        or current_payload.get("rule_set_version") != DEFAULT_RULE_SET
        or current_payload.get("helper_manifest")
        or current.conversion_summary.get("schema_version") != CONVERSION_SUMMARY_SCHEMA
        or current.decision_trace.get("schema_version") != DECISION_TRACE_SCHEMA
        or result_to_dict(current).get("schema_version") != RESULT_SCHEMA_VERSION
    ):
        return fail("Phase 12 schema or empty-helper identity mismatch", 10)
    expected_historical = (
        (phase11, "0.11", "c-ir/0.11", "generated-c/0.11"),
        (phase11_container, "0.11", "c-ir/0.11", "generated-c/0.11"),
        (phase9, "0.10", "c-ir/0.9", "generated-c/0.10"),
        (phase8, "0.6", "c-ir/0.8", "generated-c/0.8"),
    )
    for result, artifact_schema, c_ir_schema, generated_schema in expected_historical:
        payload = result.stage_artifact.payload
        if (
            result.stage_artifact.schema_version != artifact_schema
            or payload.get("c_ir_schema") != c_ir_schema
            or payload.get("schema_version") != generated_schema
        ):
            return fail(f"Historical schema behavior changed for {c_ir_schema}", 10)
    current_cir_text = json.dumps(current_payload.get("c_ir"), sort_keys=True)
    phase11_cir_text = json.dumps(phase11_container.stage_artifact.payload.get("c_ir"), sort_keys=True)
    if "array_extents" not in current_cir_text or "array_extents" not in phase11_cir_text:
        return fail("C IR 0.11/0.12 fixed-array serialization is incomplete", 10)
    for result in (phase9, phase8):
        serialized = json.dumps(result.stage_artifact.payload.get("c_ir"), sort_keys=True)
        if "array_extents" in serialized or "object_const" in serialized:
            return fail("C IR 0.8-0.10 historical serialization was repurposed", 10)
    historical_fixture_hashes = {
        "c-ir/0.8": hashlib.sha256(
            json.dumps(phase8.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "c-ir/0.9": hashlib.sha256(
            json.dumps(phase9.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "c-ir/0.11-container": hashlib.sha256(
            json.dumps(phase11_container.stage_artifact.payload["c_ir"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    if any(
        historical_fixture_hashes[key] != HISTORICAL_C_IR_SHA256[key]
        for key in historical_fixture_hashes
    ):
        return fail("Historical C IR fixture serialization changed", 10)

    registry = default_helper_registry()
    helper_assets = tuple(item["asset_fingerprint"] for item in registry.manifest)
    if registry.fingerprint != HELPER_REGISTRY_SHA256 or helper_assets != HELPER_ASSET_SHA256:
        return fail("Phase 10 StableInternal helper fingerprints changed", 11)
    helper_plan = registry.resolve([FLOOR_DIV_REFERENCE], target_contract="c11-portable-fixed-v1")
    helper_source = CTranslationUnitBuilder(
        "c11-portable-fixed-v1",
        schema_version=FUNCTION_C_IR_SCHEMA,
        provenance=CProvenance("synthetic"),
    ).build()
    helper_unit = assemble_translation_unit(helper_source, helper_plan)
    helper_data = json.dumps(serialize_translation_unit(helper_unit), sort_keys=True)
    if helper_unit.schema_version != HELPER_SCHEMA_VERSION or "array_extents" in helper_data or "object_const" in helper_data:
        return fail("C IR 0.10 helper serialization compatibility changed", 11)
    helper_fixture_hash = hashlib.sha256(
        json.dumps(
            serialize_translation_unit(helper_unit),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if helper_fixture_hash != HISTORICAL_C_IR_SHA256["c-ir/0.10-helper"]:
        return fail("C IR 0.10 helper fixture serialization changed", 11)

    module_result = converter.convert(_module_request(), observation=ObservationOptions("Full", False))
    if module_result.status is not ResultStatus.CONVERTED or not module_result.generated_c:
        return fail("Phase 12 module vertical slice failed", 12)
    module_payload = module_result.stage_artifact.payload
    c_ir = module_payload.get("c_ir", {})
    tables = {item.get("table_id"): item for item in module_payload.get("fact_tables", ())}
    required_tables = {
        "module-identity-facts", "module-import-facts", "module-function-facts",
        "module-initialization-facts", "module-namespace-facts", "module-source-facts",
    }
    if not required_tables.issubset(tables):
        return fail("Phase 12 module fact closure is incomplete", 12)
    if any(tables[name].get("schema_version") != MODULE_FACT_SCHEMA for name in required_tables):
        return fail("Phase 12 module fact schema mismatch", 12)
    declarations = c_ir.get("declarations", ())
    declaration_kinds = [item.get("kind") for item in declarations]
    prototypes = [item for item in declarations if item.get("kind") == "CFunctionPrototype"]
    definitions = [item for item in declarations if item.get("kind") == "CFunctionDefinition"]
    source_functions = [
        item for item in prototypes + definitions
        if item.get("provenance", {}).get("origin_kind") != "support-template"
    ]
    c_ir_manifest = c_ir.get("module_manifest", ())
    c_ir_manifest_by_id = {item.get("module_id"): item for item in c_ir_manifest}
    prototype_bindings = [item.get("identifier", {}).get("binding_id") for item in prototypes]
    definition_bindings = [item.get("identifier", {}).get("binding_id") for item in definitions]
    initialization_records = tables["module-initialization-facts"].get("records", ())
    initialization = initialization_records[0].get("value", {}) if len(initialization_records) == 1 else {}
    mappings = module_payload.get("source_output_mappings", ())
    module_rule_ids = {item.get("rule_id") for item in module_payload.get("rule_plans", ())}
    vertical_ok = all(
        (
            module_result.stage_artifact.schema_version == "0.12",
            module_payload.get("schema_version") == GENERATED_C_SCHEMA,
            module_payload.get("c_ir_schema") == C_IR_SCHEMA,
            len(_kind_dicts(c_ir, {"CTranslationUnit"})) == 1,
            len(prototypes) == 2,
            len(definitions) == 2,
            prototype_bindings == definition_bindings,
            c_ir.get("module_order") == ["lib.math", "app"],
            c_ir.get("module_dependencies") == [["app", "lib.math"]],
            list(c_ir_manifest_by_id) == ["lib.math", "app"],
            c_ir_manifest_by_id.get("app", {}).get("bundle_ordinal") == 0,
            c_ir_manifest_by_id.get("app", {}).get("is_primary") is True,
            c_ir_manifest_by_id.get("lib.math", {}).get("bundle_ordinal") == 1,
            c_ir_manifest_by_id.get("lib.math", {}).get("is_primary") is False,
            [item.get("bundle_function_ordinal") for item in prototypes] == [0, 1],
            [item.get("bundle_function_ordinal") for item in definitions] == [0, 1],
            {item.get("owner_module_id") for item in source_functions} == {"app", "lib.math"},
            all(item.get("owner_document_id") for item in source_functions),
            not any(kind == "CFunctionPrototype" for kind in declaration_kinds[declaration_kinds.index("CFunctionDefinition"):]),
            all(item.get("storage") == "none" for item in source_functions),
            all(item.get("identifier", {}).get("spelling", "").startswith("pycm_") for item in source_functions),
            initialization.get("module_order") == ["lib.math", "app"],
            initialization.get("cycle_policy") == "reject-all-cycles",
            initialization.get("runtime_initialization") == "none",
            not module_payload.get("helper_manifest"),
            {item.get("module_id") for item in mappings if item.get("source_document_id")} >= {"app", "lib.math"},
            all("module_id" in item and "logical_source_name" in item for item in mappings),
            "phase12.module.import_from" in module_rule_ids,
            "phase12.module.cross_call" in module_rule_ids,
        )
    )
    if not vertical_ok:
        return fail("Phase 12 module C-IR/linkage/order/mapping contract mismatch", 12)

    test_run = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    test_transcript = test_run.stdout + "\n" + test_run.stderr
    if test_run.returncode or not re.search(r"\bRan 189 tests\b", test_transcript):
        return fail("Phase 12 executable regression gate did not pass exactly 189 tests", 13)

    audits = (
        audit_architecture(ROOT),
        audit_rules(ROOT),
        audit_helpers(ROOT),
        audit_containers(ROOT),
        audit_modules(ROOT),
        audit_determinism(ROOT),
        audit_transition(ROOT, "phase_12"),
    )
    failed_audits = [item.get("audit") for item in audits if not item.get("passed")]
    if failed_audits:
        return fail("Failed Phase 12 audits: " + ", ".join(str(item) for item in failed_audits), 14)

    evidence_check = subprocess.run(
        [sys.executable, str(ROOT / "tools/collect_phase12_evidence.py"), "check", "--tests-run", "189"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if evidence_check.returncode:
        return fail(evidence_check.stdout.strip() or "Phase 12 generated evidence is stale", 15)
    evidence_root = ROOT / "evidence" / "phase_12"
    for report_name in REPORTS + ("package_report.json",):
        report = json.loads((evidence_root / report_name).read_text(encoding="utf-8"))
        if not report.get("passed"):
            return fail(f"Phase 12 evidence did not pass: {report_name}", 16)
        if "PENDING" in json.dumps(report, sort_keys=True).upper():
            return fail(f"Phase 12 evidence is not finalized: {report_name}", 16)
        if report.get("generated_c_compiled_or_executed") is True:
            return fail(f"Phase 12 evidence violates the source-only boundary: {report_name}", 16)

    package = json.loads((evidence_root / "package_report.json").read_text(encoding="utf-8"))
    if not all(
        (
            package.get("schema_version") == "pycforge.package-report/0.12",
            package.get("package_version") == "0.12.0",
            package.get("wheel_filename") == "pycforge-0.12.0-py3-none-any.whl",
            isinstance(package.get("wheel_size_bytes"), int),
            package.get("wheel_size_bytes", 0) > 0,
            bool(re.fullmatch(r"[0-9a-f]{64}", str(package.get("wheel_sha256", "")))),
            package.get("source_date_epoch") == 1735689600,
            package.get("fixed_epoch_builds_compared") == 2,
            package.get("reproducible_wheel_bytes"),
            package.get("isolated_install_passed"),
            package.get("installed_module_bundle_smoke_passed"),
            package.get("installed_container_smoke_passed"),
            package.get("installed_generated_text_conformance_passed"),
            package.get("installed_source_controlled_include_absent"),
            package.get("installed_translation_unit_count") == 1,
            package.get("wheel_archive_integrity_passed"),
            package.get("wheel_metadata_version") == "0.12.0",
            package.get("wheel_tag") == "py3-none-any",
            package.get("wheel_contains_module_resolver"),
            package.get("wheel_contains_native_extension") is False,
            package.get("wheel_file_authenticated_during_release"),
            package.get("installed_generated_artifact_schema") == GENERATED_C_SCHEMA,
            package.get("installed_c_ir_schema") == C_IR_SCHEMA,
            package.get("installed_conversion_summary_schema") == CONVERSION_SUMMARY_SCHEMA,
            package.get("installed_decision_trace_schema") == DECISION_TRACE_SCHEMA,
            package.get("installed_result_schema") == RESULT_SCHEMA_VERSION,
            package.get("installed_helper_registry_fingerprint_preserved"),
            package.get("native_extension_built") is False,
            package.get("generated_c_compiled_or_executed") is False,
        )
    ):
        return fail("Phase 12 package evidence is incomplete", 17)

    wheel = _wheel_file(args.wheel, package["wheel_filename"])
    if args.wheel and (wheel is None or not wheel.is_file()):
        return fail("Requested Phase 12 wheel is absent", 17)
    if wheel is not None:
        wheel_bytes = wheel.read_bytes()
        if (
            wheel.name != package["wheel_filename"]
            or len(wheel_bytes) != package["wheel_size_bytes"]
            or hashlib.sha256(wheel_bytes).hexdigest() != package["wheel_sha256"]
        ):
            return fail("Phase 12 wheel identity does not match package evidence", 17)
        try:
            with zipfile.ZipFile(wheel) as archive:
                if archive.testzip() is not None:
                    return fail("Phase 12 wheel archive integrity check failed", 17)
                names = archive.namelist()
                metadata = archive.read("pycforge-0.12.0.dist-info/METADATA").decode("utf-8")
                wheel_metadata = archive.read("pycforge-0.12.0.dist-info/WHEEL").decode("utf-8")
        except (OSError, KeyError, UnicodeDecodeError, zipfile.BadZipFile):
            return fail("Phase 12 wheel structure is invalid", 17)
        if (
            "\nVersion: 0.12.0\n" not in "\n" + metadata
            or "\nTag: py3-none-any\n" not in "\n" + wheel_metadata
            or any(name.lower().endswith((".so", ".pyd", ".dll", ".dylib")) for name in names)
            or not any(name == "pycforge/converter/modules/analysis.py" for name in names)
        ):
            return fail("Phase 12 wheel content or metadata contract mismatch", 17)

    expected = fingerprint_record.get("value")
    actual = tree_hash()
    if expected != actual:
        return fail(f"Phase 12 tree fingerprint mismatch: {actual} != {expected}", 18)
    print("Phase 12 validation passed")
    print("189 tests recorded: 169 predecessor regressions + 20 Phase 12 tests")
    print(f"Phase 12 tree SHA-256: {actual}")
    print(f"Phase 11 archive verified: {predecessor is not None}")
    print(f"Phase 12 wheel verified: {wheel is not None}")
    print(f"Helper registry SHA-256 preserved: {registry.fingerprint}")
    print("Explicit SourceBundle modules emit one C translation unit; generated C was not compiled or executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
