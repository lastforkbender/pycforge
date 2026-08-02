"""Authenticate and validate the bounded PyCForge Phase 14D candidate.

The validator independently checks exact required keyword-only direct-call
binding, historical Phase 14C compatibility, and release artifacts.  It has no
compiler, linker, loader, foreign-function, or generated-C execution path.
"""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tarfile
import tomllib
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import (  # noqa: E402
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
    __version__,
)
from pycforge.converter.analysis.validation import validate_analysis_payload  # noqa: E402
from pycforge.converter.c_output import validate_c_text  # noqa: E402
from pycforge.converter.contracts.configuration import (  # noqa: E402
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    DEFAULT_SEMANTIC_POLICY,
    DEFAULT_TARGET_CONTRACT,
    PHASE14C_RENDERER,
    PHASE14C_RULE_SET,
)
from pycforge.converter.contracts.versions import (  # noqa: E402
    C_IR_SCHEMA,
    CONDITIONAL_FACT_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    KEYWORD_CALL_FACT_SCHEMA,
    KEYWORD_ONLY_CALL_FACT_SCHEMA,
    MODULE_FACT_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14C_C_IR_SCHEMA,
    PHASE14C_CONVERSION_PLAN_SCHEMA,
    PHASE14C_CONVERSION_SUMMARY_SCHEMA,
    PHASE14C_DECISION_TRACE_SCHEMA,
    PHASE14C_GENERATED_C_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.cancellation import CancellationToken  # noqa: E402
from pycforge.converter.core.request import ObservationOptions  # noqa: E402
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.converter.keyword_only_calls import (  # noqa: E402
    KEYWORD_ONLY_CALL_KEY_DOMAIN,
    KEYWORD_ONLY_CALL_LOWERING_SHAPE,
    KEYWORD_ONLY_CALL_OBLIGATIONS,
    KEYWORD_ONLY_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_ONLY_CALL_RULE_ID,
    KEYWORD_ONLY_CALL_RULE_VERSION,
    KEYWORD_ONLY_CALL_TABLE_DEPENDENCIES,
    KEYWORD_ONLY_CALL_TABLE_ID,
    KeywordOnlyCallValidationCanceled,
    validate_keyword_only_call_binding_facts,
)
from pycforge.converter.support_templates import default_helper_registry  # noqa: E402
from pycforge.laboratory import audits as laboratory_audits  # noqa: E402


RELEASE_VERSION = "0.14.3"
MINI_PHASE = "14D"
PREDECESSOR_VERSION = "0.14.2"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_14c_v0_14_2.tar.gz"
PREDECESSOR_ARCHIVE_SIZE = 1_181_034
PREDECESSOR_ARCHIVE_SHA256 = (
    "1eb9666866f38dc80993a6f39175a0d98fdc1634f3aa3ab1eeb3dded2992ffb8"
)
PREDECESSOR_TREE_SHA256 = (
    "be433ef7a46bbb208efe82087b9ef924fad48eba42e42330c7964894a269bcb4"
)
PREDECESSOR_CONVERTER_SHA256 = (
    "ba4457158430bce7fb5094f68e1b07718bd168ca96e22310193efe45bd0d882b"
)
PREDECESSOR_FINGERPRINT = PurePosixPath(
    "transition/phase_14c/release_fingerprint.json"
)
PREDECESSOR_WHEEL_NAME = "pycforge-0.14.2-py3-none-any.whl"
PREDECESSOR_WHEEL_SIZE = 309_077
PREDECESSOR_WHEEL_SHA256 = (
    "6e14d24742e4bfff4017320ebdb04b35117c18fa95d97499560875a764feb4b5"
)
WHEEL_NAME = "pycforge-0.14.3-py3-none-any.whl"
SOURCE_ARCHIVE_NAME = "pycforge_phase_14d_v0_14_3.tar.gz"
REPRODUCIBLE_BUILD_EPOCH = 1_700_000_000
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
HELPER_REGISTRY_SHA256 = (
    "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
)
SEALED_TRANSITION_SUBTREE_IDENTITIES: Mapping[str, tuple[str, str]] = {
    "sealed_phase14a_transition_subtree_sha256": (
        "transition/phase_14",
        "cb92282a063d72c22b6db41cd2c0d2da8b7bdb8cb3c5a3290530744a22d6fe8a",
    ),
    "sealed_phase14b_transition_subtree_sha256": (
        "transition/phase_14b",
        "caddcbe153d005da9d67c14e182ecb6c6bde0e6e7a161dd50807a78aed7cd9e8",
    ),
    "sealed_phase14c_transition_subtree_sha256": (
        "transition/phase_14c",
        "95e5528fc7dca898a7d6883aed101d3a4c5fca5ef53988960307c50f610d04c5",
    ),
}
EXPECTED_RELEASE_TEST_COUNTS: Mapping[str, int] = {
    "discovered": 539,
    "passed": 524,
    "skipped": 15,
    "failed": 0,
    "phase14d_discovered": 65,
    "phase14d_passed": 65,
    "phase14d_failed": 0,
}
EXPECTED_MANIFEST_TEST_COUNTS: Mapping[str, int] = {
    "required_tests": 539,
    "discovered_tests": 539,
    "passed_tests": 524,
    "skipped_tests": 15,
    "failed_tests": 0,
    "phase14d_tests": 65,
    "phase14d_tests_passed": 65,
    "phase14d_tests_failed": 0,
}
PHASE14C_KEYWORD_C_SHA256 = (
    "1517720ffbc3559c02ff82823cffd172585c2a31e9944f14ee25fd4189dccf35"
)
PHASE14C_KEYWORD_OUTPUT_SHA256 = (
    "3c2508b5a9523f6f0d286d73be7583f7d8dbe340a4ff4dcc6017f7cc09c788f9"
)
RELEASE_FINGERPRINT = PurePosixPath("transition/phase_14d/release_fingerprint.json")
FINGERPRINT_DOMAIN = "pycforge-phase-14d-release-tree-v1"
TOOLCHAIN_INVOKED = False
RELEASE_FINGERPRINT_EXCLUDES = (
    RELEASE_FINGERPRINT.as_posix(),
    "__pycache__ directories",
    ".pytest_cache directories",
    "build directories",
    "dist directories",
    "*.pyc",
    "*.pyo",
)

PROMOTED_REQUIRED_FILES = frozenset(
    {
        "README.md",
        "CURRENT_STATE.md",
        "CHANGELOG.md",
        "PyCForge_Phase_14D_v0_14_3_Project_Handoff.txt",
        "specifications/phase14d_required_keyword_only_calls.md",
        "transition/phase_14d/baseline_fingerprint.json",
        "transition/phase_14d/entry_criteria.md",
        "transition/phase_14d/required_keyword_only_calls_decision.md",
        "transition/phase_14d/breadth_and_change_budgets.md",
        "transition/phase_14d/rollback_conditions.md",
        "transition/phase_14d/opening_evidence.md",
        "transition/phase_14d/gate_evidence.md",
        "transition/phase_14d/manifest.json",
        "transition/phase_14d/release_fingerprint.json",
        "evidence/phase_14d/conversion_debt.json",
        "evidence/phase_14d/entry_report.json",
        "evidence/phase_14d/release_report.json",
        "pycforge/converter/keyword_only_calls/__init__.py",
        "pycforge/converter/keyword_only_calls/analysis.py",
        "pycforge/converter/keyword_only_calls/lowering.py",
        "pycforge/converter/keyword_only_calls/model.py",
        "pycforge/converter/keyword_only_calls/validation.py",
        "pycforge/laboratory/keyword_only_audit.py",
        "tests/test_phase14d_keyword_only_contracts.py",
        "tests/test_phase14d_keyword_only_analysis.py",
        "tests/test_phase14d_keyword_only_lowering.py",
        "tests/test_phase14d_keyword_only_hardening.py",
        "tests/test_phase14d_cumulative_eligibility.py",
        "tests/test_validate_phase14d.py",
        "tools/validate_phase14d.py",
    }
)


EXPECTED_CONTRACTS: Mapping[str, object] = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "numeric_facts": "fact-table/0.14",
    "conditional_facts": "fact-table/0.14.1",
    "keyword_call_facts": "fact-table/0.14.2",
    "keyword_only_call_facts": "fact-table/0.14.3",
    "conversion_plan": "conversion-plan/0.14.3",
    "c_ir": "c-ir/0.14.3",
    "generated_c": "generated-c/0.14.3",
    "conversion_summary": "pycforge.conversion-summary/0.14.3",
    "decision_trace": "pycforge.decision-trace/0.14.3",
    "result_serialization": "0.5",
    "rule_set": "phase14-required-keyword-only-calls-v0.14.3",
    "renderer": "c-renderer-v0.14.3",
    "semantic_policy": "strict-source-v1",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "numeric_policy": "phase14-proved-floor-arithmetic-v0.14",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
}

