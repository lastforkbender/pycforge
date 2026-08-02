from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.contracts.configuration import PHASE9_RULE_SET
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    RESULT_SCHEMA_VERSION,
)
from pycforge.converter.core.serialization import result_to_dict
from pycforge.converter.support_templates import default_helper_registry
from pycforge.laboratory.audits import (
    audit_architecture,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_rules,
    audit_transition,
)


FINGERPRINT = Path("transition/phase_11/baseline_fingerprint.json")
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
PHASE10_ARCHIVE_SHA256 = "0f54742d1ae1cef604291d0a38286a475cd048792f986ca95e20b3348cdc5c4b"
PHASE10_TREE_SHA256 = "f3fc12f357ff7c3667f483375d431e087dcfb65302d279194f9ed51466787ea2"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
HELPER_ASSET_SHA256 = (
    "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
    "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predecessor-archive")
    args = parser.parse_args(argv)

    manifest = json.loads((ROOT / "transition/phase_11/manifest.json").read_text(encoding="utf-8"))
    fingerprint_record = json.loads((ROOT / FINGERPRINT).read_text(encoding="utf-8"))
    if manifest.get("phase") != 11 or manifest.get("version") != "0.11.0":
        return fail("Phase 11 manifest identity mismatch", 2)
    if __version__ != "0.11.0" or 'version = "0.11.0"' not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        return fail("Phase 11 package identity mismatch", 3)
    if (
        manifest.get("required_tests") != 169
        or manifest.get("predecessor_regression_tests") != 154
        or manifest.get("phase_tests") != 15
    ):
        return fail("Phase 11 test-count contract mismatch", 4)
    missing = [name for name in manifest.get("required_files", ()) if not (ROOT / name).is_file()]
    if missing:
        return fail("Missing Phase 11 files: " + ", ".join(sorted(missing)), 5)

    if (
        manifest.get("predecessor_archive_sha256") != PHASE10_ARCHIVE_SHA256
        or manifest.get("predecessor_tree_sha256") != PHASE10_TREE_SHA256
    ):
        return fail("Sealed Phase 10 rollback identity mismatch", 6)
    phase10_record = json.loads((ROOT / "transition/phase_10/baseline_fingerprint.json").read_text(encoding="utf-8"))
    if phase10_record.get("value") != PHASE10_TREE_SHA256:
        return fail("Recorded sealed Phase 10 tree fingerprint changed", 6)
    predecessor = Path(args.predecessor_archive).resolve() if args.predecessor_archive else None
    if predecessor is None:
        candidate = ROOT.parents[1] / "pycforge_phase_10_v0_10_0.tar.gz"
        predecessor = candidate if candidate.is_file() else None
    if args.predecessor_archive and (predecessor is None or not predecessor.is_file()):
        return fail("Requested predecessor archive is absent", 6)
    if predecessor is not None and hashlib.sha256(predecessor.read_bytes()).hexdigest() != PHASE10_ARCHIVE_SHA256:
        return fail("Sealed Phase 10 archive hash mismatch", 6)

    if hashlib.sha256((ROOT / "docs/python_to_c_converter_architecture_revision_3_1.txt").read_bytes()).hexdigest() != ROADMAP_SHA256:
        return fail("Architecture Revision 3.1 hash mismatch", 7)
    if hashlib.sha256((ROOT / "docs/python_to_c_converter_architecture_revision_3_2_addendum.md").read_bytes()).hexdigest() != ADDENDUM_SHA256:
        return fail("Architecture Revision 3.2 addendum hash mismatch", 7)
    decisions = (ROOT / "transition/phase_11/container_representation_decisions.md").read_text(encoding="utf-8").lower()
    for term in ("capacity", "aliasing", "ownership", "lifetime", "negative indices", "allocation", "cleanup", "insertion order", "pyc3407"):
        if term not in decisions:
            return fail(f"Phase 11 representation decision omits {term}", 8)

    source = "def f(value: int) -> int:\n    return value + 1\n"
    converter = PythonToCConverter()
    current = converter.convert(ConversionRequest.from_source(source))
    historical = converter.convert(
        ConversionRequest.from_source(source, rule_set_version=PHASE9_RULE_SET, renderer_version="c-renderer-v0.9")
    )
    if current.status is not ResultStatus.CONVERTED or historical.status is not ResultStatus.CONVERTED:
        return fail("Cumulative scalar compatibility conversion failed", 9)
    if current.generated_c != historical.generated_c:
        return fail("Phase 11 changed predecessor scalar generated-C bytes", 9)
    payload = current.stage_artifact.payload
    if (
        payload.get("schema_version") != GENERATED_C_SCHEMA
        or payload.get("c_ir_schema") != C_IR_SCHEMA
        or payload.get("helper_manifest")
        or current.conversion_summary.get("schema_version") != CONVERSION_SUMMARY_SCHEMA
        or current.decision_trace.get("schema_version") != DECISION_TRACE_SCHEMA
        or result_to_dict(current).get("schema_version") != RESULT_SCHEMA_VERSION
    ):
        return fail("Phase 11 schema or empty-helper identity mismatch", 10)
    if payload.get("schema_version") != "generated-c/0.11" or payload.get("rule_set_version") != "phase11-bounded-containers-v0.11":
        return fail("Phase 11 current configuration mismatch", 10)
    if historical.stage_artifact.payload.get("c_ir_schema") != "c-ir/0.9" or historical.stage_artifact.payload.get("schema_version") != "generated-c/0.10":
        return fail("Historical function/call artifact compatibility changed", 10)
    if "array_extents" in json.dumps(historical.stage_artifact.payload.get("c_ir"), sort_keys=True):
        return fail("Historical C IR serialization was silently repurposed", 10)

    registry = default_helper_registry()
    if registry.fingerprint != HELPER_REGISTRY_SHA256 or tuple(item["asset_fingerprint"] for item in registry.manifest) != HELPER_ASSET_SHA256:
        return fail("Phase 10 StableInternal helper fingerprints changed", 11)
    audits = (
        audit_architecture(ROOT),
        audit_rules(ROOT),
        audit_helpers(ROOT),
        audit_containers(ROOT),
        audit_determinism(ROOT, "def f() -> int:\n    values = [1, 2]\n    return values[-1]\n"),
        audit_transition(ROOT, "phase_11"),
    )
    failed_audits = [item.get("audit") for item in audits if not item.get("passed")]
    if failed_audits:
        return fail("Failed Phase 11 audits: " + ", ".join(str(item) for item in failed_audits), 12)

    evidence_check = subprocess.run(
        [sys.executable, str(ROOT / "tools/collect_phase11_evidence.py"), "check", "--tests-run", "169"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if evidence_check.returncode:
        return fail(evidence_check.stdout.strip() or "Phase 11 generated evidence is stale", 13)
    reports = (
        "phase11_report.json",
        "container_report.json",
        "architecture_report.json",
        "rule_report.json",
        "helper_registry_report.json",
        "determinism_report.json",
        "schema_report.json",
        "semantic_preservation_report.json",
        "test_summary.json",
        "package_report.json",
        "transition_report.json",
    )
    for report_name in reports:
        report = json.loads((ROOT / "evidence/phase_11" / report_name).read_text(encoding="utf-8"))
        if not report.get("passed"):
            return fail(f"Phase 11 evidence did not pass: {report_name}", 14)
        if "PENDING" in json.dumps(report, sort_keys=True):
            return fail(f"Phase 11 evidence is not finalized: {report_name}", 14)
        if report.get("generated_c_compiled_or_executed") is True:
            return fail(f"Phase 11 evidence violates the source-only boundary: {report_name}", 14)
    package = json.loads((ROOT / "evidence/phase_11/package_report.json").read_text(encoding="utf-8"))
    if not package.get("reproducible_wheel_bytes") or not package.get("isolated_install_passed") or not package.get("installed_container_smoke_passed"):
        return fail("Phase 11 package evidence is incomplete", 15)

    expected = fingerprint_record.get("value")
    actual = tree_hash()
    if expected != actual:
        return fail(f"Phase 11 tree fingerprint mismatch: {actual} != {expected}", 16)
    print("Phase 11 validation passed")
    print("169 tests recorded: 154 predecessor regressions + 15 Phase 11 tests")
    print(f"Phase 11 tree SHA-256: {actual}")
    print(f"Phase 10 archive verified: {predecessor is not None}")
    print(f"Helper registry SHA-256 preserved: {registry.fingerprint}")
    print("Bounded containers emit no helpers; generated C was not compiled or executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
