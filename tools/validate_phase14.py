"""Authenticate and validate the bounded PyCForge Phase 14A release.

This validator converts fixed Python witnesses and inspects their structured
artifacts.  Its arithmetic oracle is a Python reference model of the frozen
helper contracts.  It never compiles, links, loads, or executes generated C.
"""

from __future__ import annotations

import argparse
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

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, __version__  # noqa: E402
from pycforge.converter.c_output import validate_c_text  # noqa: E402
from pycforge.converter.contracts.configuration import (  # noqa: E402
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_TARGET_CONTRACT,
    PHASE14A_RENDERER,
    PHASE14A_RULE_SET,
    PHASE13_RENDERER,
    PHASE13_RULE_SET,
)
from pycforge.converter.contracts.versions import (  # noqa: E402
    CONTAINER_FACT_SCHEMA,
    MODULE_FACT_SCHEMA,
    NUMERIC_FACT_SCHEMA,
    PHASE14A_C_IR_SCHEMA,
    PHASE14A_CONVERSION_PLAN_SCHEMA,
    PHASE14A_CONVERSION_SUMMARY_SCHEMA,
    PHASE14A_DECISION_TRACE_SCHEMA,
    PHASE14A_GENERATED_C_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RECORD_FACT_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.converter.support_templates import (  # noqa: E402
    FLOOR_DIV_REFERENCE,
    FLOOR_MOD_REFERENCE,
    default_helper_registry,
)
from pycforge.laboratory.audits import (  # noqa: E402
    audit_architecture,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_modules,
    audit_numeric,
    audit_records,
    audit_rules,
    audit_transition,
)


RELEASE_VERSION = "0.14.0"
MINI_PHASE = "14A"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_13_v0_13_0.tar.gz"
PREDECESSOR_ARCHIVE_SHA256 = "36938f021db7110c590af878c748b5331ccc2d3de2f2144c3eb3b09d76fb998a"
PREDECESSOR_TREE_SHA256 = "483743b12fdd682b4b2ad488279ef243f00f0b055332096e5af09b0b01ab00a2"
PREDECESSOR_CONVERTER_SHA256 = "16d780e9eb5861f20ef3a1132928c32353aae97f99a3da526bc42386a0871dc6"
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
FLOOR_DIV_ASSET_SHA256 = "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869"
FLOOR_MOD_ASSET_SHA256 = "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e"
PHASE13_COMPATIBILITY_C_SHA256 = "d54ec54f5d9b0553d73c77179c3429928eb2c2deaa4963776429b628918cf257"
PHASE13_COMPATIBILITY_OUTPUT_SHA256 = "da9e27bd909e2ddf9154b072d668c98576a925aa7a342244db566d254ec0e556"
PHASE13_COMPATIBILITY_REQUEST_SHA256 = "a8cb25e7596427d78a9b6560e833786920216631f3179da4abc5a8a12fabe3fb"
RELEASE_FINGERPRINT = PurePosixPath("transition/phase_14/release_fingerprint.json")
FINGERPRINT_DOMAIN = "pycforge-phase-14-release-tree-v1"
TOOLCHAIN_INVOKED = False

DIV_HELPER = FLOOR_DIV_REFERENCE.canonical
MOD_HELPER = FLOOR_MOD_REFERENCE.canonical
EXPECTED_HELPERS = (DIV_HELPER, MOD_HELPER)
EXPECTED_ASSET_FINGERPRINTS = {
    DIV_HELPER: FLOOR_DIV_ASSET_SHA256,
    MOD_HELPER: FLOOR_MOD_ASSET_SHA256,
}

EXPECTED_CONTRACTS: Mapping[str, object] = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "numeric_facts": "fact-table/0.14",
    "conversion_plan": "conversion-plan/0.14",
    "c_ir": "c-ir/0.14",
    "generated_c": "generated-c/0.14",
    "conversion_summary": "pycforge.conversion-summary/0.14",
    "decision_trace": "pycforge.decision-trace/0.14",
    "result_serialization": "0.5",
    "rule_set": "phase14-bounded-numeric-v0.14",
    "renderer": "c-renderer-v0.14",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "numeric_policy": "phase14-proved-floor-arithmetic-v0.14",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
}