EXPECTED_PHASE14C_CONTRACTS: Mapping[str, object] = {
    "keyword_call_facts": "fact-table/0.14.2",
    "conversion_plan": "conversion-plan/0.14.2",
    "c_ir": "c-ir/0.14.2",
    "generated_c": "generated-c/0.14.2",
    "conversion_summary": "pycforge.conversion-summary/0.14.2",
    "decision_trace": "pycforge.decision-trace/0.14.2",
    "rule_set": "phase14-direct-keyword-calls-v0.14.2",
    "renderer": "c-renderer-v0.14.2",
}

KEYWORD_ONLY_SOURCE = (
    "def mark_int(value: int) -> int:\n    return value\n\n"
    "def mark_bool(value: bool) -> bool:\n    return value\n\n"
    "def mark_float(value: float) -> float:\n    return value\n\n"
    "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(x: int, y: bool, z: float) -> int:\n"
    "    return choose(ratio=mark_float(z), left=mark_int(x), "
    "flag=mark_bool(y))\n"
)

HISTORICAL_KEYWORD_ONLY_SOURCE = (
    "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(x: int, y: bool, z: float) -> int:\n"
    "    return choose(ratio=z, left=x, flag=y)\n"
)

PHASE14C_KEYWORD_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(flag=flag, left=value)\n"
)

REJECTION_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "missing-keyword-only",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n    return sink(value)\n",
        "PYC2904",
    ),
    (
        "keyword-only-positional",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n    return sink(value, flag)\n",
        "PYC2904",
    ),
    (
        "unknown-name",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, missing=flag)\n",
        "PYC2912",
    ),
    (
        "positional-only-name",
        "def sink(value: int, /, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag)\n",
        "PYC2912",
    ),
    (
        "collision",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value, value=value, flag=flag)\n",
        "PYC2912",
    ),
    (
        "duplicate",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag, flag=flag)\n",
        "PYC2912",
    ),
    (
        "category",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n"
        "    return sink(value=value, flag=value)\n",
        "PYC2905",
    ),
    (
        "star-positional",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(*value, flag=flag)\n",
        "PYC2910",
    ),
    (
        "star-keyword",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, **flag)\n",
        "PYC2910",
    ),
    (
        "keyword-only-default",
        "def sink(value: int, *, flag: bool = True) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag)\n",
        "PYC2911",
    ),
    (
        "positional-default",
        "def sink(value: int = 1, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag)\n",
        "PYC2911",
    ),
    (
        "variadic",
        "def sink(value: int, *rest: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value, flag=flag)\n",
        "PYC2911",
    ),
    (
        "range-keyword",
        "def run() -> int:\n"
        "    total = 0\n"
        "    for item in range(stop=3):\n"
        "        total = total + item\n"
        "    return total\n",
        "PYC2842",
    ),
    (
        "record-constructor-keyword",
        "class Sample:\n"
        "    count: int\n"
        "    def __init__(self, count: int) -> None:\n"
        "        self.count = count\n\n"
        "def run(value: int) -> int:\n"
        "    sample = Sample(count=value)\n"
        "    return value\n",
        "PYC3605",
    ),
    (
        "dynamic-target",
        "def run(value: int) -> int:\n    return missing(value=value)\n",
        "PYC2901",
    ),
    (
        "recursion",
        "def run(value: int, *, flag: bool) -> int:\n"
        "    return run(value=value, flag=flag)\n",
        "PYC2920",
    ),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_gzip_bytes(raw_tar: bytes) -> bytes:
    """Return the exact Phase 14D level-6, mtime-zero, Unix gzip member."""

    compressor = zlib.compressobj(
        level=6,
        method=zlib.DEFLATED,
        wbits=-15,
    )
    body = compressor.compress(raw_tar) + compressor.flush()
    header = bytes.fromhex("1f8b0800000000000003")
    trailer = struct.pack(
        "<II",
        zlib.crc32(raw_tar) & 0xFFFFFFFF,
        len(raw_tar) & 0xFFFFFFFF,
    )
    return header + body + trailer


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


def _ephemeral(relative: PurePosixPath) -> bool:
    return (
        "__pycache__" in relative.parts
        or ".pytest_cache" in relative.parts
        or "build" in relative.parts
        or "dist" in relative.parts
        or relative.name.endswith((".pyc", ".pyo"))
    )


def canonical_release_tree_hash(root: Path = ROOT) -> str:
    """Hash the candidate tree, excluding only 14D self-reference/ephemera."""

    files: dict[str, bytes] = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if relative != RELEASE_FINGERPRINT and not _ephemeral(relative):
            files[relative.as_posix()] = path.read_bytes()
    return _hash_file_map(files)


def canonical_release_subtree_hash(root: Path, prefix: str) -> str:
    """Hash one release-tree subtree with paths relative to that subtree."""

    base = Path(root) / PurePosixPath(prefix)
    files: dict[str, bytes] = {}
    if not base.is_dir():
        raise ValueError(f"release subtree is absent: {prefix}")
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(base).as_posix())
        if not _ephemeral(relative):
            files[relative.as_posix()] = path.read_bytes()
    if not files:
        raise ValueError(f"release subtree is empty: {prefix}")
    return _hash_file_map(files)


def archive_file_map(
    archive: Path,
    *,
    fingerprint_to_omit: PurePosixPath | None = None,
) -> dict[str, bytes]:
    """Read a safe single-root gzip tar and omit an explicit self-reference."""

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
            if _ephemeral(relative):
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
    if fingerprint_to_omit is not None:
        files.pop(fingerprint_to_omit.as_posix(), None)
    return files


def canonical_archive_tree_hash(
    archive: Path,
    *,
    fingerprint_to_omit: PurePosixPath | None = None,
) -> str:
    return _hash_file_map(
        archive_file_map(archive, fingerprint_to_omit=fingerprint_to_omit)
    )


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
    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "numeric_facts": NUMERIC_FACT_SCHEMA,
        "conditional_facts": CONDITIONAL_FACT_SCHEMA,
        "keyword_call_facts": KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_call_facts": KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "semantic_policy": DEFAULT_SEMANTIC_POLICY,
        "module_policy": DEFAULT_MODULE_POLICY,
        "record_policy": DEFAULT_RECORD_POLICY,
        "numeric_policy": DEFAULT_NUMERIC_POLICY,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "target_contract": DEFAULT_TARGET_CONTRACT,
    }


def historical_phase14c_contracts() -> dict[str, object]:
    return {
        "keyword_call_facts": KEYWORD_CALL_FACT_SCHEMA,
        "conversion_plan": PHASE14C_CONVERSION_PLAN_SCHEMA,
        "c_ir": PHASE14C_C_IR_SCHEMA,
        "generated_c": PHASE14C_GENERATED_C_SCHEMA,
        "conversion_summary": PHASE14C_CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": PHASE14C_DECISION_TRACE_SCHEMA,
        "rule_set": PHASE14C_RULE_SET,
        "renderer": PHASE14C_RENDERER,
    }


def exact_mapping_errors(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
    label: str,
) -> list[str]:
    errors: list[str] = []
    for key in sorted(set(actual) | set(expected)):
        if key not in expected:
            errors.append(f"{label}: unexpected key {key!r}")
        elif key not in actual:
            errors.append(f"{label}: missing key {key!r}")
        elif actual[key] != expected[key]:
            errors.append(f"{label}: {key!r} is {actual[key]!r}, expected {expected[key]!r}")
    return errors


def _table(payload: Mapping[str, object], table_id: str) -> dict[str, Any]:
    tables = payload.get("fact_tables", ())
    if not isinstance(tables, (list, tuple)):
        return {}
    return next(
        (
            item
            for item in tables
            if isinstance(item, dict) and item.get("table_id") == table_id
        ),
        {},
    )


