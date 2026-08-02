"""Prove exact source-only equivalence with the sealed Phase 14D release.

The predecessor is authenticated before it is opened, extracted into a
private temporary directory with explicit member checks, and imported only by
an isolated Python child process.  The child converts source manifests and
returns ``result_to_json`` text.  No generated C is compiled or executed and
no native toolchain is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import PythonToCConverter  # noqa: E402
from pycforge.converter.core.request import ObservationOptions  # noqa: E402
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.laboratory.checkpoint_e import (  # noqa: E402
    FUZZ_SEED,
    SupportedSubsetCase,
    fixed_supported_subset_cases,
    generated_fuzz_cases,
)


SEALED_PREDECESSOR_NAME = "pycforge_phase_14d_v0_14_3.tar.gz"
SEALED_PREDECESSOR_ROOT = "pycforge_phase_14d_v0_14_3"
SEALED_PREDECESSOR_SIZE = 1_282_543
SEALED_PREDECESSOR_SHA256 = (
    "13228fe8e40c89335cf1bb6c44a2ebb94bc581e287873520b7c530984053c4f1"
)

CORPUS_SCHEMA = "pycforge.checkpoint-e-predecessor-corpus/1"
RUNNER_RESULT_SCHEMA = "pycforge.checkpoint-e-predecessor-results/1"
DEFAULT_PROMOTION_GENERATED_CASE_COUNT = 64
PROMOTION_FIXED_CASE_IDS = (
    "fixed-literals",
    "fixed-arithmetic",
    "fixed-positional-call",
    "fixed-if-else",
    "fixed-while",
    "fixed-range-for",
    "fixed-list",
    "fixed-tuple",
    "fixed-dict",
    "fixed-module-bundle",
    "fixed-record",
    "fixed-floor-arithmetic",
    "fixed-boolean-region",
    "fixed-comparison-region",
    "fixed-keyword-call",
    "fixed-keyword-only-call",
)
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_CORPUS_BYTES = 4 * 1024 * 1024
MAX_RUNNER_OUTPUT_BYTES = 64 * 1024 * 1024
DEFAULT_RUNNER_TIMEOUT_SECONDS = 180

C_TOOLCHAIN_INVOKED = False
GENERATED_C_COMPILED_OR_EXECUTED = False


class PredecessorEquivalenceError(RuntimeError):
    """Raised when safe predecessor inspection or isolated conversion fails."""


def canonical_json_bytes(value: object) -> bytes:
    """Return stable UTF-8 JSON with one final newline."""

    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_member_path(name: str, *, is_directory: bool) -> PurePosixPath:
    if "\x00" in name or "\\" in name:
        raise PredecessorEquivalenceError(
            f"unsafe sealed predecessor member path: {name!r}"
        )
    normalized_text = name[:-1] if is_directory and name.endswith("/") else name
    path = PurePosixPath(normalized_text)
    if (
        not normalized_text
        or path.is_absolute()
        or path.as_posix() != normalized_text
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0] != SEALED_PREDECESSOR_ROOT
    ):
        raise PredecessorEquivalenceError(
            f"unsafe sealed predecessor member path: {name!r}"
        )
    return path


def _authenticated_members(
    archive_path: Path,
) -> tuple[bytes, list[tarfile.TarInfo], dict[str, object]]:
    """Authenticate exact archive identity and return fully checked members."""

    path = Path(archive_path)
    errors: list[str] = []
    try:
        archive_mode = path.lstat().st_mode
    except OSError:
        archive_mode = None
    if archive_mode is None or not stat.S_ISREG(archive_mode):
        errors.append(f"sealed predecessor is not a file: {path}")
    if archive_mode is not None and stat.S_ISLNK(archive_mode):
        errors.append("sealed predecessor archive must not be a symbolic link")
    if path.name != SEALED_PREDECESSOR_NAME:
        errors.append(
            "sealed predecessor filename mismatch: expected "
            f"{SEALED_PREDECESSOR_NAME}, got {path.name}"
        )

    actual_size: int | None = None
    actual_sha256: str | None = None
    archive_bytes = b""
    if archive_mode is not None and stat.S_ISREG(archive_mode):
        try:
            archive_bytes = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read sealed predecessor archive: {exc}")
        actual_size = len(archive_bytes)
        if actual_size != SEALED_PREDECESSOR_SIZE:
            errors.append(
                "sealed predecessor size mismatch: expected "
                f"{SEALED_PREDECESSOR_SIZE}, got {actual_size}"
            )
        actual_sha256 = sha256_bytes(archive_bytes)
        if actual_sha256 != SEALED_PREDECESSOR_SHA256:
            errors.append(
                "sealed predecessor SHA-256 mismatch: expected "
                f"{SEALED_PREDECESSOR_SHA256}, got {actual_sha256}"
            )
    if errors:
        raise PredecessorEquivalenceError("; ".join(errors))

    try:
        with tarfile.open(
            fileobj=io.BytesIO(archive_bytes),
            mode="r:gz",
        ) as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise PredecessorEquivalenceError(
            f"sealed predecessor is not a readable gzip tar: {exc}"
        ) from exc

    names: set[str] = set()
    normalized_names: set[str] = set()
    roots: set[str] = set()
    regular_file_count = 0
    total_regular_bytes = 0
    for member in members:
        if member.name in names:
            raise PredecessorEquivalenceError(
                f"duplicate sealed predecessor member: {member.name}"
            )
        names.add(member.name)
        if not (member.isfile() or member.isdir()):
            raise PredecessorEquivalenceError(
                "sealed predecessor contains a link or special member: "
                f"{member.name}"
            )
        relative = _safe_member_path(
            member.name,
            is_directory=member.isdir(),
        )
        normalized = relative.as_posix()
        if normalized in normalized_names:
            raise PredecessorEquivalenceError(
                f"duplicate normalized predecessor member: {normalized}"
            )
        normalized_names.add(normalized)
        roots.add(relative.parts[0])
        if member.isfile():
            regular_file_count += 1
            if member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_BYTES:
                raise PredecessorEquivalenceError(
                    f"sealed predecessor member has unsafe size: {member.name}"
                )
            total_regular_bytes += member.size
            if total_regular_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                raise PredecessorEquivalenceError(
                    "sealed predecessor exceeds the extraction byte budget"
                )

    if roots != {SEALED_PREDECESSOR_ROOT}:
        raise PredecessorEquivalenceError(
            "sealed predecessor archive root mismatch"
        )
    if regular_file_count == 0:
        raise PredecessorEquivalenceError(
            "sealed predecessor contains no regular files"
        )

    return archive_bytes, members, {
        "archive_name": path.name,
        "archive_size": actual_size,
        "archive_sha256": actual_sha256,
        "archive_root": SEALED_PREDECESSOR_ROOT,
        "member_count": len(members),
        "regular_file_count": regular_file_count,
        "uncompressed_regular_bytes": total_regular_bytes,
    }


def _extract_authenticated_archive(
    archive_path: Path,
    destination: Path,
) -> tuple[Path, dict[str, object]]:
    """Extract checked regular files without using ``TarFile.extract*``."""

    archive_bytes, members, authentication = _authenticated_members(
        archive_path
    )
    destination = Path(destination).resolve()
    if not destination.is_dir():
        raise PredecessorEquivalenceError(
            "private predecessor extraction destination is not a directory"
        )
    mode = stat.S_IMODE(destination.stat().st_mode)
    if mode & 0o077:
        raise PredecessorEquivalenceError(
            "private predecessor extraction directory has broad permissions"
        )

    with tarfile.open(
        fileobj=io.BytesIO(archive_bytes),
        mode="r:gz",
    ) as archive:
        for member in members:
            relative = _safe_member_path(
                member.name,
                is_directory=member.isdir(),
            )
            target = destination.joinpath(*relative.parts)
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise PredecessorEquivalenceError(
                    f"predecessor member escaped extraction root: {member.name}"
                ) from exc
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise PredecessorEquivalenceError(
                    f"cannot read sealed predecessor member: {member.name}"
                )
            try:
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            except OSError as exc:
                raise PredecessorEquivalenceError(
                    f"cannot extract sealed predecessor member: {member.name}"
                ) from exc
            os.chmod(target, 0o600)

    project_root = destination / SEALED_PREDECESSOR_ROOT
    required = (
        project_root / "pycforge" / "__init__.py",
        project_root
        / "pycforge"
        / "converter"
        / "core"
        / "serialization.py",
    )
    if not all(path.is_file() and not path.is_symlink() for path in required):
        raise PredecessorEquivalenceError(
            "sealed predecessor lacks required source-only converter files"
        )
    return project_root, authentication


_ISOLATED_RUNNER_SOURCE = r'''
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


CORPUS_SCHEMA = "pycforge.checkpoint-e-predecessor-corpus/1"
RESULT_SCHEMA = "pycforge.checkpoint-e-predecessor-results/1"


def canonical_bytes(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def fail(message):
    sys.stderr.write(str(message) + "\n")
    raise SystemExit(2)


if not sys.flags.isolated:
    fail("predecessor runner requires Python isolated mode")
if len(sys.argv) != 2:
    fail("predecessor runner requires exactly one source-root argument")

project_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(project_root))

import pycforge
from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_json


package_path = Path(pycforge.__file__).resolve()
try:
    package_path.relative_to(project_root)
except ValueError:
    fail("predecessor import escaped the authenticated source root")
if pycforge.__version__ != "0.14.3":
    fail("authenticated predecessor package version is not 0.14.3")

try:
    raw = sys.stdin.buffer.read()
    corpus = json.loads(raw)
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    fail("cannot read canonical predecessor corpus: " + str(exc))
if canonical_bytes(corpus) != raw:
    fail("predecessor corpus is not canonical JSON")
if not isinstance(corpus, dict) or corpus.get("schema") != CORPUS_SCHEMA:
    fail("predecessor corpus schema mismatch")
cases = corpus.get("cases")
if not isinstance(cases, list):
    fail("predecessor corpus cases must be a list")

converter = PythonToCConverter()
rows = []
for item in cases:
    if not isinstance(item, dict):
        fail("predecessor case must be an object")
    if set(item) != {"case_id", "family", "primary", "companions"}:
        fail("predecessor case fields mismatch")
    primary = item["primary"]
    companions = item["companions"]
    if (
        not isinstance(item["case_id"], str)
        or not isinstance(item["family"], str)
        or not isinstance(primary, dict)
        or set(primary) != {"logical_name", "module_id", "text"}
        or not isinstance(companions, list)
    ):
        fail("predecessor case shape mismatch")
    documents = []
    for document in [primary, *companions]:
        if (
            not isinstance(document, dict)
            or set(document) != {"logical_name", "module_id", "text"}
            or not all(isinstance(document[key], str) for key in document)
        ):
            fail("predecessor source document shape mismatch")
        documents.append(
            SourceDocumentInput(
                document["logical_name"],
                document["text"],
                document["module_id"],
            )
        )
    request = ConversionRequest(
        SourceBundle(documents[0], tuple(documents[1:]))
    )
    result_text = result_to_json(
        converter.convert(
            request,
            observation=ObservationOptions("Full", True),
        )
    )
    result_bytes = result_text.encode("utf-8")
    rows.append(
        {
            "case_id": item["case_id"],
            "result_json": result_text,
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
            "result_size": len(result_bytes),
        }
    )

output = {
    "schema": RESULT_SCHEMA,
    "isolated": bool(sys.flags.isolated),
    "no_site": bool(sys.flags.no_site),
    "package_version": pycforge.__version__,
    "case_count": len(rows),
    "rows": rows,
    "c_toolchain_invoked": False,
    "generated_c_compiled_or_executed": False,
}
sys.stdout.buffer.write(canonical_bytes(output))
'''


def promotion_corpus(
    *,
    seed: int = FUZZ_SEED,
    generated_case_count: int = DEFAULT_PROMOTION_GENERATED_CASE_COUNT,
) -> tuple[SupportedSubsetCase, ...]:
    """Return the frozen 16-case promotion set plus requested generated cases.

    The broader feature-matrix audit may grow independent boundary witnesses.
    Promotion equivalence deliberately retains the 16 fixed witnesses recorded
    by the Checkpoint E 80-case promotion evidence.
    """

    all_fixed = fixed_supported_subset_cases()
    available = {case.case_id: case for case in all_fixed}
    if len(available) != len(all_fixed):
        raise PredecessorEquivalenceError(
            "Checkpoint E fixed corpus contains duplicate case identifiers"
        )
    missing = [
        case_id for case_id in PROMOTION_FIXED_CASE_IDS if case_id not in available
    ]
    if missing:
        raise PredecessorEquivalenceError(
            "Checkpoint E promotion corpus lacks fixed cases: "
            + ", ".join(missing)
        )
    promotion_id_set = set(PROMOTION_FIXED_CASE_IDS)
    actual_order = tuple(
        case.case_id for case in all_fixed if case.case_id in promotion_id_set
    )
    if actual_order != PROMOTION_FIXED_CASE_IDS:
        raise PredecessorEquivalenceError(
            "Checkpoint E fixed promotion corpus ordering changed: "
            + ", ".join(actual_order)
        )
    fixed = tuple(available[case_id] for case_id in PROMOTION_FIXED_CASE_IDS)
    return (
        *fixed,
        *generated_fuzz_cases(seed=seed, count=generated_case_count),
    )


def _corpus_payload(
    cases: Sequence[SupportedSubsetCase],
    *,
    seed: int,
    generated_case_count: int,
) -> dict[str, object]:
    return {
        "schema": CORPUS_SCHEMA,
        "seed": seed,
        "generated_case_count": generated_case_count,
        "cases": [case.manifest() for case in cases],
    }


def _length_prefixed_digest(values: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def compare_exact_results(
    case_ids: Sequence[str],
    candidate_results: Mapping[str, bytes],
    predecessor_rows: object,
) -> dict[str, object]:
    """Compare exact UTF-8 result bytes and independently supplied digests."""

    errors: list[str] = []
    mismatches: list[dict[str, object]] = []
    predecessor_results: dict[str, bytes] = {}
    rows = predecessor_rows if isinstance(predecessor_rows, list) else []
    if not isinstance(predecessor_rows, list):
        errors.append("predecessor runner rows are not a list")

    for row in rows:
        if not isinstance(row, dict):
            errors.append("predecessor runner row is not an object")
            continue
        case_id = row.get("case_id")
        result_text = row.get("result_json")
        result_sha256 = row.get("result_sha256")
        result_size = row.get("result_size")
        if (
            not isinstance(case_id, str)
            or not isinstance(result_text, str)
            or not isinstance(result_sha256, str)
            or not isinstance(result_size, int)
        ):
            errors.append("predecessor runner row fields are invalid")
            continue
        if case_id in predecessor_results:
            errors.append(f"duplicate predecessor result case: {case_id}")
            continue
        result_bytes = result_text.encode("utf-8")
        if len(result_bytes) != result_size:
            errors.append(f"{case_id}: predecessor result size is inconsistent")
        if sha256_bytes(result_bytes) != result_sha256:
            errors.append(f"{case_id}: predecessor result digest is inconsistent")
        predecessor_results[case_id] = result_bytes

    expected_ids = list(case_ids)
    if len(set(expected_ids)) != len(expected_ids):
        errors.append("candidate corpus contains duplicate case identifiers")
    expected_set = set(expected_ids)
    missing = sorted(expected_set - set(predecessor_results))
    unexpected = sorted(set(predecessor_results) - expected_set)
    if missing:
        errors.append(
            "predecessor results omit cases: " + ", ".join(missing)
        )
    if unexpected:
        errors.append(
            "predecessor results contain unexpected cases: "
            + ", ".join(unexpected)
        )
    if set(candidate_results) != expected_set:
        errors.append("candidate result identifiers do not match the corpus")

    matched = 0
    case_digests: list[dict[str, object]] = []
    for case_id in expected_ids:
        candidate = candidate_results.get(case_id)
        predecessor = predecessor_results.get(case_id)
        candidate_sha256 = (
            sha256_bytes(candidate) if candidate is not None else None
        )
        predecessor_sha256 = (
            sha256_bytes(predecessor) if predecessor is not None else None
        )
        exact_match = (
            candidate is not None
            and predecessor is not None
            and candidate == predecessor
        )
        case_digests.append(
            {
                "case_id": case_id,
                "candidate_size": (
                    len(candidate) if candidate is not None else None
                ),
                "predecessor_size": (
                    len(predecessor) if predecessor is not None else None
                ),
                "candidate_sha256": candidate_sha256,
                "predecessor_sha256": predecessor_sha256,
                "exact_match": exact_match,
            }
        )
        if exact_match:
            matched += 1
        elif candidate is not None and predecessor is not None:
            mismatches.append(
                {
                    "case_id": case_id,
                    "candidate_size": len(candidate),
                    "predecessor_size": len(predecessor),
                    "candidate_sha256": candidate_sha256,
                    "predecessor_sha256": predecessor_sha256,
                }
            )

    candidate_ordered = [
        candidate_results[case_id]
        for case_id in expected_ids
        if case_id in candidate_results
    ]
    predecessor_ordered = [
        predecessor_results[case_id]
        for case_id in expected_ids
        if case_id in predecessor_results
    ]
    return {
        "passed": not errors and not mismatches and matched == len(expected_ids),
        "errors": errors,
        "case_count": len(expected_ids),
        "matched_case_count": matched,
        "mismatched_case_count": len(mismatches),
        "missing_case_count": len(missing),
        "unexpected_case_count": len(unexpected),
        "case_digests": case_digests,
        "mismatches": mismatches,
        "candidate_results_sha256": _length_prefixed_digest(candidate_ordered),
        "predecessor_results_sha256": _length_prefixed_digest(
            predecessor_ordered
        ),
        "exact_result_json_byte_equivalence": (
            not errors and not mismatches and matched == len(expected_ids)
        ),
    }


def audit_predecessor_equivalence(
    archive_path: Path,
    *,
    seed: int = FUZZ_SEED,
    generated_case_count: int = DEFAULT_PROMOTION_GENERATED_CASE_COUNT,
    timeout_seconds: int = DEFAULT_RUNNER_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Run the authenticated predecessor and compare exact serialized results."""

    if generated_case_count < 0:
        raise ValueError("generated_case_count must be non-negative")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    cases = promotion_corpus(
        seed=seed,
        generated_case_count=generated_case_count,
    )
    corpus = _corpus_payload(
        cases,
        seed=seed,
        generated_case_count=generated_case_count,
    )
    corpus_bytes = canonical_json_bytes(corpus)
    if len(corpus_bytes) > MAX_CORPUS_BYTES:
        raise PredecessorEquivalenceError(
            "Checkpoint E predecessor corpus exceeds its byte budget"
        )

    base_report: dict[str, object] = {
        "audit": "sealed-phase14d-exact-behavioral-equivalence",
        "passed": False,
        "errors": [],
        "seed": seed,
        "fixed_case_count": len(PROMOTION_FIXED_CASE_IDS),
        "generated_case_count": generated_case_count,
        "case_count": len(cases),
        "promotion_minimum_generated_case_count": (
            DEFAULT_PROMOTION_GENERATED_CASE_COUNT
        ),
        "promotion_minimum_case_count": (
            len(PROMOTION_FIXED_CASE_IDS)
            + DEFAULT_PROMOTION_GENERATED_CASE_COUNT
        ),
        "promotion_eligible": False,
        "corpus_schema": CORPUS_SCHEMA,
        "corpus_size": len(corpus_bytes),
        "corpus_sha256": sha256_bytes(corpus_bytes),
        "runner_result_schema": RUNNER_RESULT_SCHEMA,
        "runner_mode": "python-isolated",
        "python_command_flags": ["-I", "-S"],
        "native_toolchain_commands": [],
        "python_isolated_mode": False,
        "python_no_site_mode": False,
        "python_interpreter_invoked": False,
        "archive_authenticated_before_extraction": False,
        "archive_extracted_to_private_temporary_directory": False,
        "temporary_extraction_removed": False,
        "untrusted_pickle_loaded": False,
        "c_toolchain_invoked": C_TOOLCHAIN_INVOKED,
        "generated_c_compiled_or_executed": GENERATED_C_COMPILED_OR_EXECUTED,
    }

    try:
        with tempfile.TemporaryDirectory(
            prefix="pycforge-checkpoint-e-predecessor-"
        ) as temporary:
            private_root = Path(temporary)
            os.chmod(private_root, 0o700)
            project_root, authentication = _extract_authenticated_archive(
                Path(archive_path),
                private_root,
            )
            base_report["archive_authenticated_before_extraction"] = True
            base_report[
                "archive_extracted_to_private_temporary_directory"
            ] = True
            base_report["predecessor_archive"] = authentication

            runner_path = private_root / "_checkpoint_e_predecessor_runner.py"
            runner_path.write_text(
                _ISOLATED_RUNNER_SOURCE,
                encoding="utf-8",
                newline="\n",
            )
            os.chmod(runner_path, 0o600)

            base_report["python_interpreter_invoked"] = True
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(runner_path),
                    str(project_root),
                ],
                input=corpus_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=private_root,
                check=False,
                timeout=timeout_seconds,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.decode(
                    "utf-8",
                    errors="backslashreplace",
                ).strip()
                raise PredecessorEquivalenceError(
                    "isolated predecessor runner failed"
                    + (f": {stderr}" if stderr else "")
                )
            if len(completed.stdout) > MAX_RUNNER_OUTPUT_BYTES:
                raise PredecessorEquivalenceError(
                    "isolated predecessor runner output exceeds its byte budget"
                )
            try:
                runner_output = json.loads(completed.stdout)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise PredecessorEquivalenceError(
                    f"isolated predecessor runner returned invalid JSON: {exc}"
                ) from exc
            if canonical_json_bytes(runner_output) != completed.stdout:
                raise PredecessorEquivalenceError(
                    "isolated predecessor runner output is not canonical JSON"
                )
            if (
                not isinstance(runner_output, dict)
                or runner_output.get("schema") != RUNNER_RESULT_SCHEMA
                or runner_output.get("package_version") != "0.14.3"
                or runner_output.get("case_count") != len(cases)
                or runner_output.get("isolated") is not True
                or runner_output.get("no_site") is not True
                or runner_output.get("c_toolchain_invoked") is not False
                or runner_output.get("generated_c_compiled_or_executed")
                is not False
            ):
                raise PredecessorEquivalenceError(
                    "isolated predecessor runner contract mismatch"
                )
            base_report["python_isolated_mode"] = True
            base_report["python_no_site_mode"] = True

            observation = ObservationOptions("Full", True)
            converter = PythonToCConverter()
            candidate_results = {
                case.case_id: result_to_json(
                    converter.convert(
                        case.request(),
                        observation=observation,
                    )
                ).encode("utf-8")
                for case in cases
            }
            comparison = compare_exact_results(
                [case.case_id for case in cases],
                candidate_results,
                runner_output.get("rows"),
            )
            base_report.update(comparison)
    except (
        OSError,
        subprocess.SubprocessError,
        PredecessorEquivalenceError,
    ) as exc:
        errors = base_report.setdefault("errors", [])
        if isinstance(errors, list):
            errors.append(str(exc))
    finally:
        base_report["temporary_extraction_removed"] = True

    base_report["passed"] = bool(
        base_report.get("exact_result_json_byte_equivalence")
        and not base_report.get("errors")
        and base_report.get("archive_authenticated_before_extraction")
        and base_report.get("python_isolated_mode")
        and base_report.get("c_toolchain_invoked") is False
        and base_report.get("generated_c_compiled_or_executed") is False
    )
    base_report["promotion_eligible"] = bool(
        base_report["passed"]
        and generated_case_count >= DEFAULT_PROMOTION_GENERATED_CASE_COUNT
        and len(cases)
        >= len(PROMOTION_FIXED_CASE_IDS)
        + DEFAULT_PROMOTION_GENERATED_CASE_COUNT
    )
    return base_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Checkpoint E with the authenticated Phase 14D source "
            "release without compiling or executing generated C."
        )
    )
    parser.add_argument(
        "--predecessor-archive",
        required=True,
        type=Path,
        help="path to pycforge_phase_14d_v0_14_3.tar.gz",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=FUZZ_SEED,
        help="deterministic generated-corpus seed",
    )
    parser.add_argument(
        "--generated-cases",
        type=int,
        default=DEFAULT_PROMOTION_GENERATED_CASE_COUNT,
        help="number of generated cases in addition to the 16 fixed cases",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = audit_predecessor_equivalence(
            args.predecessor_archive,
            seed=args.seed,
            generated_case_count=args.generated_cases,
        )
    except (ValueError, PredecessorEquivalenceError) as exc:
        report = {
            "audit": "sealed-phase14d-exact-behavioral-equivalence",
            "passed": False,
            "errors": [str(exc)],
            "untrusted_pickle_loaded": False,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        }
    print(canonical_json_bytes(report).decode("utf-8"), end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