ACCEPTED_SOURCE = (
    "def left(value: int) -> int:\n"
    "    return value + 1\n"
    "\n"
    "def run(value: int) -> int:\n"
    "    first = left(value) // 3\n"
    "    second = value % -2\n"
    "    return first + second\n"
)

PHASE13_COMPATIBILITY_SOURCE = (
    "def plus(value: int) -> int:\n"
    "    return value + 1\n"
    "\n"
    "def run() -> int:\n"
    "    return plus(2)\n"
)

REJECTION_SOURCES: Mapping[str, tuple[str, str]] = {
    "float-right": ("PYC3701", "def f(value: int) -> int:\n    return value // 2.0\n"),
    "bool-right": ("PYC3701", "def f(value: int) -> int:\n    return value % True\n"),
    "prohibited-context": (
        "PYC3701",
        "def f(value: int) -> int:\n    inner = lambda: value // 2\n    return value\n",
    ),
    "zero": ("PYC3702", "def f(value: int) -> int:\n    return value // 0\n"),
    "negative-one": ("PYC3702", "def f(value: int) -> int:\n    return value % -1\n"),
    "variable": (
        "PYC3702",
        "def f(value: int, divisor: int) -> int:\n    return value // divisor\n",
    ),
    "folded-expression": (
        "PYC3702",
        "def f(value: int) -> int:\n    return value % (1 + 1)\n",
    ),
    "positive-out-of-range": (
        "PYC3702",
        "def f(value: int) -> int:\n    return value // 9223372036854775808\n",
    ),
    "int64-minimum": (
        "PYC3702",
        "def f(value: int) -> int:\n    return value % -9223372036854775808\n",
    ),
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


def _ephemeral(relative: PurePosixPath) -> bool:
    return (
        "__pycache__" in relative.parts
        or ".pytest_cache" in relative.parts
        or "build" in relative.parts
        or "dist" in relative.parts
        or relative.name.endswith((".pyc", ".pyo"))
    )


def canonical_release_tree_hash(root: Path = ROOT) -> str:
    """Hash a Phase 14 tree while excluding only its self-reference and ephemera."""

    files: dict[str, bytes] = {}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if relative != RELEASE_FINGERPRINT and not _ephemeral(relative):
            files[relative.as_posix()] = path.read_bytes()
    return _hash_file_map(files)


def archive_file_map(archive: Path) -> dict[str, bytes]:
    """Read a safe, single-root gzip tar and omit its highest-phase fingerprint."""

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

    fingerprints: list[tuple[int, str]] = []
    for name in files:
        match = re.fullmatch(r"transition/phase_(\d+)/release_fingerprint\.json", name)
        if match:
            fingerprints.append((int(match.group(1)), name))
    if fingerprints:
        files.pop(max(fingerprints)[1])
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
    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "numeric_facts": NUMERIC_FACT_SCHEMA,
        "conversion_plan": PHASE14A_CONVERSION_PLAN_SCHEMA,
        "c_ir": PHASE14A_C_IR_SCHEMA,
        "generated_c": PHASE14A_GENERATED_C_SCHEMA,
        "conversion_summary": PHASE14A_CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": PHASE14A_DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "rule_set": PHASE14A_RULE_SET,
        "renderer": PHASE14A_RENDERER,
        "module_policy": DEFAULT_MODULE_POLICY,
        "record_policy": DEFAULT_RECORD_POLICY,
        "numeric_policy": DEFAULT_NUMERIC_POLICY,
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


def _walk_dicts(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_dicts(child)


def _table(payload: Mapping[str, object], table_id: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in payload.get("fact_tables", ())
        if isinstance(item, dict) and item.get("table_id") == table_id
    ]
    return matches[0] if len(matches) == 1 else None


def _fingerprint_value(value: object) -> str | None:
    candidate = getattr(value, "value", None)
    return candidate if isinstance(candidate, str) else None


def _fresh_process_errors(root: Path, result: object) -> list[str]:
    generated = getattr(result, "generated_c", None) or ""
    output = getattr(result, "output_fingerprint", None)
    request = getattr(result, "request_fingerprint", None)
    artifact = getattr(result, "stage_artifact", None)
    expected = {
        "artifact_fingerprint": _fingerprint_value(
            None if artifact is None else artifact.artifact_fingerprint
        ),
        "generated_sha256": sha256_bytes(generated.encode("utf-8")),
        "output_fingerprint": _fingerprint_value(output),
        "request_fingerprint": _fingerprint_value(request),
    }
    code = (
        "import hashlib,json; "
        "from pycforge import ConversionRequest,PythonToCConverter; "
        f"r=PythonToCConverter().convert(ConversionRequest.from_source({ACCEPTED_SOURCE!r},"
        f"rule_set_version={PHASE14A_RULE_SET!r},renderer_version={PHASE14A_RENDERER!r})); "
        "a=r.stage_artifact; "
        "print(json.dumps({"
        "'artifact_fingerprint':None if a is None else a.artifact_fingerprint.value,"
        "'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
        "'output_fingerprint':None if r.output_fingerprint is None else r.output_fingerprint.value,"
        "'request_fingerprint':None if r.request_fingerprint is None else r.request_fingerprint.value"
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
    return [] if actual == expected else ["fresh Python process changed deterministic fingerprints"]


def accepted_numeric_errors(
    root: Path = ROOT, *, fresh_process: bool = True
) -> list[str]:
    errors: list[str] = []
    request = ConversionRequest.from_source(
        ACCEPTED_SOURCE,
        rule_set_version=PHASE14A_RULE_SET,
        renderer_version=PHASE14A_RENDERER,
    )
    first = PythonToCConverter().convert(request)
    second = PythonToCConverter().convert(request)
    if first.status is not ResultStatus.CONVERTED or first.generated_c is None:
        return ["accepted Phase 14A numeric witness did not convert"]
    if second.status is not ResultStatus.CONVERTED or second.generated_c is None:
        return ["repeated Phase 14A numeric witness did not convert"]
    if first.stage_artifact is None:
        return ["accepted Phase 14A numeric witness omitted its final artifact"]

    if result_to_json(first) != result_to_json(second):
        errors.append("Phase 14A numeric conversion is not deterministic")
    if fresh_process:
        errors.extend(_fresh_process_errors(Path(root), first))
    if not validate_c_text(first.generated_c).accepted:
        errors.append("Phase 14A generated C failed textual conformance")

    artifact = first.stage_artifact
    payload = artifact.payload
    if (
        artifact.kind != "generated_c"
        or artifact.schema_version != "0.14"
        or payload.get("schema_version") != PHASE14A_GENERATED_C_SCHEMA
        or payload.get("c_ir_schema") != PHASE14A_C_IR_SCHEMA
        or not isinstance(payload.get("c_ir"), dict)
        or payload["c_ir"].get("schema_version") != PHASE14A_C_IR_SCHEMA
        or payload.get("rule_set_version") != PHASE14A_RULE_SET
        or payload.get("renderer_version") != PHASE14A_RENDERER
        or payload.get("numeric_policy_version") != DEFAULT_NUMERIC_POLICY
    ):
        errors.append("accepted witness does not publish the exact active Phase 14 identities")

    fact_table = _table(payload, "numeric-operation-facts")
    records = [] if fact_table is None else fact_table.get("records", [])
    facts = [
        item.get("value", {}) for item in records if isinstance(item, dict)
    ]
    if (
        fact_table is None
        or fact_table.get("schema_version") != NUMERIC_FACT_SCHEMA
        or fact_table.get("producer_stage") != "analysis.plan"
        or fact_table.get("key_domain") != "binop-node-id"
        or fact_table.get("completeness") != "complete"
        or len(facts) != 2
    ):
        errors.append("accepted witness has an incomplete numeric fact table")
    else:
        if {item.get("operator_kind") for item in facts} != {
            "floor-divide",
            "floor-modulo",
        }:
            errors.append("numeric facts do not distinguish floor division and modulo")
        if {item.get("divisor_value") for item in facts} != {3, -2}:
            errors.append("numeric facts changed the proved divisor values")
        if {item.get("helper_requirement") for item in facts} != set(EXPECTED_HELPERS):
            errors.append("numeric facts do not select the exact frozen helpers")
        for fact, record in zip(facts, records):
            anchors = {
                fact.get("binop_node_id"),
                fact.get("function_node_id"),
                fact.get("operator_node_id"),
                fact.get("left_node_id"),
                fact.get("right_node_id"),
                *fact.get("divisor_literal_node_ids", ()),
            }
            provenance = record.get("provenance", {}).get("source_node_ids", ())
            if (
                record.get("key") != fact.get("binop_node_id")
                or not anchors.issubset(set(provenance))
                or fact.get("left_category") != "integer-like"
                or fact.get("right_category") != "integer-like"
                or fact.get("result_category") != "integer-like"
                or fact.get("left_c_type") != "int64_t"
                or fact.get("right_c_type") != "int64_t"
                or fact.get("result_c_type") != "int64_t"
                or fact.get("c_type") != "int64_t"
                or fact.get("evaluation_order")
                != [fact.get("left_node_id"), fact.get("right_node_id")]
                or fact.get("operands_evaluated_once") is not True
                or fact.get("divisor_in_admitted_domain") is not True
                or fact.get("divisor_nonzero_proved") is not True
                or fact.get("negative_one_divisor_excluded") is not True
                or fact.get("minimum_signed_divisor_excluded") is not True
                or fact.get("support_state") != "SupportedWithHelper"
                or fact.get("runtime_failure_channel") != "none"
                or fact.get("allocation_model") != "none"
                or fact.get("cleanup_model") != "none"
                or fact.get("target_contract") != DEFAULT_TARGET_CONTRACT
                or not all(
                    isinstance(fact.get(key), str) and fact.get(key)
                    for key in ("module_id", "document_id", "logical_name")
                )
            ):
                errors.append("numeric fact proof or provenance is incomplete")
                break

    plans = [
        item
        for item in payload.get("rule_plans", ())
        if isinstance(item, dict)
        and item.get("rule_id") == "phase14.numeric.floor_arithmetic"
    ]
    if (
        len(plans) != 2
        or {helper for plan in plans for helper in plan.get("helper_requirements", ())}
        != set(EXPECTED_HELPERS)
        or any(
            plan.get("rule_version") != "0.14"
            or plan.get("support_state") != "SupportedWithHelper"
            or plan.get("unresolved_obligations")
            or plan.get("resolved_obligations") != plan.get("semantic_obligations")
            for plan in plans
        )
    ):
        errors.append("accepted witness does not publish two closed Phase 14 RulePlans")

    registry = default_helper_registry()
    manifest = payload.get("helper_manifest", ())
    manifest_references = tuple(
        item.get("reference") for item in manifest if isinstance(item, dict)
    )
    manifest_assets = {
        item.get("reference"): item.get("asset_fingerprint")
        for item in manifest
        if isinstance(item, dict)
    }
    if (
        tuple(payload.get("helper_requirements", ())) != EXPECTED_HELPERS
        or manifest_references != EXPECTED_HELPERS
        or manifest_assets != EXPECTED_ASSET_FINGERPRINTS
        or any(item.get("factory_kind") != "structured-c-ir" for item in manifest)
        or payload.get("helper_registry_fingerprint") != HELPER_REGISTRY_SHA256
        or registry.fingerprint != HELPER_REGISTRY_SHA256
    ):
        errors.append("helper registry, requirement union, or asset identities changed")

    helper_calls = [
        item
        for item in _walk_dicts(payload.get("c_ir", {}))
        if item.get("kind") == "CCallExpr"
        and isinstance(item.get("callee"), dict)
        and str(item["callee"].get("binding_id", "")).startswith(
            "helper-binding:pycf.i64.floor_"
        )
    ]
    roles = re.findall(
        r"^\s*int64_t pycf_numeric_(left|right|result)_[0-9a-f]+ =",
        first.generated_c,
        re.MULTILINE,
    )
    if (
        len(helper_calls) != 2
        or roles != ["left", "right", "result", "left", "right", "result"]
        or first.generated_c.count("pycf_i64_floor_div_v1(") != 3
        or first.generated_c.count("pycf_i64_floor_mod_v1(") != 3
    ):
        errors.append("numeric helper calls are not staged left-right-result exactly once")

    summary = first.conversion_summary or {}
    trace = first.decision_trace or {}
    if (
        summary.get("schema_version") != PHASE14A_CONVERSION_SUMMARY_SCHEMA
        or summary.get("numeric_policy_version") != DEFAULT_NUMERIC_POLICY
        or trace.get("schema_version") != PHASE14A_DECISION_TRACE_SCHEMA
        or trace.get("numeric_policy_version") != DEFAULT_NUMERIC_POLICY
        or list(trace.get("helper_manifest", ())) != list(manifest)
    ):
        errors.append("summary or decision trace omits the Phase 14 numeric evidence")
    return errors


def rejection_smoke_errors() -> list[str]:
    errors: list[str] = []
    converter = PythonToCConverter()
    for label, (expected_code, source) in REJECTION_SOURCES.items():
        result = converter.convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE14A_RULE_SET,
                renderer_version=PHASE14A_RENDERER,
            )
        )
        codes = [diagnostic.code for diagnostic in result.diagnostics]
        trace = result.decision_trace or {}
        artifact_payload = {} if result.stage_artifact is None else result.stage_artifact.payload
        if (
            result.status is not ResultStatus.REJECTED
            or result.generated_c is not None
            or result.output_fingerprint is not None
            or codes != [expected_code]
            or result.stage_artifact is None
            or result.stage_artifact.kind != "python_ir"
            or "helper_requirements" in artifact_payload
            or list(trace.get("helper_manifest", ())) != []
        ):
            errors.append(
                f"{label} did not reject atomically with only {expected_code}"
            )
    return errors


def _floor_reference(dividend: int, divisor: int) -> tuple[int, int]:
    """Model the frozen helpers without running their generated C form."""

    magnitude = abs(dividend) // abs(divisor)
    quotient = -magnitude if (dividend < 0) != (divisor < 0) else magnitude
    remainder = dividend - quotient * divisor
    if remainder != 0 and (remainder < 0) != (divisor < 0):
        quotient -= 1
        remainder += divisor
    return quotient, remainder


def reference_model_errors() -> list[str]:
    dividends = (-(2**63), -(2**63) + 1, -7, -1, 0, 1, 7, 2**63 - 1)
    divisors = (-(2**63) + 1, -7, -2, 1, 2, 7, 2**63 - 1)
    errors: list[str] = []
    for dividend in dividends:
        for divisor in divisors:
            actual = _floor_reference(dividend, divisor)
            expected = (dividend // divisor, dividend % divisor)
            if actual != expected:
                errors.append(
                    f"floor helper model differs from Python for {dividend}, {divisor}"
                )
    return errors


def historical_phase13_errors() -> list[str]:
    result = PythonToCConverter().convert(
        ConversionRequest.from_source(
            PHASE13_COMPATIBILITY_SOURCE,
            rule_set_version=PHASE13_RULE_SET,
            renderer_version=PHASE13_RENDERER,
        )
    )
    if result.status is not ResultStatus.CONVERTED or result.generated_c is None:
        return ["explicit historical Phase 13 witness did not convert"]
    if result.stage_artifact is None:
        return ["explicit historical Phase 13 witness omitted its artifact"]
    payload = result.stage_artifact.payload
    summary = result.conversion_summary or {}
    trace = result.decision_trace or {}
    errors: list[str] = []
    if (
        result.stage_artifact.schema_version != "0.13"
        or payload.get("schema_version") != "generated-c/0.13"
        or payload.get("c_ir_schema") != "c-ir/0.13"
        or summary.get("schema_version") != "pycforge.conversion-summary/0.13"
        or trace.get("schema_version") != "pycforge.decision-trace/0.13"
        or any(
            "numeric_policy_version" in observer
            for observer in (payload, summary, trace)
        )
    ):
        errors.append("explicit Phase 13 witness changed its historical envelopes")
    if sha256_bytes(result.generated_c.encode("utf-8")) != PHASE13_COMPATIBILITY_C_SHA256:
        errors.append("explicit Phase 13 compatibility generated-C hash changed")
    if _fingerprint_value(result.output_fingerprint) != PHASE13_COMPATIBILITY_OUTPUT_SHA256:
        errors.append("explicit Phase 13 compatibility output fingerprint changed")
    if _fingerprint_value(result.request_fingerprint) != PHASE13_COMPATIBILITY_REQUEST_SHA256:
        errors.append("explicit Phase 13 compatibility request fingerprint changed")
    return errors


def converter_smoke_errors(root: Path = ROOT) -> list[str]:
    return list(
        dict.fromkeys(
            accepted_numeric_errors(root)
            + rejection_smoke_errors()
            + reference_model_errors()
            + historical_phase13_errors()
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


def _required_files(manifest: Mapping[str, object]) -> set[str]:
    declared = manifest.get("required_contract_files", ())
    names = set(declared) if isinstance(declared, list) else set()
    return names | {
        "PyCForge_Phase_14A_v0_14_0_Project_Handoff.txt",
        "pycforge/converter/numeric_semantics/analysis.py",
        "pycforge/converter/numeric_semantics/lowering.py",
        "pycforge/converter/numeric_semantics/model.py",
        "specifications/phase14a_bounded_integer_divmod.md",
        "tests/test_phase14_numeric_contracts.py",
        "tests/test_phase14_numeric_end_to_end.py",
        "tests/test_phase14_numeric_hardening.py",
        "tests/test_validate_phase14.py",
        "tools/validate_phase14.py",
        "transition/phase_14/baseline_fingerprint.json",
        "transition/phase_14/breadth_and_change_budgets.md",
        "transition/phase_14/entry_criteria.md",
        "transition/phase_14/gate_evidence.md",
        "transition/phase_14/integer_divmod_decision.md",
        "transition/phase_14/manifest.json",
        "transition/phase_14/opening_evidence.md",
        "transition/phase_14/rollback_conditions.md",
    }


def _predecessor_errors(archive: Path) -> list[str]:
    if not archive.is_file():
        return [f"requested predecessor archive is absent: {archive}"]
    digest = sha256_bytes(archive.read_bytes())
    if digest != PREDECESSOR_ARCHIVE_SHA256:
        return [f"sealed Phase 13 archive hash mismatch: {digest}"]
    try:
        tree_digest = canonical_archive_tree_hash(archive)
        converter_digest = canonical_archive_subtree_hash(archive, "pycforge/converter")
    except (OSError, tarfile.TarError, ValueError) as exc:
        return [f"cannot authenticate predecessor archive: {exc}"]
    errors: list[str] = []
    if tree_digest != PREDECESSOR_TREE_SHA256:
        errors.append(f"sealed Phase 13 tree hash mismatch: {tree_digest}")
    if converter_digest != PREDECESSOR_CONVERTER_SHA256:
        errors.append(f"sealed Phase 13 converter subtree hash mismatch: {converter_digest}")
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
        "pycforge/converter/numeric_semantics/analysis.py",
        "pycforge/converter/numeric_semantics/lowering.py",
        "pycforge/converter/numeric_semantics/model.py",
    }
    if required - names:
        errors.append("wheel omits one or more Phase 14 numeric modules")
    native = sorted(
        name for name in names if name.endswith((".so", ".dll", ".dylib", ".pyd"))
    )
    if native:
        errors.append("wheel unexpectedly contains native binaries")
    return errors


def source_archive_errors(
    archive: Path, fingerprint: Mapping[str, object]
) -> list[str]:
    if not archive.is_file():
        return [f"requested Phase 14 source archive is absent: {archive}"]
    expected = _artifact_expectation(fingerprint, "source_archive")
    errors: list[str] = []
    if expected.get("filename") != archive.name:
        errors.append("source archive name does not match the release fingerprint")
    if _is_sha256(expected.get("sha256")) and expected.get("sha256") != sha256_bytes(archive.read_bytes()):
        errors.append("source archive hash does not match the release fingerprint")
    if isinstance(expected.get("size"), int) and expected.get("size") != archive.stat().st_size:
        errors.append("source archive size does not match the release fingerprint")
    try:
        archive_tree = canonical_archive_tree_hash(archive)
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot inspect Phase 14 source archive: {exc}"]
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
            errors.append("Phase 14 release fingerprint metadata is invalid")
        expected_tree = fingerprint.get("value")
        if not _is_sha256(expected_tree):
            errors.append("Phase 14 release fingerprint value is not finalized")
        else:
            actual_tree = canonical_release_tree_hash(root)
            if expected_tree != actual_tree:
                errors.append(f"Phase 14 release tree hash mismatch: {actual_tree}")
        if fingerprint.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256:
            errors.append("release fingerprint predecessor identity mismatch")
        toolchain_fields = (
            fingerprint.get("c_toolchain_invoked"),
            fingerprint.get("promoted_candidate_toolchain_invoked"),
            fingerprint.get("compiler_linker_loader_or_execution_invoked"),
        )
        if any(value is True for value in toolchain_fields):
            errors.append("release fingerprint claims C toolchain use")
        elif require_promoted and not any(value is False for value in toolchain_fields):
            errors.append("release fingerprint omits the explicit no-toolchain result")
        if fingerprint.get("generated_c_compiled_or_executed") is True:
            errors.append("release fingerprint claims generated-C compilation or execution")
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
    manifest = _load_json(
        root / "transition/phase_14/manifest.json", "Phase 14 manifest", errors
    )
    version = manifest.get("version", manifest.get("candidate_version"))
    if (
        manifest.get("phase") != 14
        or manifest.get("mini_phase") != MINI_PHASE
        or version != RELEASE_VERSION
    ):
        errors.append("Phase 14A manifest identity mismatch")
    if require_promoted and manifest.get("status") != "promoted":
        errors.append("Phase 14A manifest is not promoted")
    required_tests = manifest.get("required_tests")
    if require_promoted and (
        not isinstance(required_tests, int) or required_tests < 335
    ):
        errors.append("Phase 14 required-test count is below its predecessor gate")
    manifest_contracts = manifest.get("schemas")
    if isinstance(manifest_contracts, dict):
        errors.extend(
            exact_mapping_errors(
                manifest_contracts, EXPECTED_CONTRACTS, "Phase 14 manifest contracts"
            )
        )
    elif require_promoted:
        errors.append("Phase 14 manifest contracts are not finalized")
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

    for name in sorted(_required_files(manifest)):
        if not (root / name).is_file():
            errors.append(f"missing Phase 14 release file: {name}")
    for name, expected in (
        ("docs/python_to_c_converter_architecture_revision_3_1.txt", ROADMAP_SHA256),
        ("docs/python_to_c_converter_architecture_revision_3_2_addendum.md", ADDENDUM_SHA256),
    ):
        path = root / name
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"{Path(name).name} hash mismatch")
    if default_helper_registry().fingerprint != HELPER_REGISTRY_SHA256:
        errors.append("Phase 10 helper registry identity changed")

    audit_calls = [
        ("architecture", lambda: audit_architecture(root)),
        ("rules", lambda: audit_rules(root)),
        ("helpers", lambda: audit_helpers(root)),
        ("containers", lambda: audit_containers(root)),
        ("modules", lambda: audit_modules(root)),
        ("records", lambda: audit_records(root)),
        ("numeric", lambda: audit_numeric(root)),
        ("determinism", lambda: audit_determinism(root)),
    ]
    if require_promoted:
        audit_calls.append(("transition", lambda: audit_transition(root, "phase_14")))
    for name, call in audit_calls:
        try:
            report = call()
        except Exception as exc:  # validators must report, not conceal, audit failures
            errors.append(f"{name} audit raised {type(exc).__name__}: {exc}")
        else:
            if report.get("passed") is not True:
                errors.append(f"{name} audit failed: {report}")
    if converter_smoke:
        errors.extend(converter_smoke_errors(root))

    if predecessor_archive is not None:
        errors.extend(_predecessor_errors(Path(predecessor_archive)))

    fingerprint_path = root / RELEASE_FINGERPRINT
    fingerprint = (
        _load_json(fingerprint_path, "Phase 14 release fingerprint", errors)
        if require_promoted or fingerprint_path.is_file()
        else {}
    )
    if fingerprint:
        errors.extend(
            _fingerprint_errors(root, fingerprint, require_promoted=require_promoted)
        )
    if wheel is not None:
        errors.extend(wheel_errors(Path(wheel), fingerprint))
    if source_archive is not None:
        errors.extend(source_archive_errors(Path(source_archive), fingerprint))

    try:
        state = (root / "CURRENT_STATE.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read CURRENT_STATE: {exc}")
    else:
        if require_promoted and (
            "Current release: `0.14.0`" not in state
            or "Phase 14A" not in state
            or "Release status: promoted" not in state
        ):
            errors.append("CURRENT_STATE does not identify a promoted Phase 14A release")
        state_lower = state.lower()
        if require_promoted and (
            "windows 11" not in state_lower
            or not any(
                wording in state_lower
                for wording in (
                    "not claimed",
                    "not evidence claimed",
                    "no windows execution claim",
                )
            )
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
    name = "pycforge-0.14.0-py3-none-any.whl"
    candidates = (root / "dist" / name, root / name, root.parent / name)
    return next((path for path in candidates if path.is_file()), None)


def locate_source_archive(root: Path = ROOT) -> Path | None:
    name = "pycforge_phase_14_v0_14_0.tar.gz"
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
    parser.add_argument(
        "--pre-seal",
        action="store_true",
        help="validate the implementation while allowing absent draft release fields",
    )
    args = parser.parse_args(argv)

    predecessor = (
        Path(args.predecessor_archive).resolve()
        if args.predecessor_archive
        else locate_predecessor_archive(ROOT)
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
            wheel=wheel,
            source_archive=source_archive,
            require_promoted=not args.pre_seal,
            converter_smoke=not args.skip_converter_smoke,
        )
    )
    if args.require_predecessor and predecessor is None:
        errors.append("sealed Phase 13 predecessor archive is required but absent")
    if args.require_wheel and wheel is None:
        errors.append("Phase 14 wheel is required but absent")
    if args.require_source_archive and source_archive is None:
        errors.append("Phase 14 source archive is required but absent")
    if args.run_tests and not errors:
        failure = _run_tests(ROOT)
        if failure:
            errors.append(failure)

    if errors:
        print("PyCForge Phase 14A validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PyCForge Phase 14A validation passed")
    print(f"Release version: {RELEASE_VERSION}")
    print(f"Release tree SHA-256: {canonical_release_tree_hash(ROOT)}")
    print(f"Sealed Phase 13 predecessor verified: {predecessor is not None}")
    print(f"Phase 14 wheel verified: {wheel is not None}")
    print(f"Phase 14 source archive verified: {source_archive is not None}")
    print("This validator invoked no C compiler, linker, loader, or execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