def _binding_names(payload: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in _table(payload, "binding-facts").get("records", ()):
        value = record.get("value", {}) if isinstance(record, dict) else {}
        if isinstance(value.get("binding_id"), str) and isinstance(
            value.get("source_name"), str
        ):
            result[value["binding_id"]] = value["source_name"]
    return result


def _walk_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_dicts(child)


def _call_name(call: Mapping[str, object], names: Mapping[str, str]) -> str | None:
    callee = call.get("callee", {})
    binding_id = callee.get("binding_id") if isinstance(callee, dict) else None
    return names.get(binding_id) if isinstance(binding_id, str) else None


def _fingerprint_value(value: object) -> str | None:
    candidate = getattr(value, "value", None)
    return candidate if isinstance(candidate, str) else None


def _fresh_process_errors(root: Path, result: object) -> list[str]:
    script = (
        "import hashlib\n"
        "from pycforge import ConversionRequest,PythonToCConverter\n"
        "from pycforge.converter.core.request import ObservationOptions\n"
        "from pycforge.converter.core.serialization import result_to_json\n"
        f"s={KEYWORD_ONLY_SOURCE!r}\n"
        "r=PythonToCConverter().convert(ConversionRequest.from_source(s),"
        "observation=ObservationOptions('Full',False))\n"
        "print(hashlib.sha256(result_to_json(r).encode()).hexdigest())\n"
        "print(hashlib.sha256((r.generated_c or '').encode()).hexdigest())\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return ["fresh-process keyword-only witness failed: " + completed.stderr.strip()]
    expected = [
        sha256_bytes(result_to_json(result).encode("utf-8")),
        sha256_bytes((getattr(result, "generated_c", None) or "").encode("utf-8")),
    ]
    if completed.stdout.splitlines() != expected:
        return ["keyword-only witness is not fresh-process deterministic"]
    return []


def accepted_keyword_only_errors(root: Path = ROOT) -> list[str]:
    converter = PythonToCConverter()
    observation = ObservationOptions("Full", False)
    first = converter.convert(
        ConversionRequest.from_source(KEYWORD_ONLY_SOURCE),
        observation=observation,
    )
    second = converter.convert(
        ConversionRequest.from_source(KEYWORD_ONLY_SOURCE),
        observation=observation,
    )
    errors: list[str] = []
    if (
        first.status is not ResultStatus.CONVERTED
        or first.generated_c is None
        or first.stage_artifact is None
    ):
        return ["accepted keyword-only witness did not convert exactly"]
    if (
        second.status is not ResultStatus.CONVERTED
        or second.generated_c != first.generated_c
        or second.output_fingerprint != first.output_fingerprint
        or second.stage_artifact != first.stage_artifact
    ):
        errors.append("accepted keyword-only witness is not deterministic")
    payload = first.stage_artifact.payload
    records = _table(payload, KEYWORD_ONLY_CALL_TABLE_ID).get("records", ())
    facts = [
        item.get("value", {})
        for item in records
        if isinstance(item, dict) and isinstance(item.get("value"), dict)
    ]
    selected = next((item for item in facts if item.get("target_name") == "choose"), {})
    plans = [
        item
        for item in payload.get("rule_plans", ())
        if isinstance(item, dict) and item.get("rule_id") == KEYWORD_ONLY_CALL_RULE_ID
    ]
    if (
        len(facts) != 1
        or len(plans) != 1
        or selected.get("parameter_names") != ["left", "flag", "ratio"]
        or selected.get("parameter_kinds")
        != ["positional-or-keyword", "keyword-only", "keyword-only"]
        or selected.get("required_keyword_only_parameter_names") != ["flag", "ratio"]
        or selected.get("source_to_parameter_ordinals") != [2, 0, 1]
        or selected.get("parameter_to_source_ordinals") != [1, 2, 0]
        or selected.get("evaluation_order") != selected.get("source_argument_node_ids")
        or selected.get("parameter_coverage_exact") is not True
        or selected.get("keyword_only_coverage_exact") is not True
        or selected.get("arguments_evaluated_once") is not True
        or selected.get("lowering_shape") != KEYWORD_ONLY_CALL_LOWERING_SHAPE
        or selected.get("allocation_model") != "none"
        or selected.get("cleanup_model") != "none"
        or selected.get("runtime_binding_failure") != "proved-absent"
        or selected.get("supported") is not True
    ):
        errors.append("accepted keyword-only fact or RulePlan is incomplete")
    if validate_keyword_only_call_binding_facts(
        dict(payload),
        expected_fact_schema=KEYWORD_ONLY_CALL_FACT_SCHEMA,
    ) != (True, ""):
        errors.append("independent keyword-only validation rejected accepted evidence")
    names = _binding_names(payload)
    run = next(
        (
            item
            for item in payload.get("c_ir", {}).get("declarations", ())
            if isinstance(item, dict)
            and item.get("kind") == "CFunctionDefinition"
            and item.get("identifier", {}).get("spelling") == "run"
        ),
        {},
    )
    calls = [
        _call_name(item, names)
        for item in _walk_dicts(run)
        if item.get("kind") == "CCallExpr"
    ]
    choose = next(
        (
            item
            for item in _walk_dicts(run)
            if item.get("kind") == "CCallExpr"
            and _call_name(item, names) == "choose"
        ),
        {},
    )
    if calls != ["mark_float", "mark_int", "mark_bool", "choose"]:
        errors.append("nested keyword-only actuals did not stage in source order")
    if [item.get("kind") for item in choose.get("arguments", ())] != [
        "CIdentifierRef",
        "CIdentifierRef",
        "CIdentifierRef",
    ]:
        errors.append("keyword-only C call does not use pure formal-order references")
    if not validate_c_text(first.generated_c).accepted:
        errors.append("keyword-only generated C failed textual conformance")
    errors.extend(_fresh_process_errors(root, first))
    return errors


def bounded_profile_errors() -> list[str]:
    primary = (
        "from lib import choose\n\n"
        "def run(value: int, flag: bool, ratio: float) -> int:\n"
        "    return choose(ratio=ratio, flag=flag, left=value)\n"
    )
    companion = (
        "def choose(left: int, *, flag: bool, ratio: float) -> int:\n"
        "    return left\n"
    )
    result = PythonToCConverter().convert(
        ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", primary, "app"),
                (SourceDocumentInput("lib.py", companion, "lib"),),
            )
        ),
        observation=ObservationOptions("Full", False),
    )
    if result.status is not ResultStatus.CONVERTED or result.stage_artifact is None:
        return ["cross-module keyword-only witness did not convert"]
    payload = result.stage_artifact.payload
    records = _table(payload, KEYWORD_ONLY_CALL_TABLE_ID).get("records", ())
    fact = records[0].get("value", {}) if len(records) == 1 else {}
    functions = {
        item["value"]["function_node_id"]: item["value"]
        for item in _table(payload, "module-function-facts").get("records", ())
        if isinstance(item, dict) and isinstance(item.get("value"), dict)
    }
    if (
        fact.get("source_to_parameter_ordinals") != [2, 1, 0]
        or functions.get(fact.get("target_function_node_id"), {}).get("module_id")
        != "lib"
        or result.conversion_summary.get("module_initialization", {}).get("module_order")
        != ["lib", "app"]
    ):
        return ["cross-module keyword-only target evidence is incomplete"]
    return []


def rejection_matrix_errors() -> list[str]:
    errors: list[str] = []
    for label, source, expected in REJECTION_CASES:
        result = PythonToCConverter().convert(ConversionRequest.from_source(source))
        codes = [item.code for item in result.diagnostics]
        if (
            result.status is not ResultStatus.REJECTED
            or codes != [expected]
            or result.generated_c is not None
            or result.output_fingerprint is not None
        ):
            errors.append(
                f"keyword-only rejection {label!r} was not exact: {codes!r}"
            )
    return errors


