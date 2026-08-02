"""Authenticate and validate the bounded PyCForge Phase 14C release.

The validator reconstructs exact direct keyword-call bindings, checks their
fact, plan, and structured-C-IR lowering evidence, and authenticates release
artifacts.  It has no compiler, linker, loader, foreign-function, or
generated-C execution path.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
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
    PHASE14B_RENDERER,
    PHASE14B_RULE_SET,
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
    MODULE_FACT_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14B_C_IR_SCHEMA,
    PHASE14B_CONDITIONAL_FACT_SCHEMA,
    PHASE14B_CONVERSION_PLAN_SCHEMA,
    PHASE14B_CONVERSION_SUMMARY_SCHEMA,
    PHASE14B_DECISION_TRACE_SCHEMA,
    PHASE14B_GENERATED_C_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.cancellation import CancellationToken  # noqa: E402
from pycforge.converter.core.request import ObservationOptions  # noqa: E402
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.converter.keyword_calls import (  # noqa: E402
    KEYWORD_CALL_KEY_DOMAIN,
    KEYWORD_CALL_LOWERING_SHAPE,
    KEYWORD_CALL_OBLIGATIONS,
    KEYWORD_CALL_PROVENANCE_EVIDENCE,
    KEYWORD_CALL_RULE_ID,
    KEYWORD_CALL_RULE_VERSION,
    KEYWORD_CALL_TABLE_DEPENDENCIES,
    KEYWORD_CALL_TABLE_ID,
    KeywordCallValidationCanceled,
    validate_keyword_call_binding_facts,
)
from pycforge.converter.support_templates import default_helper_registry  # noqa: E402
from pycforge.laboratory import audits as laboratory_audits  # noqa: E402


RELEASE_VERSION = "0.14.2"
MINI_PHASE = "14C"
PREDECESSOR_VERSION = "0.14.1"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_14b_v0_14_1.tar.gz"
PREDECESSOR_ARCHIVE_SIZE = 1_088_259
PREDECESSOR_ARCHIVE_SHA256 = "30737e3a49dc3ed163be071742736f8310c2636a1dc8ac9b9b297aa8c030d2a1"
PREDECESSOR_TREE_SHA256 = "895329a2723301de66adcb118a32308648a7993068e3ef7b5c9764914b9e2f4f"
PREDECESSOR_CONVERTER_SHA256 = "5d261abb5f7dbc480050472cac40a6b4a9539945a3d2e3211af552e094f9780d"
PREDECESSOR_FINGERPRINT = PurePosixPath(
    "transition/phase_14b/release_fingerprint.json"
)
PREDECESSOR_WHEEL_NAME = "pycforge-0.14.1-py3-none-any.whl"
PREDECESSOR_WHEEL_SIZE = 278_494
PREDECESSOR_WHEEL_SHA256 = "255cba6d45b6f7f2c8347f4764d37ad9858d9616f84cc93b65b07e205785a70d"
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
KEYWORD_GENERATED_C_SHA256 = "114938d6ce3737421059f65839d1985592fb7c12d692b6c1d17e305a2b089738"
KEYWORD_REQUEST_SHA256 = "61bbf8ac300f9416edcdb5bed2d8fc365342a7cb89b1b95ac9d43a6e32efdf92"
KEYWORD_OUTPUT_SHA256 = "cef64ddeffdc0512c3af745e02a901187d85c44e02602e15fc862cf62165b9ea"
KEYWORD_ARTIFACT_SHA256 = "e4608658de0c206f9f6dad2386bc2634bff230d57c8dba508b24fed8a1577203"
POSITIONAL_COMPATIBILITY_C_SHA256 = "36528709609e8b53a06fff4739dfa1ae5f1568d27daa0838a03315ecf701fb7e"
POSITIONAL_COMPATIBILITY_OUTPUT_SHA256 = "a30db4341270842057a722c41d5a88e9599aff0a6992cf058aad642f7a724300"
RELEASE_FINGERPRINT = PurePosixPath("transition/phase_14c/release_fingerprint.json")
FINGERPRINT_DOMAIN = "pycforge-phase-14c-release-tree-v1"
TOOLCHAIN_INVOKED = False
EXPECTED_PHASE14B_RULE_SET = "phase14-conditional-regions-v0.14.1"
EXPECTED_PHASE14B_RENDERER = "c-renderer-v0.14.1"


EXPECTED_CONTRACTS: Mapping[str, object] = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "numeric_facts": "fact-table/0.14",
    "conditional_facts": "fact-table/0.14.1",
    "keyword_call_facts": "fact-table/0.14.2",
    "conversion_plan": "conversion-plan/0.14.2",
    "c_ir": "c-ir/0.14.2",
    "generated_c": "generated-c/0.14.2",
    "conversion_summary": "pycforge.conversion-summary/0.14.2",
    "decision_trace": "pycforge.decision-trace/0.14.2",
    "result_serialization": "0.5",
    "rule_set": "phase14-direct-keyword-calls-v0.14.2",
    "renderer": "c-renderer-v0.14.2",
    "semantic_policy": "strict-source-v1",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "numeric_policy": "phase14-proved-floor-arithmetic-v0.14",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
}

EXPECTED_PHASE14B_CONTRACTS: Mapping[str, object] = {
    "conditional_facts": "fact-table/0.14.1",
    "conversion_plan": "conversion-plan/0.14.1",
    "c_ir": "c-ir/0.14.1",
    "generated_c": "generated-c/0.14.1",
    "conversion_summary": "pycforge.conversion-summary/0.14.1",
    "decision_trace": "pycforge.decision-trace/0.14.1",
    "rule_set": "phase14-conditional-regions-v0.14.1",
    "renderer": "c-renderer-v0.14.1",
}

KEYWORD_SOURCE = (
    "def mark_int(value: int) -> int:\n    return value\n\n"
    "def mark_bool(value: bool) -> bool:\n    return value\n\n"
    "def mark_float(value: float) -> float:\n    return value\n\n"
    "def choose(left: int, flag: bool, ratio: float) -> int:\n"
    "    return left\n\n"
    "def run(x: int, y: bool, z: float) -> int:\n"
    "    return choose(ratio=mark_float(z), left=mark_int(x), "
    "flag=mark_bool(y))\n"
)

HISTORICAL_KEYWORD_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(flag=flag, left=value)\n"
)

POSITIONAL_SOURCE = (
    "def choose(left: int, flag: bool) -> int:\n"
    "    return left\n\n"
    "def run(value: int, flag: bool) -> int:\n"
    "    return choose(value, flag)\n"
)

REJECTION_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "star-positional",
        "def sink(value: int) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n    return sink(*value)\n",
        "PYC2910",
    ),
    (
        "star-keyword",
        "def sink(value: int) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n    return sink(**value)\n",
        "PYC2910",
    ),
    (
        "positional-only-name",
        "def sink(value: int, /, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag)\n",
        "PYC2912",
    ),
    (
        "unknown-name",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(missing=value, flag=flag)\n",
        "PYC2912",
    ),
    (
        "positional-keyword-collision",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value, value=value, flag=flag)\n",
        "PYC2912",
    ),
    (
        "duplicate-keyword",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value=value, flag=flag, value=value)\n",
        "PYC2912",
    ),
    (
        "missing-parameter",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n    return sink(value=value)\n",
        "PYC2904",
    ),
    (
        "excess-positional",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(value, flag, value)\n",
        "PYC2904",
    ),
    (
        "mapped-category",
        "def sink(value: int, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(flag=value, value=flag)\n",
        "PYC2905",
    ),
    (
        "default-target",
        "def sink(value: int, flag: bool = True) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(flag=flag, value=value)\n",
        "PYC2911",
    ),
    (
        "keyword-only-target",
        "def sink(value: int, *, flag: bool) -> int:\n    return value\n\n"
        "def run(value: int, flag: bool) -> int:\n"
        "    return sink(flag=flag, value=value)\n",
        "PYC2911",
    ),
    (
        "variadic-target",
        "def sink(value: int, *rest: int) -> int:\n    return value\n\n"
        "def run(value: int) -> int:\n    return sink(value=value)\n",
        "PYC2911",
    ),
    (
        "recursive-target",
        "def run(value: int) -> int:\n    return run(value=value)\n",
        "PYC2920",
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
)


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


def _ephemeral(relative: PurePosixPath) -> bool:
    return (
        "__pycache__" in relative.parts
        or ".pytest_cache" in relative.parts
        or "build" in relative.parts
        or "dist" in relative.parts
        or relative.name.endswith((".pyc", ".pyo"))
    )


def canonical_release_tree_hash(root: Path = ROOT) -> str:
    """Hash the release tree while excluding only 14C self-reference/ephemera."""

    files: dict[str, bytes] = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if relative != RELEASE_FINGERPRINT and not _ephemeral(relative):
            files[relative.as_posix()] = path.read_bytes()
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
    """Return active 14C identities and frozen cumulative identities."""

    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "numeric_facts": NUMERIC_FACT_SCHEMA,
        "conditional_facts": CONDITIONAL_FACT_SCHEMA,
        "keyword_call_facts": KEYWORD_CALL_FACT_SCHEMA,
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


def historical_phase14b_contracts() -> dict[str, object]:
    """Return named historical constants rather than active aliases."""

    return {
        "conditional_facts": PHASE14B_CONDITIONAL_FACT_SCHEMA,
        "conversion_plan": PHASE14B_CONVERSION_PLAN_SCHEMA,
        "c_ir": PHASE14B_C_IR_SCHEMA,
        "generated_c": PHASE14B_GENERATED_C_SCHEMA,
        "conversion_summary": PHASE14B_CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": PHASE14B_DECISION_TRACE_SCHEMA,
        "rule_set": PHASE14B_RULE_SET,
        "renderer": PHASE14B_RENDERER,
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


def _walk_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_dicts(child)


def _fingerprint_value(value: object) -> str | None:
    candidate = getattr(value, "value", None)
    return candidate if isinstance(candidate, str) else None


def _table(payload: Mapping[str, object], table_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in payload.get("fact_tables", ())
        if isinstance(item, dict) and item.get("table_id") == table_id
    ]
    return matches[0] if len(matches) == 1 else {}


def _binding_names(payload: Mapping[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in _table(payload, "binding-facts").get("records", ()):
        value = record.get("value", {}) if isinstance(record, dict) else {}
        if isinstance(value.get("binding_id"), str) and isinstance(
            value.get("source_name"), str
        ):
            result[value["binding_id"]] = value["source_name"]
    return result


def _call_name(call: Mapping[str, object], names: Mapping[str, str]) -> str | None:
    callee = call.get("callee", {})
    return names.get(callee.get("binding_id")) if isinstance(callee, dict) else None


def _keyword_evidence(result: object) -> dict[str, object]:
    generated = getattr(result, "generated_c", None) or ""
    artifact = getattr(result, "stage_artifact", None)
    return {
        "serialized_sha256": sha256_bytes(result_to_json(result).encode("utf-8")),
        "generated_sha256": sha256_bytes(generated.encode("utf-8")),
        "request_fingerprint": _fingerprint_value(
            getattr(result, "request_fingerprint", None)
        ),
        "output_fingerprint": _fingerprint_value(
            getattr(result, "output_fingerprint", None)
        ),
        "artifact_fingerprint": _fingerprint_value(
            None if artifact is None else artifact.artifact_fingerprint
        ),
    }


def _fresh_process_errors(root: Path, result: object) -> list[str]:
    code = (
        "import hashlib,json; "
        "from pycforge import ConversionRequest,PythonToCConverter; "
        "from pycforge.converter.core.request import ObservationOptions; "
        "from pycforge.converter.core.serialization import result_to_json; "
        f"r=PythonToCConverter().convert(ConversionRequest.from_source({KEYWORD_SOURCE!r},"
        f"rule_set_version={DEFAULT_RULE_SET!r},renderer_version={DEFAULT_RENDERER!r}),"
        "observation=ObservationOptions('Full',False)); "
        "print(json.dumps({"
        "'serialized_sha256':hashlib.sha256(result_to_json(r).encode()).hexdigest(),"
        "'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
        "'request_fingerprint':None if r.request_fingerprint is None else r.request_fingerprint.value,"
        "'output_fingerprint':None if r.output_fingerprint is None else r.output_fingerprint.value,"
        "'artifact_fingerprint':None if r.stage_artifact is None else r.stage_artifact.artifact_fingerprint.value"
        "},sort_keys=True))"
    )
    environment = dict(os.environ)
    prior = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(root) if not prior else str(root) + os.pathsep + prior
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return ["fresh Python process conversion failed: " + completed.stderr.strip()]
    try:
        actual = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [f"fresh Python process returned invalid evidence: {exc}"]
    expected = _keyword_evidence(result)
    return [] if actual == expected else ["fresh Python process changed deterministic fingerprints"]


def accepted_keyword_errors(
    root: Path = ROOT, *, fresh_process: bool = True
) -> list[str]:
    """Validate the exact 14C fact, plan, and lowering vertical slice."""

    request = ConversionRequest.from_source(
        KEYWORD_SOURCE,
        rule_set_version=DEFAULT_RULE_SET,
        renderer_version=DEFAULT_RENDERER,
    )
    observation = ObservationOptions("Full", False)
    first = PythonToCConverter().convert(request, observation=observation)
    second = PythonToCConverter().convert(request, observation=observation)
    if first.status is not ResultStatus.CONVERTED or first.generated_c is None:
        return ["accepted Phase 14C keyword witness did not convert"]
    if second.status is not ResultStatus.CONVERTED or second.generated_c is None:
        return ["repeated Phase 14C keyword witness did not convert"]
    if first.stage_artifact is None:
        return ["accepted Phase 14C keyword witness omitted its final artifact"]

    errors: list[str] = []
    if result_to_json(first) != result_to_json(second):
        errors.append("Phase 14C keyword conversion is not deterministic")
    if fresh_process:
        errors.extend(_fresh_process_errors(Path(root), first))
    if not validate_c_text(first.generated_c).accepted:
        errors.append("Phase 14C generated C failed textual conformance")
    expected_fingerprints = {
        "generated": (sha256_bytes(first.generated_c.encode("utf-8")), KEYWORD_GENERATED_C_SHA256),
        "request": (_fingerprint_value(first.request_fingerprint), KEYWORD_REQUEST_SHA256),
        "output": (_fingerprint_value(first.output_fingerprint), KEYWORD_OUTPUT_SHA256),
        "artifact": (
            _fingerprint_value(first.stage_artifact.artifact_fingerprint),
            KEYWORD_ARTIFACT_SHA256,
        ),
    }
    for label, (actual, expected) in expected_fingerprints.items():
        if actual != expected:
            errors.append(f"Phase 14C keyword {label} fingerprint changed")

    artifact = first.stage_artifact
    payload = artifact.payload
    if (
        artifact.kind != "generated_c"
        or artifact.schema_version != "0.14.2"
        or payload.get("schema_version") != GENERATED_C_SCHEMA
        or payload.get("c_ir_schema") != C_IR_SCHEMA
        or payload.get("rule_set_version") != DEFAULT_RULE_SET
        or payload.get("renderer_version") != DEFAULT_RENDERER
        or not isinstance(payload.get("c_ir"), dict)
        or payload["c_ir"].get("schema_version") != C_IR_SCHEMA
    ):
        errors.append("accepted witness does not publish exact active Phase 14C identities")

    table = _table(payload, KEYWORD_CALL_TABLE_ID)
    records = table.get("records", ()) if table else ()
    facts = [record.get("value", {}) for record in records if isinstance(record, dict)]
    fact = facts[0] if len(facts) == 1 else {}
    if (
        table.get("schema_version") != KEYWORD_CALL_FACT_SCHEMA
        or table.get("producer_stage") != "analysis.plan"
        or table.get("key_domain") != KEYWORD_CALL_KEY_DOMAIN
        or table.get("completeness") != "complete"
        or tuple(table.get("invalidation_dependencies", ()))
        != KEYWORD_CALL_TABLE_DEPENDENCIES
        or len(records) != 1
        or records[0].get("key") != fact.get("call_node_id")
        or tuple(records[0].get("provenance", {}).get("evidence", ()))
        != KEYWORD_CALL_PROVENANCE_EVIDENCE
    ):
        errors.append("accepted witness has an incomplete keyword-call fact table")
    elif (
        fact.get("parameter_names") != ["left", "flag", "ratio"]
        or fact.get("parameter_categories")
        != ["integer-like", "boolean-like", "floating-like"]
        or fact.get("keyword_names") != ["ratio", "left", "flag"]
        or fact.get("source_argument_categories")
        != ["floating-like", "integer-like", "boolean-like"]
        or fact.get("source_to_parameter_ordinals") != [2, 0, 1]
        or fact.get("parameter_to_source_ordinals") != [1, 2, 0]
        or fact.get("evaluation_order") != fact.get("source_argument_node_ids")
        or fact.get("parameter_argument_node_ids")
        != [
            fact.get("source_argument_node_ids", [None, None, None])[1],
            fact.get("source_argument_node_ids", [None, None, None])[2],
            fact.get("source_argument_node_ids", [None, None, None])[0],
        ]
        or fact.get("arguments_evaluated_once") is not True
        or fact.get("parameter_coverage_exact") is not True
        or fact.get("lowering_shape") != KEYWORD_CALL_LOWERING_SHAPE
        or fact.get("allocation_model") != "none"
        or fact.get("cleanup_model") != "none"
        or fact.get("runtime_binding_failure") != "proved-absent"
        or fact.get("supported") is not True
        or fact.get("diagnostic_code") is not None
        or fact.get("rejection_node_id") is not None
    ):
        errors.append("keyword-call binding proof does not separate source/formal order")

    valid, reason = validate_keyword_call_binding_facts(
        payload,
        expected_fact_schema=KEYWORD_CALL_FACT_SCHEMA,
    )
    if not valid:
        errors.append("independent keyword-call reconstruction failed: " + reason)

    plans = [
        item
        for item in payload.get("rule_plans", ())
        if isinstance(item, dict) and item.get("rule_id") == KEYWORD_CALL_RULE_ID
    ]
    plan = plans[0] if len(plans) == 1 else {}
    obligations = tuple(plan.get("semantic_obligations", ()))
    if (
        len(plans) != 1
        or plan.get("rule_version") != KEYWORD_CALL_RULE_VERSION
        or plan.get("support_state") != "SupportedDirect"
        or plan.get("source_node_id") != fact.get("call_node_id")
        or tuple(plan.get("resolved_obligations", ())) != obligations
        or plan.get("unresolved_obligations")
        or plan.get("helper_requirements")
        or not set(KEYWORD_CALL_OBLIGATIONS).issubset(obligations)
        or not any(
            str(item).startswith("keyword-call-binding:")
            for item in plan.get("facts_used", ())
        )
    ):
        errors.append("accepted witness does not publish one closed Phase 14C RulePlan")

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
        item
        for statement in run.get("body", {}).get("statements", ())
        for item in _walk_dicts(statement)
        if item.get("kind") == "CCallExpr"
    ]
    call_order = [_call_name(item, names) for item in calls]
    target = next((item for item in calls if _call_name(item, names) == "choose"), {})
    target_argument_ids = [item.get("binding_id") for item in target.get("arguments", ())]
    declarations = {
        item.get("identifier", {}).get("binding_id"): item
        for item in run.get("body", {}).get("statements", ())
        if isinstance(item, dict) and item.get("kind") == "CVariableDeclaration"
    }

    def originating_call(binding_id: object) -> str | None:
        seen: set[object] = set()
        while binding_id not in seen:
            seen.add(binding_id)
            declaration = declarations.get(binding_id)
            if not declaration:
                return None
            initializer = declaration.get("initializer", {})
            if initializer.get("kind") == "CCallExpr":
                return _call_name(initializer, names)
            if initializer.get("kind") != "CIdentifierRef":
                return None
            binding_id = initializer.get("binding_id")
        return None

    if (
        call_order != ["mark_float", "mark_int", "mark_bool", "choose"]
        or [originating_call(item) for item in target_argument_ids]
        != ["mark_int", "mark_bool", "mark_float"]
        or [item.get("kind") for item in target.get("arguments", ())]
        != ["CIdentifierRef", "CIdentifierRef", "CIdentifierRef"]
    ):
        errors.append("structured C IR does not stage source order then call formal order")

    mappings = [
        item
        for item in payload.get("source_output_mappings", ())
        if isinstance(item, dict) and item.get("rule_plan_id") == plan.get("plan_id")
    ]
    if not mappings or any(
        not item.get("source_document_id")
        or not isinstance(item.get("start_byte"), int)
        or not isinstance(item.get("end_byte"), int)
        or item["start_byte"] >= item["end_byte"]
        for item in mappings
    ):
        errors.append("keyword-call lowering omits source-to-C mappings")

    summary = first.conversion_summary or {}
    trace = first.decision_trace or {}
    if (
        summary.get("schema_version") != CONVERSION_SUMMARY_SCHEMA
        or summary.get("rule_set_version") != DEFAULT_RULE_SET
        or summary.get("renderer_version") != DEFAULT_RENDERER
        or list(summary.get("keyword_calls", ())) != facts
        or trace.get("schema_version") != DECISION_TRACE_SCHEMA
        or trace.get("trace_level") != "Full"
        or trace.get("completeness") != "complete"
        or trace.get("truncated") is not False
        or trace.get("observer_failed") is not False
        or [
            item
            for item in trace.get("rule_decisions", ())
            if item.get("rule_id") == KEYWORD_CALL_RULE_ID
        ]
        != plans
    ):
        errors.append("summary or decision trace omits exact Phase 14C evidence")
    if (
        payload.get("helper_requirements") != []
        or payload.get("helper_manifest") != []
        or payload.get("helper_registry_fingerprint") != HELPER_REGISTRY_SHA256
    ):
        errors.append("keyword-call binding changed helper ownership")
    return errors


def rejection_matrix_errors() -> list[str]:
    """Require the closed, primary-diagnostic Phase 14C rejection matrix."""

    converter = PythonToCConverter()
    errors: list[str] = []
    negative_fact_cases = {
        "positional-only-name",
        "unknown-name",
        "positional-keyword-collision",
        "duplicate-keyword",
        "missing-parameter",
        "mapped-category",
    }
    for label, source, expected_code in REJECTION_CASES:
        result = converter.convert(ConversionRequest.from_source(source))
        if (
            result.status is not ResultStatus.REJECTED
            or [item.code for item in result.diagnostics] != [expected_code]
            or result.generated_c is not None
            or result.output_fingerprint is not None
            or result.stage_artifact is None
            or result.stage_artifact.kind not in {"python_ir", "conversion_plan"}
            or "c_ir" in result.stage_artifact.payload
            or "helper_manifest" in result.stage_artifact.payload
        ):
            errors.append(
                f"{label} did not reject atomically with exactly {expected_code}"
            )
            continue
        if label in negative_fact_cases:
            records = _table(
                result.stage_artifact.payload, KEYWORD_CALL_TABLE_ID
            ).get("records", ())
            fact = records[0].get("value", {}) if len(records) == 1 else {}
            if (
                len(records) != 1
                or fact.get("supported") is not False
                or fact.get("diagnostic_code") != expected_code
                or not fact.get("reason")
                or not fact.get("rejection_node_id")
                or records[0].get("key") != fact.get("call_node_id")
            ):
                errors.append(f"{label} omitted its complete negative binding fact")
    return errors


def bounded_profile_errors() -> list[str]:
    """Cover the mixed positional-only and explicit cross-module profiles."""

    mixed_source = (
        "def choose(head: int, /, flag: bool, ratio: float) -> int:\n"
        "    return head\n\n"
        "def run(x: int, y: bool, z: float) -> int:\n"
        "    return choose(x, ratio=z, flag=y)\n"
    )
    mixed = PythonToCConverter().convert(ConversionRequest.from_source(mixed_source))
    if mixed.status is not ResultStatus.CONVERTED or mixed.stage_artifact is None:
        return ["mixed positional-only keyword witness did not convert"]
    mixed_records = _table(
        mixed.stage_artifact.payload, KEYWORD_CALL_TABLE_ID
    ).get("records", ())
    mixed_fact = mixed_records[0].get("value", {}) if len(mixed_records) == 1 else {}
    errors: list[str] = []
    if (
        len(mixed_records) != 1
        or mixed_fact.get("positional_only_parameter_count") != 1
        or mixed_fact.get("parameter_names") != ["head", "flag", "ratio"]
        or mixed_fact.get("source_to_parameter_ordinals") != [0, 2, 1]
        or mixed_fact.get("parameter_to_source_ordinals") != [0, 2, 1]
        or mixed_fact.get("supported") is not True
    ):
        errors.append("mixed positional-only keyword binding evidence is incomplete")

    primary = (
        "from lib import choose\n\n"
        "def run(value: int, flag: bool, ratio: float) -> int:\n"
        "    return choose(ratio=ratio, flag=flag, left=value)\n"
    )
    companion = (
        "def choose(left: int, flag: bool, ratio: float) -> int:\n"
        "    return left\n"
    )
    bundle = SourceBundle(
        SourceDocumentInput("app.py", primary, "app"),
        (SourceDocumentInput("lib.py", companion, "lib"),),
    )
    cross = PythonToCConverter().convert(ConversionRequest(bundle))
    if cross.status is not ResultStatus.CONVERTED or cross.stage_artifact is None:
        return errors + ["cross-module keyword witness did not convert"]
    payload = cross.stage_artifact.payload
    records = _table(payload, KEYWORD_CALL_TABLE_ID).get("records", ())
    fact = records[0].get("value", {}) if len(records) == 1 else {}
    functions = {
        item.get("value", {}).get("function_node_id"): item.get("value", {})
        for item in _table(payload, "module-function-facts").get("records", ())
        if isinstance(item, dict)
    }
    if (
        len(records) != 1
        or functions.get(fact.get("target_function_node_id"), {}).get("module_id")
        != "lib"
        or fact.get("parameter_names") != ["left", "flag", "ratio"]
        or fact.get("source_to_parameter_ordinals") != [2, 1, 0]
        or fact.get("supported") is not True
        or (cross.conversion_summary or {})
        .get("module_initialization", {})
        .get("module_order")
        != ["lib", "app"]
    ):
        errors.append("cross-module exact keyword target evidence is incomplete")
    return errors


def independent_tamper_errors() -> list[str]:
    """Prove producer-independent validation rejects order, AST, and plan forgery."""

    result = PythonToCConverter().convert(ConversionRequest.from_source(KEYWORD_SOURCE))
    if result.status is not ResultStatus.CONVERTED or result.stage_artifact is None:
        return ["tamper baseline keyword conversion failed"]
    baseline = json.loads(json.dumps(dict(result.stage_artifact.payload)))
    baseline["schema_version"] = CONVERSION_PLAN_SCHEMA
    valid, reason = validate_analysis_payload(baseline)
    if not valid:
        return ["tamper baseline analysis payload is invalid: " + reason]

    def feature_record(payload: dict[str, Any]) -> dict[str, Any]:
        return _table(payload, KEYWORD_CALL_TABLE_ID)["records"][0]

    mutations = (
        ("source order", lambda payload: feature_record(payload)["value"]["source_argument_node_ids"].reverse()),
        ("formal permutation", lambda payload: feature_record(payload)["value"]["parameter_to_source_ordinals"].reverse()),
        ("provenance", lambda payload: feature_record(payload)["provenance"].update(source_node_ids=[])),
        (
            "Python IR keyword",
            lambda payload: next(
                item
                for item in payload["python_ir"]["nodes"]
                if item["node_id"] == feature_record(payload)["value"]["keyword_node_ids"][0]
            )["fields"].update(arg="left"),
        ),
        (
            "RulePlan obligations",
            lambda payload: next(
                item
                for item in payload["rule_plans"]
                if item["rule_id"] == KEYWORD_CALL_RULE_ID
            ).update(semantic_obligations=["forged"], resolved_obligations=["forged"]),
        ),
    )
    errors: list[str] = []
    for label, mutate in mutations:
        payload = deepcopy(baseline)
        mutate(payload)
        valid, reason = validate_analysis_payload(payload)
        if valid or not reason:
            errors.append(f"independent validation accepted {label} tampering")
    return errors


def cancellation_errors() -> list[str]:
    """Require cancellation to retire artifacts and interrupt reconstruction."""

    errors: list[str] = []
    token = CancellationToken()
    token.cancel()
    result = PythonToCConverter().convert(
        ConversionRequest.from_source(KEYWORD_SOURCE), cancellation=token
    )
    if (
        result.status is not ResultStatus.CANCELED
        or [item.code for item in result.diagnostics] != ["PYC1901"]
        or result.generated_c is not None
        or result.output_fingerprint is not None
    ):
        errors.append("pre-canceled keyword conversion did not retire output atomically")

    baseline = PythonToCConverter().convert(ConversionRequest.from_source(KEYWORD_SOURCE))
    if baseline.stage_artifact is None:
        return errors + ["cancellation reconstruction baseline omitted its artifact"]
    payload = dict(baseline.stage_artifact.payload)
    validator_token = CancellationToken()
    validator_token.cancel()
    try:
        validate_keyword_call_binding_facts(
            payload,
            expected_fact_schema=KEYWORD_CALL_FACT_SCHEMA,
            cancellation=validator_token,
        )
    except KeywordCallValidationCanceled:
        pass
    else:
        errors.append("independent keyword validator ignored cancellation")
    return errors


def historical_phase14b_errors() -> list[str]:
    """Require exact explicit 14B rejection and no-keyword compatibility."""

    converter = PythonToCConverter()
    observation = ObservationOptions("Full", False)
    contract_errors = exact_mapping_errors(
        historical_phase14b_contracts(),
        EXPECTED_PHASE14B_CONTRACTS,
        "historical Phase 14B contracts",
    )
    if contract_errors:
        return contract_errors
    historical_keyword = converter.convert(
        ConversionRequest.from_source(
            HISTORICAL_KEYWORD_SOURCE,
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        ),
        observation=observation,
    )
    errors: list[str] = []
    payload = (
        {} if historical_keyword.stage_artifact is None else historical_keyword.stage_artifact.payload
    )
    if (
        historical_keyword.status is not ResultStatus.REJECTED
        or [item.code for item in historical_keyword.diagnostics] != ["PYC2910"]
        or [item.diagnostic_id for item in historical_keyword.diagnostics]
        != ["diag-33b10f68721e38b3e960"]
        or _fingerprint_value(historical_keyword.request_fingerprint)
        != "c447d082bb1b12228b0e7fd80ed17c438063f0591ffee2b4b240031fc6d9187f"
        or historical_keyword.stage_artifact is None
        or historical_keyword.stage_artifact.kind != "conversion_plan"
        or historical_keyword.stage_artifact.schema_version != "0.14.1"
        or _fingerprint_value(historical_keyword.stage_artifact.artifact_fingerprint)
        != "8daf5c369e7ea4e61521bebbae32efccd4ede450e375b09bc44f37ed9d0540c5"
        or payload.get("schema_version") != PHASE14B_CONVERSION_PLAN_SCHEMA
        or (historical_keyword.conversion_summary or {}).get("schema_version")
        != PHASE14B_CONVERSION_SUMMARY_SCHEMA
        or (historical_keyword.decision_trace or {}).get("schema_version")
        != PHASE14B_DECISION_TRACE_SCHEMA
        or KEYWORD_CALL_TABLE_ID
        in {item.get("table_id") for item in payload.get("fact_tables", ())}
        or historical_keyword.generated_c is not None
        or historical_keyword.output_fingerprint is not None
    ):
        errors.append("explicit Phase 14B keyword rejection envelope changed")

    active = converter.convert(ConversionRequest.from_source(POSITIONAL_SOURCE))
    historical = converter.convert(
        ConversionRequest.from_source(
            POSITIONAL_SOURCE,
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        )
    )
    if (
        active.status is not ResultStatus.CONVERTED
        or historical.status is not ResultStatus.CONVERTED
        or active.generated_c != historical.generated_c
        or active.output_fingerprint != historical.output_fingerprint
        or sha256_bytes((active.generated_c or "").encode("utf-8"))
        != POSITIONAL_COMPATIBILITY_C_SHA256
        or _fingerprint_value(active.output_fingerprint)
        != POSITIONAL_COMPATIBILITY_OUTPUT_SHA256
        or active.stage_artifact is None
        or active.stage_artifact.schema_version != "0.14.2"
        or historical.stage_artifact is None
        or historical.stage_artifact.schema_version != "0.14.1"
        or historical.stage_artifact.payload.get("schema_version")
        != PHASE14B_GENERATED_C_SCHEMA
        or historical.stage_artifact.payload.get("c_ir_schema") != PHASE14B_C_IR_SCHEMA
        or _table(active.stage_artifact.payload, KEYWORD_CALL_TABLE_ID).get("records")
        != []
    ):
        errors.append("active no-keyword output changed explicit Phase 14B compatibility")
    return errors


def converter_smoke_errors(root: Path = ROOT) -> list[str]:
    return list(
        dict.fromkeys(
            accepted_keyword_errors(root)
            + bounded_profile_errors()
            + rejection_matrix_errors()
            + independent_tamper_errors()
            + cancellation_errors()
            + historical_phase14b_errors()
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
        "specifications/phase14c_direct_keyword_calls.md",
        "transition/phase_14c/baseline_fingerprint.json",
        "transition/phase_14c/breadth_and_change_budgets.md",
        "transition/phase_14c/direct_keyword_calls_decision.md",
        "transition/phase_14c/entry_criteria.md",
        "transition/phase_14c/opening_evidence.md",
        "transition/phase_14c/rollback_conditions.md",
        "evidence/phase_14c/conversion_debt.json",
        "evidence/phase_14c/entry_report.json",
    }


def _promoted_required_files(manifest: Mapping[str, object]) -> set[str]:
    declared = manifest.get("required_contract_files", ())
    names = set(declared) if isinstance(declared, list) else set()
    return names | _opening_required_files() | {
        "PyCForge_Phase_14C_v0_14_2_Project_Handoff.txt",
        "pycforge/converter/keyword_calls/__init__.py",
        "pycforge/converter/keyword_calls/analysis.py",
        "pycforge/converter/keyword_calls/lowering.py",
        "pycforge/converter/keyword_calls/model.py",
        "pycforge/converter/keyword_calls/validation.py",
        "tests/test_phase14c_keyword_contracts.py",
        "tests/test_phase14c_keyword_analysis.py",
        "tests/test_phase14c_keyword_lowering.py",
        "tests/test_phase14c_keyword_hardening.py",
        "tests/test_phase14c_keyword_audits.py",
        "tests/test_validate_phase14c.py",
        "tools/validate_phase14c.py",
        "transition/phase_14c/gate_evidence.md",
        "transition/phase_14c/manifest.json",
        "transition/phase_14c/release_fingerprint.json",
        "evidence/phase_14c/release_report.json",
    }


def predecessor_errors(archive: Path) -> list[str]:
    if not archive.is_file():
        return [f"requested predecessor archive is absent: {archive}"]
    errors: list[str] = []
    if archive.stat().st_size != PREDECESSOR_ARCHIVE_SIZE:
        errors.append(f"sealed Phase 14B archive size mismatch: {archive.stat().st_size}")
    digest = sha256_bytes(archive.read_bytes())
    if digest != PREDECESSOR_ARCHIVE_SHA256:
        errors.append(f"sealed Phase 14B archive hash mismatch: {digest}")
        return errors
    try:
        # Phase 14B's alphanumeric directory is deliberately explicit: the
        # predecessor's canonical identity omits this exact self-reference.
        tree_digest = canonical_archive_tree_hash(
            archive, fingerprint_to_omit=PREDECESSOR_FINGERPRINT
        )
        converter_digest = canonical_archive_subtree_hash(archive, "pycforge/converter")
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot authenticate predecessor archive: {exc}"]
    if tree_digest != PREDECESSOR_TREE_SHA256:
        errors.append(f"sealed Phase 14B tree hash mismatch: {tree_digest}")
    if converter_digest != PREDECESSOR_CONVERTER_SHA256:
        errors.append(f"sealed Phase 14B converter subtree hash mismatch: {converter_digest}")
    return errors


def predecessor_wheel_errors(wheel: Path) -> list[str]:
    if not wheel.is_file():
        return [f"requested predecessor wheel is absent: {wheel}"]
    errors: list[str] = []
    if wheel.name != PREDECESSOR_WHEEL_NAME:
        errors.append("sealed Phase 14B wheel name mismatch")
    if wheel.stat().st_size != PREDECESSOR_WHEEL_SIZE:
        errors.append("sealed Phase 14B wheel size mismatch")
    if sha256_bytes(wheel.read_bytes()) != PREDECESSOR_WHEEL_SHA256:
        errors.append("sealed Phase 14B wheel hash mismatch")
        return errors
    try:
        with zipfile.ZipFile(wheel) as package:
            names = set(package.namelist())
            metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
            metadata = package.read(metadata_name).decode("utf-8")
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
        return errors + [f"cannot inspect predecessor wheel: {exc}"]
    if "Version: 0.14.1\n" not in metadata:
        errors.append("sealed Phase 14B wheel metadata version mismatch")
    if "pycforge/converter/conditional_regions/validation.py" not in names:
        errors.append("sealed Phase 14B wheel omits its conditional-region package")
    if any(name.endswith((".so", ".dll", ".dylib", ".pyd")) for name in names):
        errors.append("sealed Phase 14B wheel unexpectedly contains native binaries")
    return errors


def _artifact_expectation(
    fingerprint: Mapping[str, object], key: str
) -> Mapping[str, object]:
    artifacts = fingerprint.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    value = artifacts.get(key, {})
    return value if isinstance(value, dict) else {}


def wheel_errors(wheel: Path, fingerprint: Mapping[str, object]) -> list[str]:
    if not wheel.is_file():
        return [f"requested wheel is absent: {wheel}"]
    expected = _artifact_expectation(fingerprint, "wheel")
    errors: list[str] = []
    digest = sha256_bytes(wheel.read_bytes())
    if expected.get("filename") != wheel.name:
        errors.append("wheel name does not match the release fingerprint")
    if expected.get("sha256") != digest:
        errors.append("wheel hash does not match the release fingerprint")
    if expected.get("size") != wheel.stat().st_size:
        errors.append("wheel size does not match the release fingerprint")
    if expected.get("fixed_epoch_builds_byte_identical") is not True:
        errors.append("wheel fingerprint omits byte-identical fixed-epoch builds")
    if expected.get("isolated_install_passed") is not True:
        errors.append("wheel fingerprint omits isolated-install validation")
    try:
        with zipfile.ZipFile(wheel) as package:
            names = set(package.namelist())
            metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
            metadata = package.read(metadata_name).decode("utf-8")
    except (OSError, zipfile.BadZipFile, KeyError, StopIteration, UnicodeError) as exc:
        return errors + [f"cannot inspect wheel: {exc}"]
    if f"Version: {RELEASE_VERSION}\n" not in metadata:
        errors.append("wheel metadata version mismatch")
    required = {
        "pycforge/converter/keyword_calls/__init__.py",
        "pycforge/converter/keyword_calls/analysis.py",
        "pycforge/converter/keyword_calls/lowering.py",
        "pycforge/converter/keyword_calls/model.py",
        "pycforge/converter/keyword_calls/validation.py",
    }
    if required - names:
        errors.append("wheel omits one or more Phase 14C keyword-call modules")
    if any(name.endswith((".so", ".dll", ".dylib", ".pyd")) for name in names):
        errors.append("wheel unexpectedly contains native binaries")
    return errors


def source_archive_errors(
    archive: Path, fingerprint: Mapping[str, object]
) -> list[str]:
    if not archive.is_file():
        return [f"requested Phase 14C source archive is absent: {archive}"]
    expected = _artifact_expectation(fingerprint, "source_archive")
    errors: list[str] = []
    if expected.get("filename") != archive.name:
        errors.append("source archive name does not match the release fingerprint")
    if _is_sha256(expected.get("sha256")) and expected.get("sha256") != sha256_bytes(archive.read_bytes()):
        errors.append("source archive hash does not match the release fingerprint")
    if isinstance(expected.get("size"), int) and expected.get("size") != archive.stat().st_size:
        errors.append("source archive size does not match the release fingerprint")
    if expected.get("normalized_builds_byte_identical") is not True:
        errors.append("source archive fingerprint omits deterministic duplicate builds")
    try:
        archive_tree = canonical_archive_tree_hash(
            archive, fingerprint_to_omit=RELEASE_FINGERPRINT
        )
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot inspect Phase 14C source archive: {exc}"]
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
            errors.append("Phase 14C release fingerprint metadata is invalid")
        expected_tree = fingerprint.get("value")
        if not _is_sha256(expected_tree):
            errors.append("Phase 14C release fingerprint value is not finalized")
        else:
            actual_tree = canonical_release_tree_hash(root)
            if expected_tree != actual_tree:
                errors.append(f"Phase 14C release tree hash mismatch: {actual_tree}")
        if (
            fingerprint.get("predecessor_version") != PREDECESSOR_VERSION
            or fingerprint.get("predecessor_archive_sha256") != PREDECESSOR_ARCHIVE_SHA256
            or fingerprint.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or fingerprint.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
        ):
            errors.append("release fingerprint predecessor identity mismatch")
        tests = fingerprint.get("tests", {})
        if (
            not isinstance(tests, dict)
            or not isinstance(tests.get("discovered"), int)
            or tests.get("discovered", 0) < 413
            or tests.get("failed") != 0
        ):
            errors.append("release fingerprint regression evidence is incomplete")
        for key in (
            "c_toolchain_invoked",
            "promoted_candidate_toolchain_invoked",
            "compiler_linker_loader_or_execution_invoked",
            "generated_c_compiled_or_executed",
        ):
            if fingerprint.get(key) is not False:
                errors.append(f"release fingerprint does not explicitly keep {key} false")
        if fingerprint.get("phase_14d_started") is not False:
            errors.append("release fingerprint does not keep Phase 14D closed")
        if fingerprint.get("phase_15_started") is not False:
            errors.append("release fingerprint does not keep Phase 15 closed")
    return errors


def _audit_calls(root: Path, *, include_phase14c_transition: bool):
    calls: list[tuple[str, Any]] = [
        ("architecture", lambda: laboratory_audits.audit_architecture(root)),
        ("rules", lambda: laboratory_audits.audit_rules(root)),
        ("helpers", lambda: laboratory_audits.audit_helpers(root)),
        ("containers", lambda: laboratory_audits.audit_containers(root)),
        ("modules", lambda: laboratory_audits.audit_modules(root)),
        ("records", lambda: laboratory_audits.audit_records(root)),
        ("numeric", lambda: laboratory_audits.audit_numeric(root)),
        ("conditional", lambda: laboratory_audits.audit_conditional(root)),
    ]
    audit_keyword = getattr(laboratory_audits, "audit_keyword", None)
    if callable(audit_keyword):
        calls.append(("keyword", lambda: audit_keyword(root)))
    calls.extend(
        [
            ("determinism", lambda: laboratory_audits.audit_determinism(root)),
            (
                "sealed Phase 14B transition",
                lambda: laboratory_audits.audit_transition(root, "phase_14b"),
            ),
        ]
    )
    if include_phase14c_transition:
        calls.append(
            (
                "Phase 14C transition",
                lambda: laboratory_audits.audit_transition(root, "phase_14c"),
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
    manifest_path = root / "transition/phase_14c/manifest.json"
    manifest = (
        _load_json(manifest_path, "Phase 14C manifest", errors)
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
            errors.append("Phase 14C manifest identity mismatch")
        if require_promoted and manifest.get("status") != "promoted":
            errors.append("Phase 14C manifest is not promoted")
        if (
            manifest.get("predecessor_version") != PREDECESSOR_VERSION
            or manifest.get("predecessor_archive_sha256") != PREDECESSOR_ARCHIVE_SHA256
            or manifest.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or manifest.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
            or manifest.get("predecessor_wheel_sha256") != PREDECESSOR_WHEEL_SHA256
        ):
            errors.append("Phase 14C manifest predecessor identity mismatch")
        schemas = manifest.get("schemas")
        if isinstance(schemas, dict):
            errors.extend(
                exact_mapping_errors(schemas, EXPECTED_CONTRACTS, "Phase 14C manifest contracts")
            )
        elif require_promoted:
            errors.append("Phase 14C manifest contracts are not finalized")
        if require_promoted:
            required_tests = manifest.get("required_tests")
            if not isinstance(required_tests, int) or required_tests < 413:
                errors.append("Phase 14C required-test count is below its predecessor gate")
            promotion = manifest.get("promotion", {})
            if (
                not isinstance(promotion, dict)
                or promotion.get("implemented") is not True
                or promotion.get("validated") is not True
                or promotion.get("promoted") is not True
                or promotion.get("release_fingerprint_assigned") is not True
                or promotion.get("c_toolchain_invoked") is not False
                or any(
                    promotion.get(key) is not False
                    for key in (
                        "generated_c_compiled",
                        "generated_c_linked",
                        "generated_c_loaded",
                        "generated_c_executed",
                    )
                )
            ):
                errors.append("Phase 14C manifest promotion evidence is incomplete")
            phase14d = manifest.get("phase_14d", {})
            phase15 = manifest.get("phase_15", {})
            if not isinstance(phase14d, dict) or phase14d.get("automatic_open") is not False:
                errors.append("Phase 14C manifest does not keep Phase 14D closed")
            if not isinstance(phase15, dict) or phase15.get("automatic_open") is not False:
                errors.append("Phase 14C manifest does not keep Phase 15 closed")

    errors.extend(
        exact_mapping_errors(current_contracts(), EXPECTED_CONTRACTS, "active contracts")
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
        _promoted_required_files(manifest) if require_promoted else _opening_required_files()
    )
    for name in sorted(required_files):
        if not (root / name).is_file():
            errors.append(f"missing Phase 14C release file: {name}")
    for name, expected in (
        ("docs/python_to_c_converter_architecture_revision_3_1.txt", ROADMAP_SHA256),
        ("docs/python_to_c_converter_architecture_revision_3_2_addendum.md", ADDENDUM_SHA256),
    ):
        path = root / name
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"{Path(name).name} hash mismatch")
    if default_helper_registry().fingerprint != HELPER_REGISTRY_SHA256:
        errors.append("Phase 10 helper registry identity changed")

    for name, call in _audit_calls(
        root, include_phase14c_transition=require_promoted or manifest_path.is_file()
    ):
        try:
            report = call()
        except Exception as exc:
            errors.append(f"{name} audit raised {type(exc).__name__}: {exc}")
        else:
            if report.get("passed") is not True:
                errors.append(f"{name} audit failed: {report}")
            if name in {"conditional", "keyword"} and (
                report.get("c_toolchain_invoked", False) is not False
                or report.get("generated_c_compiled_or_executed", False) is not False
            ):
                errors.append(f"{name} audit does not preserve the no-toolchain boundary")
    if converter_smoke:
        errors.extend(converter_smoke_errors(root))
    if predecessor_archive is not None:
        errors.extend(predecessor_errors(Path(predecessor_archive)))
    if predecessor_wheel is not None:
        errors.extend(predecessor_wheel_errors(Path(predecessor_wheel)))

    fingerprint_path = root / RELEASE_FINGERPRINT
    fingerprint = (
        _load_json(fingerprint_path, "Phase 14C release fingerprint", errors)
        if require_promoted or fingerprint_path.is_file()
        else {}
    )
    if fingerprint:
        errors.extend(_fingerprint_errors(root, fingerprint, require_promoted=require_promoted))
    if wheel is not None:
        errors.extend(wheel_errors(Path(wheel), fingerprint))
    if source_archive is not None:
        errors.extend(source_archive_errors(Path(source_archive), fingerprint))

    if require_promoted:
        try:
            state = (root / "CURRENT_STATE.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read CURRENT_STATE: {exc}")
        else:
            state_lower = state.lower()
            if (
                "Current release: `0.14.2`" not in state
                or "Phase 14C" not in state
                or "Release status: promoted" not in state
            ):
                errors.append("CURRENT_STATE does not identify a promoted Phase 14C release")
            if "windows 11" not in state_lower or "not claimed" not in state_lower:
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


def locate_predecessor_wheel(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_WHEEL_NAME,
        root.parent / PREDECESSOR_WHEEL_NAME,
        root.parents[1] / PREDECESSOR_WHEEL_NAME,
        root.parents[1] / "release" / PREDECESSOR_WHEEL_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def locate_wheel(root: Path = ROOT) -> Path | None:
    name = "pycforge-0.14.2-py3-none-any.whl"
    candidates = (root / "dist" / name, root / name, root.parent / name)
    return next((path for path in candidates if path.is_file()), None)


def locate_source_archive(root: Path = ROOT) -> Path | None:
    name = "pycforge_phase_14c_v0_14_2.tar.gz"
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
        help="validate implementation and opening evidence before promotion artifacts exist",
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
        errors.append("sealed Phase 14B predecessor archive is required but absent")
    if args.require_predecessor_wheel and predecessor_wheel is None:
        errors.append("sealed Phase 14B predecessor wheel is required but absent")
    if args.require_wheel and wheel is None:
        errors.append("Phase 14C wheel is required but absent")
    if args.require_source_archive and source_archive is None:
        errors.append("Phase 14C source archive is required but absent")
    if args.run_tests and not errors:
        failure = _run_tests(ROOT)
        if failure:
            errors.append(failure)

    if errors:
        print("PyCForge Phase 14C validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PyCForge Phase 14C validation passed")
    print(f"Release version: {RELEASE_VERSION}")
    print(f"Release tree SHA-256: {canonical_release_tree_hash(ROOT)}")
    print(f"Sealed Phase 14B predecessor archive verified: {predecessor is not None}")
    print(f"Sealed Phase 14B predecessor wheel verified: {predecessor_wheel is not None}")
    print(f"Phase 14C wheel verified: {wheel is not None}")
    print(f"Phase 14C source archive verified: {source_archive is not None}")
    print("This validator invoked no C compiler, linker, loader, or execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
