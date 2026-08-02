from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__
from pycforge.converter.core.serialization import result_to_dict
from pycforge.converter.support_templates import (
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
    FrozenHelperRegistry,
    builtin_definitions,
    default_helper_registry,
)
from pycforge.laboratory.audits import (
    audit_architecture,
    audit_determinism,
    audit_helpers,
    audit_rules,
    audit_transition,
)


FINGERPRINT = Path("transition/phase_10/baseline_fingerprint.json")
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
PHASE9_ARCHIVE_SHA256 = "68a5bbe443513d5a40a009be8e55ca9ec513805a4dc6f8c9d5e08bdd6a4afcff"
PHASE9_TREE_SHA256 = "bfbb13eb764b02a6b8fb2c4ff1eb12f4249976bb1919aa85a383d6e24b4079e8"


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


def main() -> int:
    manifest = json.loads(
        (ROOT / "transition/phase_10/manifest.json").read_text(encoding="utf-8")
    )
    fingerprint_record = json.loads((ROOT / FINGERPRINT).read_text(encoding="utf-8"))
    if manifest.get("phase") != 10 or manifest.get("version") != "0.10.0":
        return fail("Phase 10 manifest identity mismatch", 2)
    if __version__ != "0.10.0" or 'version = "0.10.0"' not in (ROOT / "pyproject.toml").read_text(encoding="utf-8"):
        return fail("Phase 10 package identity mismatch", 3)
    if manifest.get("required_tests") != 154 or manifest.get("opening_regression_tests") != 143 or manifest.get("phase_tests") != 11:
        return fail("Phase 10 test-count contract mismatch", 4)
    missing = [name for name in manifest.get("required_files", ()) if not (ROOT / name).is_file()]
    if missing:
        return fail("Missing Phase 10 files: " + ", ".join(sorted(missing)), 5)
    if manifest.get("predecessor_archive_sha256") != PHASE9_ARCHIVE_SHA256 or manifest.get("predecessor_tree_sha256") != PHASE9_TREE_SHA256:
        return fail("Sealed Phase 9 rollback identity mismatch", 6)
    phase9_record = json.loads(
        (ROOT / "transition/phase_9/baseline_fingerprint.json").read_text(encoding="utf-8")
    )
    if phase9_record.get("value") != PHASE9_TREE_SHA256:
        return fail("Recorded sealed Phase 9 tree fingerprint changed", 6)
    if hashlib.sha256((ROOT / "docs/python_to_c_converter_architecture_revision_3_1.txt").read_bytes()).hexdigest() != ROADMAP_SHA256:
        return fail("Architecture Revision 3.1 hash mismatch", 7)
    if hashlib.sha256((ROOT / "docs/python_to_c_converter_architecture_revision_3_2_addendum.md").read_bytes()).hexdigest() != ADDENDUM_SHA256:
        return fail("Architecture Revision 3.2 addendum hash mismatch", 7)

    decisions = (ROOT / "transition/phase_10/helper_feasibility_decisions.md").read_text(encoding="utf-8")
    for reference in (FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical):
        if reference not in decisions:
            return fail(f"Accepted helper decision missing: {reference}", 8)

    registry = default_helper_registry()
    reverse = FrozenHelperRegistry(reversed(builtin_definitions()))
    required_helpers = [FLOOR_DIV_REFERENCE.canonical, FLOOR_MOD_REFERENCE.canonical]
    if [item["reference"] for item in registry.manifest] != required_helpers:
        return fail("Phase 10 helper registry contents mismatch", 9)
    if registry.manifest != reverse.manifest or registry.fingerprint != reverse.fingerprint:
        return fail("Helper registry varies by registration order", 9)
    resolved = registry.resolve(required_helpers, target_contract="c11-portable-fixed-v1")
    if [item.reference.canonical for item in resolved.manifest] != required_helpers:
        return fail("Exact helper dependency closure mismatch", 9)

    source = "def identity(value: int) -> int:\n    return value\n"
    request = ConversionRequest.from_source(source)
    converter = PythonToCConverter()
    baseline = converter.convert(request)

    def broken_progress(_event: object) -> None:
        raise RuntimeError("injected progress observer failure")

    observed = converter.convert(request, progress=broken_progress)
    if baseline.status is not ResultStatus.CONVERTED or result_to_dict(observed) != result_to_dict(baseline):
        return fail("Progress observer changed Phase 10 conversion semantics", 10)
    payload = baseline.stage_artifact.payload
    if payload.get("helper_requirements") or payload.get("helper_manifest"):
        return fail("Current promoted RulePlans unexpectedly selected a helper", 11)
    if (
        baseline.stage_artifact.schema_version != "0.10"
        or payload.get("schema_version") != "generated-c/0.10"
        or payload.get("c_ir_schema") != "c-ir/0.9"
        or baseline.conversion_summary.get("schema_version") != "pycforge.conversion-summary/0.10"
        or baseline.decision_trace.get("schema_version") != "pycforge.decision-trace/0.10"
        or result_to_dict(baseline).get("schema_version") != "0.3"
    ):
        return fail("Phase 10 public schema identity mismatch", 11)
    if "pycf_i64_floor_" in (baseline.generated_c or ""):
        return fail("Unused helper entered current generated C", 11)

    audits = (
        audit_architecture(ROOT),
        audit_rules(ROOT),
        audit_helpers(ROOT),
        audit_determinism(ROOT),
        audit_transition(ROOT, "phase_10"),
    )
    failed_audits = [item.get("audit") for item in audits if not item.get("passed")]
    if failed_audits:
        return fail("Failed Phase 10 audits: " + ", ".join(str(item) for item in failed_audits), 12)

    reports = (
        "phase10_report.json",
        "helper_registry_report.json",
        "semantic_preservation_report.json",
        "qt_widget_smoke_report.json",
        "test_summary.json",
        "package_report.json",
        "transition_report.json",
    )
    for report_name in reports:
        report = json.loads((ROOT / "evidence/phase_10" / report_name).read_text(encoding="utf-8"))
        if not report.get("passed"):
            return fail(f"Phase 10 evidence did not pass: {report_name}", 13)
        if "PENDING" in json.dumps(report, sort_keys=True):
            return fail(f"Phase 10 evidence is not finalized: {report_name}", 13)
        if report.get("generated_c_compiled_or_executed") is True:
            return fail(f"Phase 10 evidence violates the source-only boundary: {report_name}", 13)
    package = json.loads((ROOT / "evidence/phase_10/package_report.json").read_text(encoding="utf-8"))
    if not package.get("reproducible_wheel_bytes") or not package.get("isolated_install_passed"):
        return fail("Phase 10 package evidence is incomplete", 14)
    qt = json.loads((ROOT / "evidence/phase_10/qt_widget_smoke_report.json").read_text(encoding="utf-8"))
    if not qt.get("passed") or not all(qt.get("checks", {}).values()):
        return fail("Actual Qt widget smoke did not pass", 15)

    expected = fingerprint_record.get("value")
    actual = tree_hash()
    if expected != actual:
        return fail(f"Phase 10 tree fingerprint mismatch: {actual} != {expected}", 16)
    print("Phase 10 validation passed")
    print("154 tests recorded: 143 opening-checkpoint regressions + 11 Phase 10 tests")
    print(f"Phase 10 tree SHA-256: {actual}")
    print(f"Helper registry SHA-256: {registry.fingerprint}")
    print("Current RulePlans emit no helpers; generated C was not compiled or executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