def independent_tamper_errors() -> list[str]:
    result = PythonToCConverter().convert(
        ConversionRequest.from_source(KEYWORD_ONLY_SOURCE)
    )
    if result.status is not ResultStatus.CONVERTED or result.stage_artifact is None:
        return ["cannot construct keyword-only tamper baseline"]
    baseline = json.loads(json.dumps(dict(result.stage_artifact.payload)))
    baseline["schema_version"] = CONVERSION_PLAN_SCHEMA
    if validate_analysis_payload(baseline) != (True, ""):
        return ["keyword-only tamper baseline does not independently validate"]
    errors: list[str] = []

    def record(payload: dict) -> dict:
        return _table(payload, KEYWORD_ONLY_CALL_TABLE_ID)["records"][0]

    mutations = (
        (
            "source order",
            lambda payload: record(payload)["value"][
                "source_argument_node_ids"
            ].reverse(),
        ),
        (
            "formal order",
            lambda payload: record(payload)["value"][
                "parameter_argument_node_ids"
            ].reverse(),
        ),
        (
            "parameter kind",
            lambda payload: record(payload)["value"]["parameter_kinds"].__setitem__(
                -1,
                "positional-or-keyword",
            ),
        ),
        (
            "keyword-only coverage",
            lambda payload: record(payload)["value"].__setitem__(
                "required_keyword_only_parameter_names",
                [],
            ),
        ),
        (
            "permutation",
            lambda payload: record(payload)["value"].__setitem__(
                "source_to_parameter_ordinals",
                [0, 1, 2],
            ),
        ),
    )
    for label, mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        valid, reason = validate_analysis_payload(payload)
        if valid or not reason:
            errors.append(f"independent validator accepted {label} tampering")
    return errors


def cancellation_errors() -> list[str]:
    errors: list[str] = []
    token = CancellationToken()
    token.cancel()
    result = PythonToCConverter().convert(
        ConversionRequest.from_source(KEYWORD_ONLY_SOURCE),
        cancellation=token,
    )
    if (
        result.status is not ResultStatus.CANCELED
        or result.generated_c is not None
        or result.output_fingerprint is not None
    ):
        errors.append("pre-canceled keyword-only conversion did not retire output")
    baseline = PythonToCConverter().convert(
        ConversionRequest.from_source(KEYWORD_ONLY_SOURCE)
    )
    if baseline.stage_artifact is None:
        return errors + ["cancellation baseline omitted its artifact"]
    validator_token = CancellationToken()
    validator_token.cancel()
    try:
        validate_keyword_only_call_binding_facts(
            dict(baseline.stage_artifact.payload),
            expected_fact_schema=KEYWORD_ONLY_CALL_FACT_SCHEMA,
            cancellation=validator_token,
        )
    except KeywordOnlyCallValidationCanceled:
        pass
    else:
        errors.append("independent keyword-only validator ignored cancellation")
    return errors


def historical_phase14c_errors() -> list[str]:
    contract_errors = exact_mapping_errors(
        historical_phase14c_contracts(),
        EXPECTED_PHASE14C_CONTRACTS,
        "historical Phase 14C contracts",
    )
    if contract_errors:
        return contract_errors
    converter = PythonToCConverter()
    historical_rejection = converter.convert(
        ConversionRequest.from_source(
            HISTORICAL_KEYWORD_ONLY_SOURCE,
            rule_set_version=PHASE14C_RULE_SET,
            renderer_version=PHASE14C_RENDERER,
        ),
        observation=ObservationOptions("Full", False),
    )
    errors: list[str] = []
    if (
        historical_rejection.status is not ResultStatus.REJECTED
        or [item.code for item in historical_rejection.diagnostics] != ["PYC2911"]
        or [item.diagnostic_id for item in historical_rejection.diagnostics]
        != ["diag-8405a8ed7e520a5f8a35"]
        or _fingerprint_value(historical_rejection.request_fingerprint)
        != "f921ebf5ba65d9341678c2706cdcb9f7f8a10ee95511a0832f78ba3ce47a3db0"
        or historical_rejection.stage_artifact is None
        or historical_rejection.stage_artifact.schema_version != "0.14.2"
        or _fingerprint_value(
            historical_rejection.stage_artifact.artifact_fingerprint
        )
        != "403374c475857731cbd3d1431b5299e9cb34768134b42c2596fe2571b32f3841"
        or KEYWORD_ONLY_CALL_TABLE_ID
        in {
            item.get("table_id")
            for item in historical_rejection.stage_artifact.payload.get(
                "fact_tables",
                (),
            )
        }
        or historical_rejection.generated_c is not None
        or historical_rejection.output_fingerprint is not None
    ):
        errors.append("explicit Phase 14C keyword-only rejection envelope changed")

    active = converter.convert(
        ConversionRequest.from_source(PHASE14C_KEYWORD_SOURCE)
    )
    historical = converter.convert(
        ConversionRequest.from_source(
            PHASE14C_KEYWORD_SOURCE,
            rule_set_version=PHASE14C_RULE_SET,
            renderer_version=PHASE14C_RENDERER,
        )
    )
    if (
        active.status is not ResultStatus.CONVERTED
        or historical.status is not ResultStatus.CONVERTED
        or active.generated_c != historical.generated_c
        or active.output_fingerprint != historical.output_fingerprint
        or sha256_bytes((active.generated_c or "").encode("utf-8"))
        != PHASE14C_KEYWORD_C_SHA256
        or _fingerprint_value(active.output_fingerprint)
        != PHASE14C_KEYWORD_OUTPUT_SHA256
        or active.stage_artifact is None
        or active.stage_artifact.schema_version != "0.14.3"
        or historical.stage_artifact is None
        or historical.stage_artifact.schema_version != "0.14.2"
        or _table(active.stage_artifact.payload, KEYWORD_ONLY_CALL_TABLE_ID).get(
            "records"
        )
        != []
    ):
        errors.append("active no-14D-rule output changed explicit Phase 14C behavior")
    return errors


def converter_smoke_errors(root: Path = ROOT) -> list[str]:
    return list(
        dict.fromkeys(
            accepted_keyword_only_errors(root)
            + bounded_profile_errors()
            + rejection_matrix_errors()
            + independent_tamper_errors()
            + cancellation_errors()
            + historical_phase14c_errors()
        )
    )


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


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _opening_required_files() -> set[str]:
    return {
        "pycforge/converter/keyword_only_calls/__init__.py",
        "pycforge/converter/keyword_only_calls/analysis.py",
        "pycforge/converter/keyword_only_calls/lowering.py",
        "pycforge/converter/keyword_only_calls/model.py",
        "pycforge/converter/keyword_only_calls/validation.py",
        "tests/test_phase14d_keyword_only_contracts.py",
        "tests/test_phase14d_keyword_only_analysis.py",
        "tests/test_phase14d_keyword_only_lowering.py",
        "tests/test_phase14d_keyword_only_hardening.py",
        "tests/test_phase14d_cumulative_eligibility.py",
        "tests/test_validate_phase14d.py",
        "tools/validate_phase14d.py",
    }


def _promoted_required_files(manifest: Mapping[str, object]) -> set[str]:
    declared = manifest.get("required_contract_files", ())
    names = {
        name
        for name in declared
        if isinstance(name, str)
        and bool(name)
        and not PurePosixPath(name).is_absolute()
        and ".." not in PurePosixPath(name).parts
    } if isinstance(declared, list) else set()
    return names | _opening_required_files() | set(PROMOTED_REQUIRED_FILES)


def _manifest_required_file_errors(manifest: Mapping[str, object]) -> list[str]:
    declared = manifest.get("required_contract_files")
    if not isinstance(declared, list):
        return ["Phase 14D manifest required_contract_files is not a list"]
    errors: list[str] = []
    declared_names = {item for item in declared if isinstance(item, str)}
    if len(declared) != len(declared_names):
        errors.append(
            "Phase 14D manifest required_contract_files contains duplicates "
            "or non-string entries"
        )
    for name in declared:
        if not isinstance(name, str):
            continue
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != name
        ):
            errors.append(
                f"Phase 14D manifest required_contract_files has unsafe path {name!r}"
            )
    missing = sorted(PROMOTED_REQUIRED_FILES - declared_names)
    if missing:
        errors.append(
            "Phase 14D manifest required_contract_files omits canonical "
            "promotion files: "
            + ", ".join(missing)
        )
    return errors


def _exact_release_test_count_errors(
    actual: object,
    expected: Mapping[str, int],
    label: str,
) -> list[str]:
    if not isinstance(actual, dict):
        return [f"{label} is not a mapping"]
    errors: list[str] = []
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            errors.append(
                f"{label} {key} is {actual.get(key)!r}, "
                f"expected {expected_value}"
            )
    return errors


