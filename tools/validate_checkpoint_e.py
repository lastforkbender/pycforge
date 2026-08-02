"""Validate the source-only PyCForge Checkpoint E hardening gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge.laboratory.checkpoint_e import (  # noqa: E402
    DEFAULT_FUZZ_CASE_COUNT,
    EXPECTED_CONTRACT_IDENTITIES,
    audit_architecture_branding_product_boundary,
    audit_feature_matrix,
    audit_full_supported_subset,
    current_contract_identities,
)
from pycforge import __version__  # noqa: E402
from pycforge.ide import WORKSPACE_CONTRACT_VERSION  # noqa: E402
from tools.checkpoint_e_predecessor_equivalence import (  # noqa: E402
    PredecessorEquivalenceError,
    SEALED_PREDECESSOR_NAME,
    SEALED_PREDECESSOR_ROOT,
    SEALED_PREDECESSOR_SHA256,
    SEALED_PREDECESSOR_SIZE,
    audit_predecessor_equivalence,
)
from tools.build_checkpoint_e_release import (  # noqa: E402
    FINGERPRINT_DOMAIN,
    RELEASE_FINGERPRINT,
    ReleaseBuildError,
    release_tree_hash,
)


CHECKPOINT_E_VERSION = "0.14.4"
WORKSPACE_CONTRACT = "pycforge-workspace/0.2"
FEATURE_MATRIX_SCHEMA = "pycforge.feature-matrix/0.14.3"
FEATURE_MATRIX_ENTRY_COUNT = 69
FEATURE_MATRIX_SHA256 = (
    "ca78dff3ea203130781f5e0fde879c0ca9d7b7a0e550a05ab5d46ea3432cc01a"
)
TOOLCHAIN_INVOKED = False
GENERATED_C_COMPILED_OR_EXECUTED = False
PROMOTION_MINIMUM_GENERATED_CASES = 64
PROMOTION_MINIMUM_TOTAL_CASES = 80

REQUIRED_CHECKPOINT_E_FILES = frozenset(
    {
        "pycforge/laboratory/checkpoint_e.py",
        "tools/build_checkpoint_e_release.py",
        "tools/checkpoint_e_predecessor_equivalence.py",
        "tools/validate_checkpoint_e.py",
        "tests/test_checkpoint_e_audits.py",
        "tests/test_checkpoint_e_feature_matrix.py",
        "tests/test_checkpoint_e_predecessor_equivalence.py",
        "tests/test_checkpoint_e_release_packaging.py",
        "tests/test_checkpoint_e_versioning.py",
        "tests/test_validate_checkpoint_e.py",
        "README.md",
        "CURRENT_STATE.md",
        "CHANGELOG.md",
        "MANIFEST.in",
        "docs/python_to_c_converter_architecture_revision_3_1.txt",
        "docs/python_to_c_converter_architecture_revision_3_2_addendum.md",
        "docs/python_to_c_converter_architecture_revision_3_3_workspace_addendum.md",
        "docs/pycforge_workspace_quality_addendum.md",
        "specifications/feature_matrix.json",
        "specifications/pycforge_workspace.md",
        "transition/checkpoint_e/entry_criteria.md",
        "transition/checkpoint_e/architecture_and_workspace_decision.md",
        "transition/checkpoint_e/performance_budgets.md",
        "transition/checkpoint_e/feature_boundaries.md",
        "transition/checkpoint_e/feature_matrix_reconciliation.md",
        "transition/checkpoint_e/breadth_and_change_budgets.md",
        "transition/checkpoint_e/rollback_conditions.md",
        "transition/checkpoint_e/opening_evidence.md",
        "transition/checkpoint_e/gate_evidence.md",
        "evidence/checkpoint_e/entry_report.json",
        "evidence/checkpoint_e/workspace_debt.json",
        "evidence/checkpoint_e/debt_delta.json",
    }
)

PROMOTION_REQUIRED_CHECKPOINT_E_FILES = frozenset(
    {
        "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt",
        "transition/checkpoint_e/manifest.json",
        "evidence/checkpoint_e/full_subset_validation.json",
        "evidence/checkpoint_e/release_report.json",
    }
)

SEALED_REQUIRED_CHECKPOINT_E_FILES = frozenset(
    {RELEASE_FINGERPRINT.as_posix()}
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    """Locate the sealed Phase 14D archive without scanning arbitrary trees."""

    candidates = (
        root / SEALED_PREDECESSOR_NAME,
        root.parent / SEALED_PREDECESSOR_NAME,
        root.parent / "release_build" / "final" / SEALED_PREDECESSOR_NAME,
        root.parent / "final" / SEALED_PREDECESSOR_NAME,
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def authenticate_predecessor_archive(path: Path) -> dict[str, object]:
    """Authenticate identity and inspect archive structure without extraction."""

    errors: list[str] = []
    actual_size: int | None = None
    actual_sha256: str | None = None
    member_count = 0
    regular_file_count = 0
    archive_roots: list[str] = []

    if not path.is_file():
        errors.append(f"sealed predecessor is not a file: {path}")
    else:
        actual_size = path.stat().st_size
        if path.name != SEALED_PREDECESSOR_NAME:
            errors.append(
                f"sealed predecessor filename mismatch: expected "
                f"{SEALED_PREDECESSOR_NAME}, got {path.name}"
            )
        if actual_size != SEALED_PREDECESSOR_SIZE:
            errors.append(
                f"sealed predecessor size mismatch: expected "
                f"{SEALED_PREDECESSOR_SIZE}, got {actual_size}"
            )
        actual_sha256 = sha256_file(path)
        if actual_sha256 != SEALED_PREDECESSOR_SHA256:
            errors.append(
                "sealed predecessor SHA-256 mismatch: expected "
                f"{SEALED_PREDECESSOR_SHA256}, got {actual_sha256}"
            )

        try:
            with tarfile.open(path, mode="r:gz") as archive:
                members = archive.getmembers()
        except (OSError, tarfile.TarError) as exc:
            errors.append(f"sealed predecessor is not a readable gzip tar: {exc}")
        else:
            member_count = len(members)
            names: set[str] = set()
            roots: set[str] = set()
            for member in members:
                name = member.name
                pure = PurePosixPath(name)
                if name in names:
                    errors.append(f"duplicate archive member: {name}")
                names.add(name)
                if (
                    pure.is_absolute()
                    or not pure.parts
                    or any(part in {"", ".", ".."} for part in pure.parts)
                ):
                    errors.append(f"unsafe archive member path: {name}")
                    continue
                roots.add(pure.parts[0])
                if member.isfile():
                    regular_file_count += 1
                elif not member.isdir():
                    errors.append(
                        f"non-regular archive member is not allowed: {name}"
                    )
            archive_roots = sorted(roots)
            if archive_roots != [SEALED_PREDECESSOR_ROOT]:
                errors.append(
                    "sealed predecessor archive root mismatch: expected "
                    f"{SEALED_PREDECESSOR_ROOT}, got "
                    f"{','.join(archive_roots) or '<none>'}"
                )
            if not regular_file_count:
                errors.append("sealed predecessor contains no regular files")

    return {
        "audit": "sealed-phase14d-predecessor-authentication",
        "passed": not errors,
        "errors": errors,
        "archive_name": path.name,
        "expected_size": SEALED_PREDECESSOR_SIZE,
        "actual_size": actual_size,
        "expected_sha256": SEALED_PREDECESSOR_SHA256,
        "actual_sha256": actual_sha256,
        "archive_roots": archive_roots,
        "member_count": member_count,
        "regular_file_count": regular_file_count,
        "archive_extracted": False,
    }


def audit_checkpoint_metadata(root: Path) -> dict[str, object]:
    """Validate the non-semantic release, roadmap, and matrix identities."""

    errors: list[str] = []
    project_version: object = None
    matrix_schema: object = None
    matrix_entry_count: int | None = None
    matrix_sha256: str | None = None

    if __version__ != CHECKPOINT_E_VERSION:
        errors.append(
            f"imported package version is {__version__!r}, expected "
            f"{CHECKPOINT_E_VERSION!r}"
        )
    if WORKSPACE_CONTRACT_VERSION != WORKSPACE_CONTRACT:
        errors.append(
            "workspace contract identity changed: "
            f"{WORKSPACE_CONTRACT_VERSION!r}"
        )

    try:
        project = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )
        project_version = project["project"]["version"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read project version: {exc}")
    else:
        if project_version != CHECKPOINT_E_VERSION:
            errors.append(
                f"project version is {project_version!r}, expected "
                f"{CHECKPOINT_E_VERSION!r}"
            )

    matrix_path = root / "specifications/feature_matrix.json"
    try:
        matrix_bytes = matrix_path.read_bytes()
        matrix = json.loads(matrix_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read semantic feature matrix: {exc}")
    else:
        matrix_sha256 = hashlib.sha256(matrix_bytes).hexdigest()
        matrix_schema = matrix.get("schema") if isinstance(matrix, dict) else None
        entries = matrix.get("entries") if isinstance(matrix, dict) else None
        matrix_entry_count = len(entries) if isinstance(entries, list) else None
        if matrix_schema != FEATURE_MATRIX_SCHEMA:
            errors.append(
                f"feature matrix schema is {matrix_schema!r}, expected "
                f"{FEATURE_MATRIX_SCHEMA!r}"
            )
        if matrix_entry_count != FEATURE_MATRIX_ENTRY_COUNT:
            errors.append(
                f"feature matrix has {matrix_entry_count!r} entries, expected "
                f"{FEATURE_MATRIX_ENTRY_COUNT}"
            )
        if matrix_sha256 != FEATURE_MATRIX_SHA256:
            errors.append(
                "sealed Phase 14D feature matrix bytes changed: "
                f"{matrix_sha256}"
            )

    forbidden_openings = sorted(
        path.relative_to(root).as_posix()
        for path in (
            root / "transition/phase_14e",
            root / "evidence/phase_14e",
            root / "transition/phase_15",
            root / "evidence/phase_15",
        )
        if path.exists()
    )
    if forbidden_openings:
        errors.append(
            "unapproved phase opening exists: " + ", ".join(forbidden_openings)
        )

    return {
        "audit": "checkpoint-e-release-metadata-and-roadmap",
        "passed": not errors,
        "errors": errors,
        "package_version": __version__,
        "project_version": project_version,
        "converter_contract_version": EXPECTED_CONTRACT_IDENTITIES[
            "converter_contract"
        ],
        "workspace_contract": WORKSPACE_CONTRACT_VERSION,
        "feature_matrix_schema": matrix_schema,
        "feature_matrix_entry_count": matrix_entry_count,
        "feature_matrix_sha256": matrix_sha256,
        "phase14e_opened": any(
            "phase_14e" in relative for relative in forbidden_openings
        ),
        "phase15_opened": any(
            "phase_15" in relative for relative in forbidden_openings
        ),
    }


def audit_release_fingerprint(
    root: Path,
    *,
    required: bool,
) -> dict[str, object]:
    """Validate the late-bound, self-excluding release-tree fingerprint."""

    path = root / RELEASE_FINGERPRINT
    if not path.is_file():
        return {
            "audit": "checkpoint-e-release-fingerprint",
            "passed": not required,
            "skipped": not required,
            "required": required,
            "errors": (
                [f"required release fingerprint is missing: {RELEASE_FINGERPRINT}"]
                if required
                else []
            ),
            "path": RELEASE_FINGERPRINT.as_posix(),
            "present": False,
            "declarations_match": False,
        }

    errors: list[str] = []
    try:
        declaration = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        declaration = {}
        errors.append(f"release fingerprint is not valid UTF-8 JSON: {exc}")
    if not isinstance(declaration, dict):
        errors.append("release fingerprint root must be an object")
        declaration = {}

    tree_sha256: str | None = None
    tree_file_count: int | None = None
    try:
        tree_sha256, tree_file_count = release_tree_hash(root)
    except ReleaseBuildError as exc:
        errors.append(f"cannot compute release-tree fingerprint: {exc}")

    expected_fields = {
        "algorithm": "sha256",
        "domain": FINGERPRINT_DOMAIN,
        "status": "promoted",
        "scope_status": "sealed",
    }
    for key, expected in expected_fields.items():
        if declaration.get(key) != expected:
            errors.append(
                f"release fingerprint {key} is "
                f"{declaration.get(key)!r}, expected {expected!r}"
            )
    value = declaration.get("value")
    if not isinstance(value, str) or len(value) != 64:
        errors.append("release fingerprint value is not a 64-character digest")
    else:
        try:
            int(value, 16)
        except ValueError:
            errors.append("release fingerprint value is not lowercase hexadecimal")
        if value != value.lower():
            errors.append("release fingerprint value is not lowercase hexadecimal")
    if tree_sha256 is not None and value != tree_sha256:
        errors.append(
            "release fingerprint value does not match the self-excluding "
            f"release tree: declared {value!r}, actual {tree_sha256!r}"
        )
    declared_file_count = declaration.get("file_count")
    if (
        tree_file_count is not None
        and declared_file_count != tree_file_count
    ):
        errors.append(
            "release fingerprint file_count does not match the release tree: "
            f"declared {declared_file_count!r}, actual {tree_file_count}"
        )

    return {
        "audit": "checkpoint-e-release-fingerprint",
        "passed": not errors,
        "required": required,
        "errors": errors,
        "path": RELEASE_FINGERPRINT.as_posix(),
        "present": True,
        "algorithm": declaration.get("algorithm"),
        "domain": declaration.get("domain"),
        "status": declaration.get("status"),
        "scope_status": declaration.get("scope_status"),
        "declared_value": value,
        "actual_value": tree_sha256,
        "declared_file_count": declared_file_count,
        "actual_file_count": tree_file_count,
        "declarations_match": not errors,
        "self_excluded_from_tree_hash": True,
    }


def audit_internal_release_records(
    root: Path,
    *,
    required: bool,
) -> dict[str, object]:
    """Check final internal promotion records without creating a hash cycle."""

    missing = sorted(
        relative
        for relative in PROMOTION_REQUIRED_CHECKPOINT_E_FILES
        if not (root / relative).is_file()
    )
    if not required:
        return {
            "audit": "checkpoint-e-internal-release-records",
            "passed": True,
            "skipped": True,
            "required": False,
            "errors": [],
            "missing": missing,
        }

    errors = [
        f"missing promotion record: {relative}" for relative in missing
    ]
    expected_records = (
        (
            "transition/checkpoint_e/manifest.json",
            "pycforge.checkpoint-e-manifest/0.14.4",
        ),
        (
            "evidence/checkpoint_e/release_report.json",
            "pycforge.checkpoint-e-release-report/0.14.4",
        ),
    )
    records: dict[str, object] = {}
    for relative, expected_schema in expected_records:
        path = root / relative
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{relative} is not valid UTF-8 JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{relative} root must be an object")
            continue
        records[relative] = {
            "schema": value.get("schema_version"),
            "status": value.get("status"),
            "scope_status": value.get("scope_status"),
            "version": value.get("version", value.get("release_version")),
        }
        if value.get("schema_version") != expected_schema:
            errors.append(
                f"{relative} schema is {value.get('schema_version')!r}, "
                f"expected {expected_schema!r}"
            )
        if value.get("status") != "promoted":
            errors.append(f"{relative} status is not 'promoted'")
        if value.get("scope_status") != "sealed":
            errors.append(f"{relative} scope_status is not 'sealed'")
        if value.get("version", value.get("release_version")) != CHECKPOINT_E_VERSION:
            errors.append(f"{relative} version is not {CHECKPOINT_E_VERSION}")

    handoff = root / "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt"
    if handoff.is_file() and handoff.stat().st_size < 256:
        errors.append("Checkpoint E handoff is unexpectedly small")

    return {
        "audit": "checkpoint-e-internal-release-records",
        "passed": not errors,
        "required": True,
        "errors": errors,
        "missing": missing,
        "records": records,
    }


def validate_checkpoint_e(
    root: Path = ROOT,
    *,
    predecessor_archive: Path | None = None,
    require_predecessor: bool = False,
    run_fuzz: bool = True,
    fuzz_case_count: int = DEFAULT_FUZZ_CASE_COUNT,
    run_predecessor_equivalence: bool = True,
    mode: str = "focused",
) -> dict[str, object]:
    """Run all independent Checkpoint E validation surfaces."""

    if mode not in {"focused", "promotion", "sealed"}:
        raise ValueError(f"unsupported Checkpoint E validation mode: {mode!r}")
    promotion_requested = mode in {"promotion", "sealed"}
    fingerprint_required = mode == "sealed"
    effective_require_predecessor = require_predecessor or promotion_requested

    missing_files = sorted(
        relative
        for relative in REQUIRED_CHECKPOINT_E_FILES
        if not (root / relative).is_file()
    )
    identities = current_contract_identities()
    identity_mismatches = {
        key: {"expected": expected, "actual": identities.get(key)}
        for key, expected in EXPECTED_CONTRACT_IDENTITIES.items()
        if identities.get(key) != expected
    }
    metadata = audit_checkpoint_metadata(root)
    architecture = audit_architecture_branding_product_boundary(root)
    feature_matrix = audit_feature_matrix(root)
    if run_fuzz:
        fuzz: dict[str, object] = audit_full_supported_subset(
            fuzz_case_count=fuzz_case_count
        )
    else:
        fuzz = {
            "audit": "checkpoint-e-full-supported-subset",
            "passed": True,
            "skipped": True,
            "reason": "explicit validator option",
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }

    resolved_archive = predecessor_archive or locate_predecessor_archive(root)
    if resolved_archive is None:
        predecessor: dict[str, object] = {
            "audit": "sealed-phase14d-predecessor-authentication",
            "passed": not effective_require_predecessor,
            "skipped": not effective_require_predecessor,
            "errors": (
                ["required sealed Phase 14D predecessor archive was not found"]
                if effective_require_predecessor
                else []
            ),
            "expected_name": SEALED_PREDECESSOR_NAME,
            "expected_sha256": SEALED_PREDECESSOR_SHA256,
            "archive_extracted": False,
        }
    else:
        predecessor = authenticate_predecessor_archive(resolved_archive)

    if resolved_archive is None:
        predecessor_equivalence: dict[str, object] = {
            "audit": "sealed-phase14d-exact-behavioral-equivalence",
            "passed": not effective_require_predecessor,
            "skipped": True,
            "errors": (
                ["required sealed Phase 14D predecessor archive was not found"]
                if effective_require_predecessor
                else []
            ),
            "case_count": 0,
            "matched_case_count": 0,
            "promotion_eligible": False,
            "exact_result_json_byte_equivalence": False,
            "archive_authenticated_before_extraction": False,
            "archive_extracted_to_private_temporary_directory": False,
            "python_interpreter_invoked": False,
            "python_isolated_mode": False,
            "python_no_site_mode": False,
            "untrusted_pickle_loaded": False,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    elif not predecessor.get("passed"):
        predecessor_equivalence = {
            "audit": "sealed-phase14d-exact-behavioral-equivalence",
            "passed": False,
            "skipped": True,
            "errors": [
                "predecessor equivalence requires an authenticated archive"
            ],
            "case_count": 0,
            "matched_case_count": 0,
            "promotion_eligible": False,
            "exact_result_json_byte_equivalence": False,
            "archive_authenticated_before_extraction": False,
            "archive_extracted_to_private_temporary_directory": False,
            "python_interpreter_invoked": False,
            "python_isolated_mode": False,
            "python_no_site_mode": False,
            "untrusted_pickle_loaded": False,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    elif not run_predecessor_equivalence:
        predecessor_equivalence = {
            "audit": "sealed-phase14d-exact-behavioral-equivalence",
            "passed": True,
            "skipped": True,
            "reason": "explicit focused-validator option",
            "errors": [],
            "case_count": 0,
            "matched_case_count": 0,
            "promotion_eligible": False,
            "exact_result_json_byte_equivalence": False,
            "archive_authenticated_before_extraction": False,
            "archive_extracted_to_private_temporary_directory": False,
            "python_interpreter_invoked": False,
            "python_isolated_mode": False,
            "python_no_site_mode": False,
            "untrusted_pickle_loaded": False,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    else:
        try:
            predecessor_equivalence = audit_predecessor_equivalence(
                resolved_archive,
                generated_case_count=fuzz_case_count,
            )
        except (ValueError, PredecessorEquivalenceError) as exc:
            predecessor_equivalence = {
                "audit": "sealed-phase14d-exact-behavioral-equivalence",
                "passed": False,
                "errors": [str(exc)],
                "case_count": 0,
                "matched_case_count": 0,
                "promotion_eligible": False,
                "exact_result_json_byte_equivalence": False,
                "archive_authenticated_before_extraction": False,
                "archive_extracted_to_private_temporary_directory": False,
                "python_interpreter_invoked": False,
                "python_isolated_mode": False,
                "python_no_site_mode": False,
                "untrusted_pickle_loaded": False,
                "c_toolchain_invoked": False,
                "generated_c_compiled_or_executed": False,
            }

    internal_release_records = audit_internal_release_records(
        root,
        required=promotion_requested,
    )
    release_fingerprint = audit_release_fingerprint(
        root,
        required=fingerprint_required,
    )
    promotion_missing_files = sorted(
        relative
        for relative in PROMOTION_REQUIRED_CHECKPOINT_E_FILES
        if not (root / relative).is_file()
    )
    sealed_missing_files = sorted(
        relative
        for relative in SEALED_REQUIRED_CHECKPOINT_E_FILES
        if not (root / relative).is_file()
    )
    promotion_blockers = [
        *(
            ["full-supported-subset audit was skipped"]
            if not run_fuzz or fuzz.get("skipped")
            else []
        ),
        *(
            [
                "promotion requires exactly "
                f"{PROMOTION_MINIMUM_GENERATED_CASES} generated cases, got "
                f"{fuzz_case_count}"
            ]
            if fuzz_case_count != PROMOTION_MINIMUM_GENERATED_CASES
            else []
        ),
        *(
            ["executable feature-matrix coverage is incomplete"]
            if not feature_matrix.get("coverage_complete")
            else []
        ),
        *(
            [
                "feature-matrix gate did not execute exactly 69 entries plus "
                "the unlisted default"
            ]
            if (
                feature_matrix.get("matrix_witness_count")
                != FEATURE_MATRIX_ENTRY_COUNT
                or feature_matrix.get("unlisted_default_witness_count") != 1
            )
            else []
        ),
        *(
            [
                "full-supported-subset promotion corpus is not exactly "
                f"{PROMOTION_MINIMUM_TOTAL_CASES} cases"
            ]
            if (
                fuzz.get("fixed_case_count") != 16
                or fuzz.get("generated_case_count")
                != PROMOTION_MINIMUM_GENERATED_CASES
                or fuzz.get("case_count") != PROMOTION_MINIMUM_TOTAL_CASES
            )
            else []
        ),
        *(
            ["generated promotion corpus does not cover every promoted family"]
            if fuzz.get("generated_missing_families")
            else []
        ),
        *(
            ["sealed predecessor is not authenticated"]
            if not predecessor.get("passed")
            else []
        ),
        *(
            ["sealed predecessor equivalence was skipped"]
            if predecessor_equivalence.get("skipped")
            else []
        ),
        *(
            ["sealed predecessor equivalence is not promotion-eligible"]
            if not predecessor_equivalence.get("promotion_eligible")
            else []
        ),
        *(
            ["sealed predecessor equivalence is not exactly 80/80"]
            if (
                predecessor_equivalence.get("case_count")
                != PROMOTION_MINIMUM_TOTAL_CASES
                or predecessor_equivalence.get("matched_case_count")
                != PROMOTION_MINIMUM_TOTAL_CASES
                or not predecessor_equivalence.get(
                    "exact_result_json_byte_equivalence"
                )
            )
            else []
        ),
        *(
            f"missing promotion file: {relative}"
            for relative in promotion_missing_files
        ),
        *internal_release_records.get("errors", []),
    ]
    promotion_requirements_satisfied = not promotion_blockers
    promotion_eligible = (
        promotion_requested and promotion_requirements_satisfied
    )
    sealed_release_eligible = (
        mode == "sealed"
        and promotion_requirements_satisfied
        and release_fingerprint.get("passed") is True
        and not sealed_missing_files
    )

    errors = [
        *(f"missing Checkpoint E file: {relative}" for relative in missing_files),
        *(
            ["frozen converter contract identities changed"]
            if identity_mismatches
            else []
        ),
        *(
            ["Checkpoint E metadata, roadmap, or feature matrix audit failed"]
            if not metadata.get("passed")
            else []
        ),
        *(
            ["architecture/branding/product-boundary audit failed"]
            if not architecture.get("passed")
            else []
        ),
        *(
            ["executable feature-matrix audit failed"]
            if not feature_matrix.get("passed")
            else []
        ),
        *(
            ["full-supported-subset fuzz/metamorphic audit failed"]
            if not fuzz.get("passed")
            else []
        ),
        *(
            ["sealed predecessor authentication failed"]
            if not predecessor.get("passed")
            else []
        ),
        *(
            ["sealed predecessor exact behavioral equivalence failed"]
            if not predecessor_equivalence.get("passed")
            else []
        ),
        *(promotion_blockers if promotion_requested else []),
        *(
            (
                f"missing sealed-release file: {relative}"
                for relative in sealed_missing_files
            )
            if fingerprint_required
            else []
        ),
        *(
            release_fingerprint.get("errors", [])
            if fingerprint_required
            else []
        ),
    ]
    report: dict[str, object] = {
        "schema": "pycforge.checkpoint-e-validation-report/1",
        "validator": "checkpoint-e",
        "mode": mode,
        "passed": not errors,
        "errors": errors,
        "missing_required_files": missing_files,
        "promotion_missing_files": promotion_missing_files,
        "sealed_missing_files": sealed_missing_files,
        "contract_identities": identities,
        "identity_mismatches": identity_mismatches,
        "metadata_roadmap_feature_matrix": metadata,
        "architecture_branding_product_boundary": architecture,
        "executable_feature_matrix": feature_matrix,
        "full_supported_subset": fuzz,
        "sealed_predecessor": predecessor,
        "sealed_predecessor_equivalence": predecessor_equivalence,
        "internal_release_records": internal_release_records,
        "release_fingerprint": release_fingerprint,
        "promotion_minimum_generated_case_count": (
            PROMOTION_MINIMUM_GENERATED_CASES
        ),
        "promotion_minimum_total_case_count": PROMOTION_MINIMUM_TOTAL_CASES,
        "promotion_blockers": promotion_blockers,
        "promotion_requirements_satisfied": (
            promotion_requirements_satisfied
        ),
        "promotion_eligible": promotion_eligible,
        "sealed_release_eligible": sealed_release_eligible,
        "c_toolchain_invoked": TOOLCHAIN_INVOKED,
        "generated_c_compiled_or_executed": GENERATED_C_COMPILED_OR_EXECUTED,
    }
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Checkpoint E without compiling or executing generated C."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("focused", "promotion", "sealed"),
        default="focused",
        help=(
            "focused permits explicit skips; promotion requires the complete "
            "64-case hardening corpus and predecessor gate; sealed also "
            "requires the assigned release-tree fingerprint"
        ),
    )
    parser.add_argument(
        "--predecessor-archive",
        type=Path,
        help="path to the sealed Phase 14D source archive",
    )
    parser.add_argument(
        "--require-predecessor",
        action="store_true",
        help="fail if the sealed Phase 14D archive cannot be located",
    )
    parser.add_argument(
        "--skip-fuzz",
        action="store_true",
        help="skip the long full-subset audit (intended for focused tests only)",
    )
    parser.add_argument(
        "--fuzz-cases",
        type=int,
        default=DEFAULT_FUZZ_CASE_COUNT,
        help="number of deterministic generated cases",
    )
    parser.add_argument(
        "--skip-predecessor-equivalence",
        action="store_true",
        help=(
            "skip isolated predecessor comparison (intended for focused "
            "tests only; never for promotion)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="also write the canonical JSON report to this path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = validate_checkpoint_e(
            predecessor_archive=args.predecessor_archive,
            require_predecessor=args.require_predecessor,
            run_fuzz=not args.skip_fuzz,
            fuzz_case_count=args.fuzz_cases,
            run_predecessor_equivalence=(
                not args.skip_predecessor_equivalence
            ),
            mode=args.mode,
        )
    except (ValueError, PredecessorEquivalenceError) as exc:
        report = {
            "validator": "checkpoint-e",
            "passed": False,
            "errors": [str(exc)],
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError as exc:
            report["passed"] = False
            report.setdefault("errors", []).append(
                f"cannot write validator report: {exc}"
            )
            rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
