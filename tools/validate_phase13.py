"""Authenticate and validate the PyCForge Phase 13 v0.13.0 release.

The validator exercises conversion and inspects structured artifacts.  It does
not compile, link, load, or execute generated C.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__  # noqa: E402
from pycforge.converter.c_output import validate_c_text  # noqa: E402
from pycforge.converter.contracts.configuration import (  # noqa: E402
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_TARGET_CONTRACT,
    PHASE12_MODULE_POLICY,
    PHASE12_RENDERER,
    PHASE12_RULE_SET,
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
)
from pycforge.converter.contracts.versions import (  # noqa: E402
    CONTAINER_FACT_SCHEMA,
    MODULE_FACT_SCHEMA,
    PHASE13_C_IR_SCHEMA,
    PHASE13_CONVERSION_PLAN_SCHEMA,
    PHASE13_CONVERSION_SUMMARY_SCHEMA,
    PHASE13_DECISION_TRACE_SCHEMA,
    PHASE13_GENERATED_C_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.support_templates import default_helper_registry  # noqa: E402
from pycforge.laboratory.audits import (  # noqa: E402
    audit_architecture,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_modules,
    audit_records,
    audit_rules,
    audit_transition,
)


RELEASE_VERSION = "0.13.0"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_12_2_v0_12_2.tar.gz"
PREDECESSOR_ARCHIVE_SHA256 = "6a603684001f2cb2e9365d7e9b318f1a95dbe95b2cb36cf8821c30403c1754d0"
PREDECESSOR_TREE_SHA256 = "434981decfd2b2fc2b344f5b9a3b37377396376c2e0a8c8ed00bb9fa9077d765"
PREDECESSOR_CONVERTER_SHA256 = "4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51"
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
PHASE13_COMPATIBILITY_C_SHA256 = "d54ec54f5d9b0553d73c77179c3429928eb2c2deaa4963776429b628918cf257"
PHASE13_COMPATIBILITY_OUTPUT_SHA256 = "da9e27bd909e2ddf9154b072d668c98576a925aa7a342244db566d254ec0e556"
PHASE13_COMPATIBILITY_REQUEST_SHA256 = "a8cb25e7596427d78a9b6560e833786920216631f3179da4abc5a8a12fabe3fb"
RELEASE_FINGERPRINT = PurePosixPath("transition/phase_13/release_fingerprint.json")
FINGERPRINT_DOMAIN = "pycforge-phase-13-release-tree-v1"

EXPECTED_CONTRACTS: Mapping[str, object] = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "conversion_plan": "conversion-plan/0.13",
    "c_ir": "c-ir/0.13",
    "generated_c": "generated-c/0.13",
    "conversion_summary": "pycforge.conversion-summary/0.13",
    "decision_trace": "pycforge.decision-trace/0.13",
    "result_serialization": "0.5",
    "rule_set": "phase13-static-records-v0.13",
    "renderer": "c-renderer-v0.13",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
}

RECORD_TABLES = {
    "record-access-facts",
    "record-binding-facts",
    "record-definition-facts",
    "record-field-facts",
    "record-initializer-facts",
    "record-instance-facts",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file_map(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        path_bytes = relative.encode("utf-8")
        data = files[relative]
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _included(relative: PurePosixPath) -> bool:
    return not (
        relative == RELEASE_FINGERPRINT
        or "__pycache__" in relative.parts
        or ".pytest_cache" in relative.parts
        or "build" in relative.parts
        or "dist" in relative.parts
        or relative.name.endswith((".pyc", ".pyo"))
    )


def canonical_release_tree_hash(root: Path = ROOT) -> str:
    """Hash the release tree, excluding its self-referential fingerprint."""

    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if _included(relative):
            files[relative.as_posix()] = path.read_bytes()
    return _hash_file_map(files)


def archive_file_map(archive: Path) -> dict[str, bytes]:
    """Read a single-root, regular-file-only gzip tar without extracting it."""

    files: dict[str, bytes] = {}
    root_name: str | None = None
    with tarfile.open(archive, mode="r:gz") as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"unsafe archive member: {member.name!r}")
            if root_name is None:
                root_name = path.parts[0]
            elif path.parts[0] != root_name:
                raise ValueError("archive has more than one release root")
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) == 1:
                raise ValueError(f"archive member is not a release file: {member.name!r}")
            relative = PurePosixPath(*path.parts[1:])
            if not _included(relative):
                continue
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read archive member: {member.name!r}")
            name = relative.as_posix()
            if name in files:
                raise ValueError(f"duplicate archive member: {name!r}")
            files[name] = stream.read()
    if root_name is None or not files:
        raise ValueError("archive is empty")
    return files


def canonical_archive_tree_hash(archive: Path) -> str:
    return _hash_file_map(archive_file_map(archive))


def canonical_archive_subtree_hash(archive: Path, prefix: str) -> str:
    marker = prefix.rstrip("/") + "/"
    files = {
        name[len(marker) :]: data
        for name, data in archive_file_map(archive).items()
        if name.startswith(marker)
    }
    if not files:
        raise ValueError(f"archive subtree is absent: {prefix}")
    return _hash_file_map(files)


def current_contracts() -> dict[str, object]:
    """Return the explicit historical Phase 13 contract surface.

    The public name is retained for compatibility with the sealed validator's
    tests.  It must not follow the active defaults of a later cumulative tree.
    """

    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "conversion_plan": PHASE13_CONVERSION_PLAN_SCHEMA,
        "c_ir": PHASE13_C_IR_SCHEMA,
        "generated_c": PHASE13_GENERATED_C_SCHEMA,
        "conversion_summary": PHASE13_CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": PHASE13_DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "rule_set": PHASE13_RULE_SET,
        "renderer": PHASE13_RENDERER,
        "module_policy": DEFAULT_MODULE_POLICY,
        "record_policy": DEFAULT_RECORD_POLICY,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "target_contract": DEFAULT_TARGET_CONTRACT,
    }


def exact_mapping_errors(
    actual: Mapping[str, object], expected: Mapping[str, object], label: str
) -> list[str]:
    errors: list[str] = []
    for key in sorted(set(actual) | set(expected)):
        if key not in actual:
            errors.append(f"{label}: missing key {key!r}")
        elif key not in expected:
            errors.append(f"{label}: unexpected key {key!r}")
        elif actual[key] != expected[key]:
            errors.append(
                f"{label}: {key!r} is {actual[key]!r}, expected {expected[key]!r}"
            )
    return errors


def _record_source() -> str:
    return (
        "class Sample:\n"
        "    count: int\n"
        "    ratio: float\n"
        "    enabled: bool\n"
        "    def __init__(self, count: int, ratio: float, enabled: bool) -> None:\n"
        "        self.count = count\n"
        "        self.ratio = ratio\n"
        "        self.enabled = enabled\n"
        "\n"
        "def read() -> int:\n"
        "    sample = Sample(7, 1.5, True)\n"
        "    return sample.count\n"
    )


def converter_smoke_errors() -> list[str]:
    errors: list[str] = []
    converter = PythonToCConverter()
    phase13 = {
        "rule_set_version": PHASE13_RULE_SET,
        "renderer_version": PHASE13_RENDERER,
    }
    request = ConversionRequest.from_source(_record_source(), **phase13)
    first = converter.convert(request)
    second = PythonToCConverter().convert(request)
    if first.status is not ResultStatus.CONVERTED or first.generated_c is None:
        return ["accepted static-record smoke did not convert"]
    if second.status is not ResultStatus.CONVERTED or second.generated_c is None:
        return ["repeated static-record smoke did not convert"]
    if first.generated_c != second.generated_c or first.output_fingerprint != second.output_fingerprint:
        errors.append("static-record conversion is not deterministic")
    if not validate_c_text(first.generated_c).accepted:
        errors.append("static-record generated C failed textual conformance")
    artifact = first.stage_artifact.payload if first.stage_artifact else {}
    tables = {
        item.get("table_id")
        for item in artifact.get("fact_tables", ())
        if str(item.get("table_id", "")).startswith("record-")
    }
    if tables != RECORD_TABLES:
        errors.append("static-record fact-table inventory is incomplete")
    if artifact.get("c_ir_schema") != PHASE13_C_IR_SCHEMA:
        errors.append("static-record smoke did not publish c-ir/0.13")
    if artifact.get("helper_manifest"):
        errors.append("static-record smoke unexpectedly requires runtime helpers")
    identifiers = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", first.generated_c))
    if identifiers & {"malloc", "calloc", "realloc", "free", "NULL", "nullptr"}:
        errors.append("static-record C contains allocation or null machinery")
    if "typedef struct" not in first.generated_c or "const Sample sample" not in first.generated_c:
        errors.append("static-record C omits typedef or const automatic aggregate")

    class_free = ConversionRequest.from_source(
        "def plus(value: int) -> int:\n"
        "    return value + 1\n"
        "\n"
        "def run() -> int:\n"
        "    return plus(2)\n",
        **phase13,
    )
    historical_phase13 = converter.convert(class_free)
    historical = converter.convert(
        replace(
            class_free,
            rule_set_version=PHASE12_RULE_SET,
            renderer_version=PHASE12_RENDERER,
            module_policy_version=PHASE12_MODULE_POLICY,
        )
    )
    if (
        historical_phase13.status is not ResultStatus.CONVERTED
        or historical.status is not ResultStatus.CONVERTED
        or historical_phase13.generated_c != historical.generated_c
        or historical_phase13.output_fingerprint != historical.output_fingerprint
    ):
        errors.append("class-free Phase 13 generated C differs from explicit Phase 12")
    if historical_phase13.generated_c is not None:
        if sha256_bytes(historical_phase13.generated_c.encode("utf-8")) != PHASE13_COMPATIBILITY_C_SHA256:
            errors.append("explicit Phase 13 compatibility generated-C hash changed")
    if (
        historical_phase13.output_fingerprint is None
        or historical_phase13.output_fingerprint.value != PHASE13_COMPATIBILITY_OUTPUT_SHA256
    ):
        errors.append("explicit Phase 13 compatibility output fingerprint changed")
    if (
        historical_phase13.request_fingerprint is None
        or historical_phase13.request_fingerprint.value != PHASE13_COMPATIBILITY_REQUEST_SHA256
    ):
        errors.append("explicit Phase 13 compatibility request fingerprint changed")
    return errors


def _required_files(manifest: Mapping[str, object]) -> set[str]:
    declared = manifest.get("required_contract_files", ())
    names = set(declared) if isinstance(declared, list) else set()
    return names | {
        "PyCForge_Phase_13_v0_13_0_Project_Handoff.txt",
        "pycforge/converter/records/analysis.py",
        "pycforge/converter/records/lowering.py",
        "tests/test_phase13_end_to_end.py",
        "tests/test_phase13_record_analysis.py",
        "tests/test_phase13_record_lowering.py",
        "tests/test_phase13_record_validation.py",
        "tools/validate_phase13.py",
        "transition/phase_13/candidate_reseed.md",
        "transition/phase_13/gate_evidence.md",
    }


def _load_json(path: Path, label: str, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read {label}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} is not a JSON object")
        return {}
    return value


def _predecessor_errors(archive: Path) -> list[str]:
    errors: list[str] = []
    if not archive.is_file():
        return [f"requested predecessor archive is absent: {archive}"]
    digest = sha256_bytes(archive.read_bytes())
    if digest != PREDECESSOR_ARCHIVE_SHA256:
        return [f"sealed Phase 12.2 archive hash mismatch: {digest}"]
    try:
        tree_digest = canonical_archive_tree_hash(archive)
        converter_digest = canonical_archive_subtree_hash(archive, "pycforge/converter")
    except (OSError, tarfile.TarError, ValueError) as exc:
        return [f"cannot authenticate predecessor archive: {exc}"]
    if tree_digest != PREDECESSOR_TREE_SHA256:
        errors.append(f"sealed Phase 12.2 tree hash mismatch: {tree_digest}")
    if converter_digest != PREDECESSOR_CONVERTER_SHA256:
        errors.append(f"sealed Phase 12 converter subtree hash mismatch: {converter_digest}")
    return errors


def wheel_errors(wheel: Path, fingerprint: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    if not wheel.is_file():
        return [f"requested wheel is absent: {wheel}"]
    artifacts = fingerprint.get("artifacts", {})
    expected = artifacts.get("wheel", {}) if isinstance(artifacts, dict) else {}
    digest = sha256_bytes(wheel.read_bytes())
    if not isinstance(expected, dict) or expected.get("sha256") != digest:
        errors.append("wheel hash does not match the release fingerprint")
    if isinstance(expected, dict) and expected.get("size") != wheel.stat().st_size:
        errors.append("wheel size does not match the release fingerprint")
    try:
        with zipfile.ZipFile(wheel) as package:
            names = set(package.namelist())
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = package.read(metadata_name).decode("utf-8")
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
        return errors + [f"cannot inspect wheel: {exc}"]
    if f"Version: {RELEASE_VERSION}\n" not in metadata:
        errors.append("wheel metadata version mismatch")
    required = {
        "pycforge/converter/records/analysis.py",
        "pycforge/converter/records/lowering.py",
        "pycforge/converter/records/model.py",
    }
    missing = sorted(required - names)
    if missing:
        errors.append("wheel omits record modules: " + ", ".join(missing))
    native = sorted(name for name in names if name.endswith((".so", ".dll", ".dylib", ".pyd")))
    if native:
        errors.append("wheel unexpectedly contains native binaries")
    return errors


def source_archive_errors(
    archive: Path, fingerprint: Mapping[str, object]
) -> list[str]:
    if not archive.is_file():
        return [f"requested Phase 13 source archive is absent: {archive}"]
    artifacts = fingerprint.get("artifacts", {})
    expected = artifacts.get("source_archive", {}) if isinstance(artifacts, dict) else {}
    errors: list[str] = []
    if not isinstance(expected, dict) or expected.get("filename") != archive.name:
        errors.append("source archive name does not match the release fingerprint")
    try:
        archive_tree = canonical_archive_tree_hash(archive)
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot inspect Phase 13 source archive: {exc}"]
    if archive_tree != fingerprint.get("value"):
        errors.append(f"source archive release tree hash mismatch: {archive_tree}")
    return errors


def validate_tree(
    root: Path = ROOT,
    *,
    predecessor_archive: Path | None = None,
    wheel: Path | None = None,
    source_archive: Path | None = None,
    require_promoted: bool = True,
    converter_smoke: bool = True,
) -> tuple[str, ...]:
    root = Path(root)
    errors: list[str] = []
    manifest = _load_json(root / "transition/phase_13/manifest.json", "Phase 13 manifest", errors)
    if manifest.get("phase") != 13 or manifest.get("version") != RELEASE_VERSION:
        errors.append("Phase 13 manifest identity mismatch")
    if require_promoted and manifest.get("status") != "promoted":
        errors.append("Phase 13 manifest is not promoted")
    if not isinstance(manifest.get("required_tests"), int) or int(manifest.get("required_tests", 0)) < 224:
        errors.append("Phase 13 required-test count is below its predecessor gate")
    manifest_contracts = manifest.get("schemas", {})
    if isinstance(manifest_contracts, dict):
        errors.extend(exact_mapping_errors(manifest_contracts, EXPECTED_CONTRACTS, "Phase 13 manifest contracts"))
    else:
        errors.append("Phase 13 manifest contracts are not an object")
    errors.extend(exact_mapping_errors(current_contracts(), EXPECTED_CONTRACTS, "active contracts"))

    if __version__ != RELEASE_VERSION:
        errors.append(f"imported version is {__version__!r}")
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        project_version = project["project"]["version"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read package version: {exc}")
    else:
        if project_version != RELEASE_VERSION:
            errors.append(f"pyproject version is {project_version!r}")

    for name in sorted(_required_files(manifest)):
        if not (root / name).is_file():
            errors.append(f"missing Phase 13 release file: {name}")
    if sha256_bytes((root / "docs/python_to_c_converter_architecture_revision_3_1.txt").read_bytes()) != ROADMAP_SHA256:
        errors.append("Architecture Revision 3.1 hash mismatch")
    if sha256_bytes((root / "docs/python_to_c_converter_architecture_revision_3_2_addendum.md").read_bytes()) != ADDENDUM_SHA256:
        errors.append("Architecture Revision 3.2 addendum hash mismatch")
    if default_helper_registry().fingerprint != HELPER_REGISTRY_SHA256:
        errors.append("Phase 10 helper registry identity changed")

    for name, report in (
        ("architecture", audit_architecture(root)),
        ("rules", audit_rules(root)),
        ("helpers", audit_helpers(root)),
        ("containers", audit_containers(root)),
        ("modules", audit_modules(root)),
        ("records", audit_records(root)),
        ("determinism", audit_determinism(root)),
        ("transition", audit_transition(root, "phase_13")),
    ):
        if report.get("passed") is not True:
            errors.append(f"{name} audit failed: {report}")
    if converter_smoke:
        errors.extend(converter_smoke_errors())

    if predecessor_archive is not None:
        errors.extend(_predecessor_errors(Path(predecessor_archive)))

    fingerprint_path = root / RELEASE_FINGERPRINT
    fingerprint = (
        _load_json(fingerprint_path, "Phase 13 release fingerprint", errors)
        if require_promoted or fingerprint_path.is_file()
        else {}
    )
    if fingerprint:
        if (
            fingerprint.get("algorithm") != "sha256"
            or fingerprint.get("domain") != FINGERPRINT_DOMAIN
            or fingerprint.get("status") != "promoted"
        ):
            errors.append("Phase 13 release fingerprint metadata is invalid")
        expected_tree = fingerprint.get("value")
        actual_tree = canonical_release_tree_hash(root)
        if expected_tree != actual_tree:
            errors.append(f"Phase 13 release tree hash mismatch: {actual_tree}")
        if fingerprint.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256:
            errors.append("release fingerprint predecessor identity mismatch")
    if wheel is not None:
        errors.extend(wheel_errors(Path(wheel), fingerprint))
    if source_archive is not None:
        errors.extend(source_archive_errors(Path(source_archive), fingerprint))

    state = (root / "CURRENT_STATE.md").read_text(encoding="utf-8")
    if require_promoted and (
        "Current release: `0.13.0` / Phase 13" not in state
        or "Release status: promoted" not in state
    ):
        errors.append("CURRENT_STATE does not identify a promoted Phase 13 release")
    state_lower = state.lower()
    if "windows 11" not in state_lower or not any(
        wording in state_lower
        for wording in ("not claimed", "not evidence claimed", "no windows execution claim")
    ):
        errors.append("CURRENT_STATE omits the Windows 11 no-claim boundary")
    return tuple(dict.fromkeys(errors))


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_ARCHIVE_NAME,
        root.parent / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / "release" / PREDECESSOR_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def locate_wheel(root: Path = ROOT) -> Path | None:
    name = "pycforge-0.13.0-py3-none-any.whl"
    candidates = (root / "dist" / name, root / name, root.parent / name)
    return next((path for path in candidates if path.is_file()), None)


def locate_source_archive(root: Path = ROOT) -> Path | None:
    name = "pycforge_phase_13_v0_13_0.tar.gz"
    candidates = (
        root / name,
        root.parent / name,
        root.parents[1] / "release" / name,
    )
    return next((path for path in candidates if path.is_file()), None)


def _run_tests(root: Path) -> str | None:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        transcript = (completed.stdout + "\n" + completed.stderr).strip()
        return "regression suite failed\n" + transcript
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-archive")
    parser.add_argument("--require-predecessor", action="store_true")
    parser.add_argument("--wheel")
    parser.add_argument("--require-wheel", action="store_true")
    parser.add_argument("--source-archive")
    parser.add_argument("--require-source-archive", action="store_true")
    parser.add_argument("--skip-converter-smoke", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args(argv)

    archive = Path(args.predecessor_archive).resolve() if args.predecessor_archive else locate_predecessor_archive(ROOT)
    wheel = Path(args.wheel).resolve() if args.wheel else locate_wheel(ROOT)
    source_archive = (
        Path(args.source_archive).resolve()
        if args.source_archive
        else locate_source_archive(ROOT)
    )
    errors = list(
        validate_tree(
            ROOT,
            predecessor_archive=archive,
            wheel=wheel,
            source_archive=source_archive,
            converter_smoke=not args.skip_converter_smoke,
        )
    )
    if args.require_predecessor and archive is None:
        errors.append("sealed Phase 12.2 predecessor archive is required but absent")
    if args.require_wheel and wheel is None:
        errors.append("Phase 13 wheel is required but absent")
    if args.require_source_archive and source_archive is None:
        errors.append("Phase 13 source archive is required but absent")
    if args.run_tests and not errors:
        failure = _run_tests(ROOT)
        if failure:
            errors.append(failure)

    if errors:
        print("PyCForge Phase 13 validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PyCForge Phase 13 validation passed")
    print(f"Release version: {RELEASE_VERSION}")
    print(f"Release tree SHA-256: {canonical_release_tree_hash(ROOT)}")
    print(f"Sealed Phase 12.2 predecessor verified: {archive is not None}")
    print(f"Phase 13 wheel verified: {wheel is not None}")
    print(f"Phase 13 source archive verified: {source_archive is not None}")
    print("This validator invoked no C compiler, linker, loader, or execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