def _sealed_transition_subtree_errors(
    root: Path,
    fingerprint: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    for field, (prefix, sealed_digest) in (
        SEALED_TRANSITION_SUBTREE_IDENTITIES.items()
    ):
        if fingerprint.get(field) != sealed_digest:
            errors.append(
                f"release fingerprint {field} does not match its sealed identity"
            )
        try:
            actual_digest = canonical_release_subtree_hash(root, prefix)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot hash sealed release subtree {prefix}: {exc}")
        else:
            if actual_digest != sealed_digest:
                errors.append(
                    f"sealed release subtree hash mismatch for {prefix}: "
                    f"{actual_digest}"
                )
    return errors


def predecessor_errors(archive: Path) -> list[str]:
    if not archive.is_file():
        return [f"requested predecessor archive is absent: {archive}"]
    errors: list[str] = []
    if archive.name != PREDECESSOR_ARCHIVE_NAME:
        errors.append("sealed Phase 14C archive name mismatch")
    if archive.stat().st_size != PREDECESSOR_ARCHIVE_SIZE:
        errors.append(
            f"sealed Phase 14C archive size mismatch: {archive.stat().st_size}"
        )
    digest = sha256_bytes(archive.read_bytes())
    if digest != PREDECESSOR_ARCHIVE_SHA256:
        errors.append(f"sealed Phase 14C archive hash mismatch: {digest}")
        return errors
    try:
        tree_digest = canonical_archive_tree_hash(
            archive,
            fingerprint_to_omit=PREDECESSOR_FINGERPRINT,
        )
        converter_digest = canonical_archive_subtree_hash(
            archive,
            "pycforge/converter",
        )
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot authenticate predecessor archive: {exc}"]
    if tree_digest != PREDECESSOR_TREE_SHA256:
        errors.append(f"sealed Phase 14C tree hash mismatch: {tree_digest}")
    if converter_digest != PREDECESSOR_CONVERTER_SHA256:
        errors.append(
            f"sealed Phase 14C converter subtree hash mismatch: {converter_digest}"
        )
    return errors


def predecessor_wheel_errors(wheel: Path) -> list[str]:
    if not wheel.is_file():
        return [f"requested predecessor wheel is absent: {wheel}"]
    errors: list[str] = []
    if wheel.name != PREDECESSOR_WHEEL_NAME:
        errors.append("sealed Phase 14C wheel name mismatch")
    if wheel.stat().st_size != PREDECESSOR_WHEEL_SIZE:
        errors.append("sealed Phase 14C wheel size mismatch")
    if sha256_bytes(wheel.read_bytes()) != PREDECESSOR_WHEEL_SHA256:
        errors.append("sealed Phase 14C wheel hash mismatch")
        return errors
    try:
        with zipfile.ZipFile(wheel) as package:
            names = set(package.namelist())
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = package.read(metadata_name).decode("utf-8")
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
        return errors + [f"cannot inspect predecessor wheel: {exc}"]
    if "Version: 0.14.2\n" not in metadata:
        errors.append("sealed Phase 14C wheel metadata version mismatch")
    if "pycforge/converter/keyword_calls/validation.py" not in names:
        errors.append("sealed Phase 14C wheel omits its keyword-call package")
    if any(name.endswith((".so", ".dll", ".dylib", ".pyd")) for name in names):
        errors.append("sealed Phase 14C wheel unexpectedly contains native binaries")
    return errors


def _artifact_expectation(
    fingerprint: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    artifacts = fingerprint.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    value = artifacts.get(key, {})
    return value if isinstance(value, dict) else {}


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _at_least_two(value: object) -> bool:
    return type(value) is int and value >= 2


def _final_artifact_metadata_errors(
    fingerprint: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    artifacts = fingerprint.get("artifacts")
    if not isinstance(artifacts, dict):
        return ["release fingerprint artifacts is not a mapping"]

    wheel = _artifact_expectation(fingerprint, "wheel")
    wheel_expectations = (
        ("filename", WHEEL_NAME),
        ("fixed_epoch", REPRODUCIBLE_BUILD_EPOCH),
        ("fixed_epoch_builds_byte_identical", True),
        ("metadata_version", RELEASE_VERSION),
        ("tag", "py3-none-any"),
        ("native_binaries", 0),
        ("isolated_install_passed", True),
        ("installed_same_module_keyword_only_conversion_passed", True),
        ("installed_cross_module_keyword_only_conversion_passed", True),
        ("installed_keyword_only_audit_passed", True),
        ("installed_linked_c_atomic_save_passed", True),
        ("installed_stale_output_save_block_passed", True),
        ("installed_injected_atomic_failure_passed", True),
    )
    for key, expected in wheel_expectations:
        if wheel.get(key) != expected:
            errors.append(
                f"release fingerprint wheel {key} is not finalized"
            )
    if not _positive_int(wheel.get("size")):
        errors.append("release fingerprint wheel size is not finalized")
    if not _is_sha256(wheel.get("sha256")):
        errors.append("release fingerprint wheel sha256 is not finalized")
    if not _at_least_two(wheel.get("fixed_epoch_builds_compared")):
        errors.append(
            "release fingerprint wheel fixed_epoch_builds_compared is below two"
        )
    for key in ("zip_members", "record_entries"):
        if not _positive_int(wheel.get(key)):
            errors.append(f"release fingerprint wheel {key} is not finalized")
    if type(wheel.get("svg_assets")) is not int or wheel.get("svg_assets") < 0:
        errors.append("release fingerprint wheel svg_assets is not finalized")

    source = _artifact_expectation(fingerprint, "source_archive")
    source_expectations = (
        ("filename", SOURCE_ARCHIVE_NAME),
        ("fixed_epoch", REPRODUCIBLE_BUILD_EPOCH),
        ("normalized_builds_byte_identical", True),
        ("size_recorded_externally", True),
        ("sha256_recorded_externally", True),
    )
    for key, expected in source_expectations:
        if source.get(key) != expected:
            errors.append(
                f"release fingerprint source archive {key} is not finalized"
            )
    if not _at_least_two(source.get("normalized_builds_compared")):
        errors.append(
            "release fingerprint source archive normalized_builds_compared "
            "is below two"
        )
    if "size" in source or "sha256" in source:
        errors.append(
            "release fingerprint source archive embeds circular raw size or sha256"
        )
    return errors


def wheel_errors(wheel: Path, fingerprint: Mapping[str, object]) -> list[str]:
    if not wheel.is_file():
        return [f"requested wheel is absent: {wheel}"]
    expected = _artifact_expectation(fingerprint, "wheel")
    errors: list[str] = []
    if wheel.name != WHEEL_NAME:
        errors.append("wheel name is not the canonical Phase 14D wheel name")
    if expected.get("filename") != wheel.name:
        errors.append("wheel name does not match the release fingerprint")
    if expected.get("sha256") != sha256_bytes(wheel.read_bytes()):
        errors.append("wheel hash does not match the release fingerprint")
    if expected.get("size") != wheel.stat().st_size:
        errors.append("wheel size does not match the release fingerprint")
    if expected.get("fixed_epoch") != REPRODUCIBLE_BUILD_EPOCH:
        errors.append("wheel fingerprint fixed epoch is not canonical")
    if not _at_least_two(expected.get("fixed_epoch_builds_compared")):
        errors.append("wheel fingerprint compares fewer than two fixed-epoch builds")
    if expected.get("fixed_epoch_builds_byte_identical") is not True:
        errors.append("wheel fingerprint omits byte-identical fixed-epoch builds")
    if expected.get("isolated_install_passed") is not True:
        errors.append("wheel fingerprint omits isolated-install validation")
    try:
        with zipfile.ZipFile(wheel) as package:
            name_list = package.namelist()
            names = set(name_list)
            corrupt = package.testzip()
            member_bytes = {name: package.read(name) for name in name_list}
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = member_bytes[metadata_name].decode("utf-8")
            wheel_name = next(
                name for name in names if name.endswith(".dist-info/WHEEL")
            )
            wheel_metadata = member_bytes[wheel_name].decode("utf-8")
            record_name = next(
                name for name in names if name.endswith(".dist-info/RECORD")
            )
            record_rows = list(
                csv.reader(
                    io.StringIO(package.read(record_name).decode("utf-8"))
                )
            )
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
        return errors + [f"cannot inspect wheel: {exc}"]
    if corrupt is not None:
        errors.append(f"wheel ZIP integrity failed at {corrupt}")
    if len(name_list) != len(names):
        errors.append("wheel contains duplicate member names")
    if f"Version: {RELEASE_VERSION}\n" not in metadata:
        errors.append("wheel metadata version mismatch")
    if "Root-Is-Purelib: true\n" not in wheel_metadata or "Tag: py3-none-any\n" not in wheel_metadata:
        errors.append("wheel does not retain the pure Python py3-none-any tag")
    required = {
        "pycforge/converter/keyword_only_calls/__init__.py",
        "pycforge/converter/keyword_only_calls/analysis.py",
        "pycforge/converter/keyword_only_calls/lowering.py",
        "pycforge/converter/keyword_only_calls/model.py",
        "pycforge/converter/keyword_only_calls/validation.py",
    }
    if required - names:
        errors.append("wheel omits one or more Phase 14D modules")
    native = [
        name
        for name in names
        if name.endswith((".so", ".dll", ".dylib", ".pyd"))
    ]
    if native:
        errors.append("wheel unexpectedly contains native binaries")
    if any(not isinstance(row, list) or len(row) != 3 for row in record_rows):
        errors.append("wheel RECORD has malformed rows")
    else:
        record_names = [row[0] for row in record_rows]
        if len(record_names) != len(set(record_names)) or set(record_names) != names:
            errors.append("wheel RECORD does not cover every member exactly once")
        for member, digest, size in record_rows:
            if member == record_name:
                if digest or size:
                    errors.append("wheel RECORD self-entry is not empty")
                continue
            if member not in names:
                continue
            data = member_bytes[member]
            encoded = base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()
            ).rstrip(b"=").decode("ascii")
            if digest != "sha256=" + encoded or size != str(len(data)):
                errors.append(f"wheel RECORD digest or size mismatch: {member}")
                break
    svg_count = sum(name.endswith(".svg") for name in names)
    for key, actual in (
        ("zip_members", len(names)),
        ("record_entries", len(record_rows)),
        ("svg_assets", svg_count),
        ("native_binaries", len(native)),
    ):
        expected_value = expected.get(key)
        if isinstance(expected_value, int) and expected_value != actual:
            errors.append(f"wheel {key} does not match the release fingerprint")
    return errors


def source_archive_errors(
    archive: Path,
    fingerprint: Mapping[str, object],
    *,
    fingerprint_bytes: bytes | None = None,
) -> list[str]:
    if not archive.is_file():
        return [f"requested Phase 14D source archive is absent: {archive}"]
    expected = _artifact_expectation(fingerprint, "source_archive")
    errors: list[str] = []
    if archive.name != SOURCE_ARCHIVE_NAME:
        errors.append(
            "source archive name is not the canonical Phase 14D archive name"
        )
    if expected.get("filename") != archive.name:
        errors.append("source archive name does not match the release fingerprint")
    if expected.get("fixed_epoch") != REPRODUCIBLE_BUILD_EPOCH:
        errors.append("source archive fingerprint fixed epoch is not canonical")
    if not _at_least_two(expected.get("normalized_builds_compared")):
        errors.append(
            "source archive fingerprint compares fewer than two normalized builds"
        )
    if expected.get("normalized_builds_byte_identical") is not True:
        errors.append("source archive fingerprint omits deterministic duplicate builds")
    if expected.get("size_recorded_externally") is not True:
        errors.append("source archive fingerprint omits external size custody")
    if expected.get("sha256_recorded_externally") is not True:
        errors.append("source archive fingerprint omits external sha256 custody")
    if "size" in expected or "sha256" in expected:
        errors.append(
            "source archive fingerprint embeds circular raw size or sha256"
        )
    try:
        compressed = archive.read_bytes()
        if compressed[:10] != bytes.fromhex("1f8b0800000000000003"):
            errors.append("source archive gzip header is not normalized with -n")
        decompressor = zlib.decompressobj(wbits=31)
        raw_tar = decompressor.decompress(compressed)
        raw_tar += decompressor.flush()
        if not decompressor.eof:
            errors.append("source archive gzip member is incomplete")
        if decompressor.unused_data or decompressor.unconsumed_tail:
            errors.append(
                "source archive contains concatenated or trailing gzip data"
            )
        if compressed != canonical_gzip_bytes(raw_tar):
            errors.append(
                "source archive bytes are not canonical level-6 gzip"
            )
        if raw_tar[257:265] != b"ustar\x0000":
            errors.append("source archive is not normalized USTAR format")
        with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as package:
            members = package.getmembers()
        ephemeral_members = []
        for member in members:
            path = PurePosixPath(member.name)
            if len(path.parts) > 1 and _ephemeral(
                PurePosixPath(*path.parts[1:])
            ):
                ephemeral_members.append(member.name)
        if ephemeral_members:
            errors.append(
                "source archive contains forbidden release ephemera: "
                + ", ".join(sorted(ephemeral_members))
            )
        fixed_epoch = expected.get("fixed_epoch")
        if not isinstance(fixed_epoch, int):
            errors.append("source archive fingerprint omits its fixed epoch")
        else:
            if any(member.mtime != fixed_epoch for member in members):
                errors.append("source archive member mtimes are not normalized")
        if any(
            member.uid != 0
            or member.gid != 0
            or member.uname != ""
            or member.gname != ""
            for member in members
        ):
            errors.append("source archive ownership metadata is not normalized")
        if any(
            (member.isdir() and member.mode != 0o755)
            or (member.isfile() and member.mode != 0o644)
            for member in members
        ):
            errors.append("source archive modes are not normalized")
        if any(member.pax_headers for member in members):
            errors.append("source archive unexpectedly contains PAX metadata")
        files = archive_file_map(archive)
        embedded_bytes = files.get(RELEASE_FINGERPRINT.as_posix())
        if embedded_bytes is None:
            errors.append(
                "source archive omits its embedded Phase 14D release fingerprint"
            )
        else:
            try:
                embedded = json.loads(embedded_bytes.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                errors.append(
                    "source archive embedded Phase 14D release fingerprint "
                    f"is invalid JSON: {exc}"
                )
            else:
                if not isinstance(embedded, dict):
                    errors.append(
                        "source archive embedded Phase 14D release fingerprint "
                        "is not a JSON object"
                    )
                elif embedded != dict(fingerprint):
                    errors.append(
                        "source archive embedded Phase 14D release fingerprint "
                        "does not match the supplied root fingerprint"
                    )
            if (
                fingerprint_bytes is not None
                and embedded_bytes != fingerprint_bytes
            ):
                errors.append(
                    "source archive embedded Phase 14D release fingerprint bytes "
                    "do not match the root fingerprint file"
                )
        files.pop(RELEASE_FINGERPRINT.as_posix(), None)
        archive_tree = _hash_file_map(files)
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot inspect Phase 14D source archive: {exc}"]
    if archive_tree != fingerprint.get("value"):
        errors.append(f"source archive release tree hash mismatch: {archive_tree}")
    return errors


def _fingerprint_errors(
    root: Path,
    fingerprint: Mapping[str, object],
    *,
    require_promoted: bool,
) -> list[str]:
    errors: list[str] = []
    finalized = fingerprint.get("status") == "promoted"
    if require_promoted or finalized:
        if (
            fingerprint.get("algorithm") != "sha256"
            or fingerprint.get("domain") != FINGERPRINT_DOMAIN
            or fingerprint.get("status") != "promoted"
        ):
            errors.append("Phase 14D release fingerprint metadata is invalid")
        if fingerprint.get("value_status") != "assigned-self-excluding-tree-hash":
            errors.append("Phase 14D release fingerprint value_status is not assigned")
        if fingerprint.get("excludes") != list(RELEASE_FINGERPRINT_EXCLUDES):
            errors.append("Phase 14D release fingerprint exclusions are not exact")
        expected_tree = fingerprint.get("value")
        if not _is_sha256(expected_tree):
            errors.append("Phase 14D release fingerprint value is not finalized")
        else:
            actual_tree = canonical_release_tree_hash(root)
            if expected_tree != actual_tree:
                errors.append(f"Phase 14D release tree hash mismatch: {actual_tree}")
        if (
            fingerprint.get("predecessor_version") != PREDECESSOR_VERSION
            or fingerprint.get("predecessor_archive")
            != PREDECESSOR_ARCHIVE_NAME
            or fingerprint.get("predecessor_archive_size")
            != PREDECESSOR_ARCHIVE_SIZE
            or fingerprint.get("predecessor_archive_sha256")
            != PREDECESSOR_ARCHIVE_SHA256
            or fingerprint.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or fingerprint.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
            or fingerprint.get("predecessor_wheel") != PREDECESSOR_WHEEL_NAME
            or fingerprint.get("predecessor_wheel_size")
            != PREDECESSOR_WHEEL_SIZE
            or fingerprint.get("predecessor_wheel_sha256")
            != PREDECESSOR_WHEEL_SHA256
        ):
            errors.append("release fingerprint predecessor identity mismatch")
        expected_converter = fingerprint.get("converter_subtree_sha256")
        if not _is_sha256(expected_converter):
            errors.append("release fingerprint converter subtree is not finalized")
        else:
            try:
                actual_converter = canonical_release_subtree_hash(
                    root,
                    "pycforge/converter",
                )
            except (OSError, ValueError) as exc:
                errors.append(f"cannot hash release converter subtree: {exc}")
            else:
                if expected_converter != actual_converter:
                    errors.append(
                        "release fingerprint converter subtree hash mismatch: "
                        f"{actual_converter}"
                    )
        errors.extend(_sealed_transition_subtree_errors(root, fingerprint))

        tests = fingerprint.get("tests")
        errors.extend(
            _exact_release_test_count_errors(
                tests,
                EXPECTED_RELEASE_TEST_COUNTS,
                "release fingerprint tests",
            )
        )
        if isinstance(tests, dict):
            required_tests = tests.get("required_phase14d_tests")
            canonical_tests = {
                name
                for name in PROMOTED_REQUIRED_FILES
                if name.startswith("tests/")
            }
            if (
                not isinstance(required_tests, list)
                or not canonical_tests.issubset(
                    {name for name in required_tests if isinstance(name, str)}
                )
            ):
                errors.append(
                    "release fingerprint required Phase 14D tests are incomplete"
                )

        audits = fingerprint.get("audits")
        required_audits = (
            "architecture",
            "rules",
            "helpers",
            "containers",
            "modules",
            "records",
            "numeric",
            "conditional",
            "keyword",
            "keyword_only",
            "determinism",
            "sealed_phase_14c_transition",
            "phase_14d_transition",
        )
        if (
            not isinstance(audits, dict)
            or any(audits.get(name) is not True for name in required_audits)
        ):
            errors.append("release fingerprint cumulative audits are incomplete")
        errors.extend(_final_artifact_metadata_errors(fingerprint))
        for key in (
            "c_toolchain_invoked",
            "promoted_candidate_toolchain_invoked",
            "compiler_linker_loader_or_execution_invoked",
            "generated_c_compiled_or_executed",
        ):
            if fingerprint.get(key) is not False:
                errors.append(f"release fingerprint does not keep {key} false")
        if fingerprint.get("phase_15_started") is not False:
            errors.append("release fingerprint does not keep Phase 15 closed")
    return errors


def _audit_calls(
    root: Path,
    *,
    include_phase14d_transition: bool,
    require_keyword_only_audit: bool,
):
    calls: list[tuple[str, Any]] = [
        ("architecture", lambda: laboratory_audits.audit_architecture(root)),
        ("rules", lambda: laboratory_audits.audit_rules(root)),
        ("helpers", lambda: laboratory_audits.audit_helpers(root)),
        ("containers", lambda: laboratory_audits.audit_containers(root)),
        ("modules", lambda: laboratory_audits.audit_modules(root)),
        ("records", lambda: laboratory_audits.audit_records(root)),
        ("numeric", lambda: laboratory_audits.audit_numeric(root)),
        ("conditional", lambda: laboratory_audits.audit_conditional(root)),
        ("keyword", lambda: laboratory_audits.audit_keyword(root)),
        ("determinism", lambda: laboratory_audits.audit_determinism(root)),
        (
            "sealed Phase 14C transition",
            lambda: laboratory_audits.audit_transition(root, "phase_14c"),
        ),
    ]
    audit_keyword_only = getattr(laboratory_audits, "audit_keyword_only", None)
    if callable(audit_keyword_only):
        calls.insert(
            9,
            ("keyword-only", lambda: audit_keyword_only(root)),
        )
    elif require_keyword_only_audit:
        calls.insert(9, ("keyword-only", None))
    if include_phase14d_transition:
        calls.append(
            (
                "Phase 14D transition",
                lambda: laboratory_audits.audit_transition(root, "phase_14d"),
            )
        )
    return calls


def validate_tree(
    root: Path = ROOT,
    *,
    predecessor_archive: Path | None = None,
    predecessor_wheel: Path | None = None,
    wheel: Path | None = None,
    source_archive: Path | None = None,
    require_promoted: bool = True,
    converter_smoke: bool = True,
) -> tuple[str, ...]:
    root = Path(root)
    errors: list[str] = []
    manifest_path = root / "transition/phase_14d/manifest.json"
    manifest = (
        _load_json(manifest_path, "Phase 14D manifest", errors)
        if require_promoted or manifest_path.is_file()
        else {}
    )
    if manifest:
        version = manifest.get("version", manifest.get("candidate_version"))
        if (
            manifest.get("phase") != 14
            or manifest.get("mini_phase") != MINI_PHASE
            or version != RELEASE_VERSION
        ):
            errors.append("Phase 14D manifest identity mismatch")
        if require_promoted and manifest.get("status") != "promoted":
            errors.append("Phase 14D manifest is not promoted")
        if (
            manifest.get("predecessor_version") != PREDECESSOR_VERSION
            or manifest.get("predecessor_archive_sha256")
            != PREDECESSOR_ARCHIVE_SHA256
            or manifest.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or manifest.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
            or manifest.get("predecessor_wheel_sha256")
            != PREDECESSOR_WHEEL_SHA256
        ):
            errors.append("Phase 14D manifest predecessor identity mismatch")
        schemas = manifest.get("schemas")
        if isinstance(schemas, dict):
            errors.extend(
                exact_mapping_errors(
                    schemas,
                    EXPECTED_CONTRACTS,
                    "Phase 14D manifest contracts",
                )
            )
        elif require_promoted:
            errors.append("Phase 14D manifest contracts are not finalized")
        errors.extend(_manifest_required_file_errors(manifest))

    finalized = require_promoted or manifest.get("status") == "promoted"
    if finalized:
        errors.extend(
            _exact_release_test_count_errors(
                manifest,
                EXPECTED_MANIFEST_TEST_COUNTS,
                "Phase 14D manifest test counts",
            )
        )
        report_path = root / "evidence/phase_14d/release_report.json"
        report = _load_json(
            report_path,
            "Phase 14D release report",
            errors,
        )
        if report:
            errors.extend(
                _exact_release_test_count_errors(
                    report.get("tests"),
                    EXPECTED_RELEASE_TEST_COUNTS,
                    "Phase 14D release report tests",
                )
            )

    errors.extend(
        exact_mapping_errors(
            current_contracts(),
            EXPECTED_CONTRACTS,
            "active contracts",
        )
    )
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

    required_files = (
        _promoted_required_files(manifest)
        if require_promoted
        else _opening_required_files()
    )
    for name in sorted(required_files):
        if not (root / name).is_file():
            errors.append(f"missing Phase 14D release file: {name}")
    for name, expected in (
        ("docs/python_to_c_converter_architecture_revision_3_1.txt", ROADMAP_SHA256),
        (
            "docs/python_to_c_converter_architecture_revision_3_2_addendum.md",
            ADDENDUM_SHA256,
        ),
    ):
        path = root / name
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"{Path(name).name} hash mismatch")
    if default_helper_registry().fingerprint != HELPER_REGISTRY_SHA256:
        errors.append("Phase 10 helper registry identity changed")

    for name, call in _audit_calls(
        root,
        include_phase14d_transition=require_promoted or manifest_path.is_file(),
        require_keyword_only_audit=require_promoted,
    ):
        if call is None:
            errors.append("keyword-only audit is absent")
            continue
        try:
            report = call()
        except Exception as exc:
            errors.append(f"{name} audit raised {type(exc).__name__}: {exc}")
        else:
            if report.get("passed") is not True:
                errors.append(f"{name} audit failed: {report}")
            if name in {"conditional", "keyword", "keyword-only"} and (
                report.get("c_toolchain_invoked", False) is not False
                or report.get("generated_c_compiled_or_executed", False) is not False
            ):
                errors.append(f"{name} audit does not preserve no-toolchain custody")
    if converter_smoke:
        errors.extend(converter_smoke_errors(root))
    if predecessor_archive is not None:
        errors.extend(predecessor_errors(Path(predecessor_archive)))
    if predecessor_wheel is not None:
        errors.extend(predecessor_wheel_errors(Path(predecessor_wheel)))

    fingerprint_path = root / RELEASE_FINGERPRINT
    fingerprint_bytes: bytes | None = None
    fingerprint = (
        _load_json(fingerprint_path, "Phase 14D release fingerprint", errors)
        if require_promoted or fingerprint_path.is_file()
        else {}
    )
    if fingerprint:
        try:
            fingerprint_bytes = fingerprint_path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read Phase 14D release fingerprint bytes: {exc}")
        errors.extend(
            _fingerprint_errors(
                root,
                fingerprint,
                require_promoted=require_promoted,
            )
        )
    if wheel is not None:
        errors.extend(wheel_errors(Path(wheel), fingerprint))
    if source_archive is not None:
        errors.extend(
            source_archive_errors(
                Path(source_archive),
                fingerprint,
                fingerprint_bytes=fingerprint_bytes,
            )
        )
    return tuple(dict.fromkeys(errors))


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_ARCHIVE_NAME,
        root.parent / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / "release" / PREDECESSOR_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def locate_predecessor_wheel(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_WHEEL_NAME,
        root.parent / PREDECESSOR_WHEEL_NAME,
        root.parents[1] / PREDECESSOR_WHEEL_NAME,
        root.parents[1] / "release" / PREDECESSOR_WHEEL_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def locate_wheel(root: Path = ROOT) -> Path | None:
    candidates = (
        root / "dist" / WHEEL_NAME,
        root / WHEEL_NAME,
        root.parent / WHEEL_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def locate_source_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / SOURCE_ARCHIVE_NAME,
        root.parent / SOURCE_ARCHIVE_NAME,
        root.parents[1] / "release" / SOURCE_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def _unittest_count_errors(
    transcript: str,
    *,
    phase14d_discovered: int,
) -> list[str]:
    errors: list[str] = []
    ran = re.findall(r"^Ran ([0-9]+) tests? in [^\n]+$", transcript, re.MULTILINE)
    outcomes = re.findall(
        r"^OK \(skipped=([0-9]+)\)$",
        transcript,
        re.MULTILINE,
    )
    if len(ran) != 1:
        errors.append("regression transcript does not report exactly one test total")
    elif int(ran[0]) != EXPECTED_RELEASE_TEST_COUNTS["discovered"]:
        errors.append(
            "regression transcript discovered "
            f"{ran[0]} tests, expected "
            f"{EXPECTED_RELEASE_TEST_COUNTS['discovered']}"
        )
    if len(outcomes) != 1:
        errors.append(
            "regression transcript does not report the exact skipped-test outcome"
        )
    elif int(outcomes[0]) != EXPECTED_RELEASE_TEST_COUNTS["skipped"]:
        errors.append(
            "regression transcript skipped "
            f"{outcomes[0]} tests, expected "
            f"{EXPECTED_RELEASE_TEST_COUNTS['skipped']}"
        )
    if phase14d_discovered != EXPECTED_RELEASE_TEST_COUNTS[
        "phase14d_discovered"
    ]:
        errors.append(
            "Phase 14D discovery found "
            f"{phase14d_discovered} tests, expected "
            f"{EXPECTED_RELEASE_TEST_COUNTS['phase14d_discovered']}"
        )
    return errors


def _phase14d_discovered_count(root: Path) -> tuple[int | None, str | None]:
    script = (
        "import unittest\n"
        "loader=unittest.defaultTestLoader\n"
        "phase=loader.discover('tests',pattern='test_phase14d*.py')\n"
        "validator=loader.discover("
        "'tests',pattern='test_validate_phase14d.py')\n"
        "print(phase.countTestCases()+validator.countTestCases())\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        transcript = (completed.stdout + "\n" + completed.stderr).strip()
        return None, "Phase 14D test discovery failed\n" + transcript
    try:
        return int(completed.stdout.strip()), None
    except ValueError:
        return (
            None,
            "Phase 14D test discovery returned a non-integer count: "
            + completed.stdout.strip(),
        )


def _run_tests(root: Path) -> str | None:
    phase14d_discovered, discovery_error = _phase14d_discovered_count(root)
    if discovery_error is not None or phase14d_discovered is None:
        return discovery_error or "Phase 14D test discovery failed"
    phase0_baseline = root / "transition/phase_0/baseline_fingerprint.json"
    try:
        phase0_baseline_bytes = phase0_baseline.read_bytes()
    except OSError as exc:
        return f"cannot snapshot sealed Phase 0 baseline before tests: {exc}"
    completed: subprocess.CompletedProcess[str] | None = None
    execution_error: OSError | None = None
    restoration_error: OSError | None = None
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        execution_error = exc
    finally:
        try:
            phase0_baseline.write_bytes(phase0_baseline_bytes)
        except OSError as exc:
            restoration_error = exc
    if restoration_error is not None:
        return f"cannot restore sealed Phase 0 baseline after tests: {restoration_error}"
    if execution_error is not None or completed is None:
        return f"cannot execute regression suite: {execution_error}"
    transcript = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode:
        return "regression suite failed\n" + transcript
    count_errors = _unittest_count_errors(
        transcript,
        phase14d_discovered=phase14d_discovered,
    )
    if count_errors:
        return "regression suite count mismatch\n" + "\n".join(count_errors)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-archive")
    parser.add_argument("--require-predecessor", action="store_true")
    parser.add_argument("--predecessor-wheel")
    parser.add_argument("--require-predecessor-wheel", action="store_true")
    parser.add_argument("--wheel")
    parser.add_argument("--require-wheel", action="store_true")
    parser.add_argument("--source-archive")
    parser.add_argument("--require-source-archive", action="store_true")
    parser.add_argument("--skip-converter-smoke", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument(
        "--pre-seal",
        action="store_true",
        help="validate implementation before promotion artifacts exist",
    )
    args = parser.parse_args(argv)

    predecessor = (
        Path(args.predecessor_archive).resolve()
        if args.predecessor_archive
        else locate_predecessor_archive(ROOT)
    )
    predecessor_wheel = (
        Path(args.predecessor_wheel).resolve()
        if args.predecessor_wheel
        else locate_predecessor_wheel(ROOT)
    )
    wheel = Path(args.wheel).resolve() if args.wheel else locate_wheel(ROOT)
    source_archive = (
        Path(args.source_archive).resolve()
        if args.source_archive
        else locate_source_archive(ROOT)
    )
    errors = list(
        validate_tree(
            ROOT,
            predecessor_archive=predecessor,
            predecessor_wheel=predecessor_wheel,
            wheel=wheel,
            source_archive=source_archive,
            require_promoted=not args.pre_seal,
            converter_smoke=not args.skip_converter_smoke,
        )
    )
    if args.require_predecessor and predecessor is None:
        errors.append("sealed Phase 14C predecessor archive is required but absent")
    if args.require_predecessor_wheel and predecessor_wheel is None:
        errors.append("sealed Phase 14C predecessor wheel is required but absent")
    if args.require_wheel and wheel is None:
        errors.append("Phase 14D wheel is required but absent")
    if args.require_source_archive and source_archive is None:
        errors.append("Phase 14D source archive is required but absent")
    if args.run_tests and not errors:
        failure = _run_tests(ROOT)
        if failure:
            errors.append(failure)

    if errors:
        print("PyCForge Phase 14D validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PyCForge Phase 14D validation passed")
    print(f"Release version: {RELEASE_VERSION}")
    print(f"Release tree SHA-256: {canonical_release_tree_hash(ROOT)}")
    print(f"Sealed Phase 14C predecessor archive verified: {predecessor is not None}")
    print(f"Sealed Phase 14C predecessor wheel verified: {predecessor_wheel is not None}")
    print(f"Phase 14D wheel verified: {wheel is not None}")
    print(f"Phase 14D source archive verified: {source_archive is not None}")
    print("This validator invoked no C compiler, linker, loader, or execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
