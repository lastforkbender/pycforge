"""Authenticate and validate the bounded PyCForge Phase 14B release.

The validator inspects structured conversion artifacts for conditional
temporary regions and compares deterministic Python-process evidence.  It has
no compiler, linker, loader, foreign-function, or generated-C execution path.
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
from pycforge.converter.conditional_regions import (  # noqa: E402
    CONDITIONAL_REGION_KEY_DOMAIN,
    CONDITIONAL_REGION_LOWERING_SHAPE,
    CONDITIONAL_REGION_OBLIGATIONS,
    CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
    CONDITIONAL_REGION_TABLE_DEPENDENCIES,
    CONDITIONAL_REGION_TABLE_ID,
)
from pycforge.converter.contracts.configuration import (  # noqa: E402
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_NUMERIC_POLICY,
    DEFAULT_RECORD_POLICY,
    DEFAULT_SEMANTIC_POLICY,
    DEFAULT_TARGET_CONTRACT,
    PHASE14A_RENDERER,
    PHASE14A_RULE_SET,
    PHASE14B_RENDERER,
    PHASE14B_RULE_SET,
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
from pycforge.converter.core.request import ObservationOptions  # noqa: E402
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.converter.support_templates import (  # noqa: E402
    FLOOR_DIV_REFERENCE,
    default_helper_registry,
)
from pycforge.laboratory.audits import (  # noqa: E402
    audit_architecture,
    audit_conditional,
    audit_containers,
    audit_determinism,
    audit_helpers,
    audit_modules,
    audit_numeric,
    audit_records,
    audit_rules,
    audit_transition,
)


RELEASE_VERSION = "0.14.1"
MINI_PHASE = "14B"
PREDECESSOR_VERSION = "0.14.0"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_14_v0_14_0.tar.gz"
PREDECESSOR_ARCHIVE_SIZE = 1_016_512
PREDECESSOR_ARCHIVE_SHA256 = "d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917"
PREDECESSOR_TREE_SHA256 = "6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76"
PREDECESSOR_CONVERTER_SHA256 = "ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d"
ROADMAP_SHA256 = "d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3"
ADDENDUM_SHA256 = "93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
CONDITIONAL_GENERATED_C_SHA256 = "cf9ccd348c69bbf51f8642b06e0b6cac3f82d585f4a334a103c9c3e914f610a5"
PHASE14A_COMPATIBILITY_C_SHA256 = "0ba73812646f4113b99bbe72661d7a7eef129901439422cc2d47bbc6ddaa64c5"
PHASE14A_COMPATIBILITY_OUTPUT_SHA256 = "27f2abb910f41170714de587158e2eacc66ef81d8535b28a754f5f960e9b6f0d"
PHASE14A_COMPATIBILITY_REQUEST_SHA256 = "f3bdc058becb0854692235850037797872afc00a18a132c88b7bb2950a2d4360"
RELEASE_FINGERPRINT = PurePosixPath("transition/phase_14b/release_fingerprint.json")
FINGERPRINT_DOMAIN = "pycforge-phase-14b-release-tree-v1"
TOOLCHAIN_INVOKED = False


EXPECTED_CONTRACTS: Mapping[str, object] = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "record_facts": "fact-table/0.13",
    "numeric_facts": "fact-table/0.14",
    "conditional_facts": "fact-table/0.14.1",
    "conversion_plan": "conversion-plan/0.14.1",
    "c_ir": "c-ir/0.14.1",
    "generated_c": "generated-c/0.14.1",
    "conversion_summary": "pycforge.conversion-summary/0.14.1",
    "decision_trace": "pycforge.decision-trace/0.14.1",
    "result_serialization": "0.5",
    "rule_set": "phase14-conditional-regions-v0.14.1",
    "renderer": "c-renderer-v0.14.1",
    "semantic_policy": "strict-source-v1",
    "module_policy": "phase13-explicit-record-modules-v0.13",
    "record_policy": "phase13-immutable-automatic-records-v0.13",
    "numeric_policy": "phase14-proved-floor-arithmetic-v0.14",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
}

CONDITIONAL_SOURCE = (
    "def flag(value: bool) -> bool:\n"
    "    return value\n\n"
    "def value(item: int) -> int:\n"
    "    return item\n\n"
    "def both(a: bool, b: bool, c: bool) -> bool:\n"
    "    return flag(a) and b and flag(c)\n\n"
    "def either(a: bool, b: bool) -> bool:\n"
    "    return a or flag(b)\n\n"
    "def ordered(a: int, b: int, c: int, d: int) -> bool:\n"
    "    return a < b < (value(c) // 2) < d + 1\n"
)

PHASE14A_COMPATIBILITY_SOURCE = "def run() -> int:\n    return 1\n"

HISTORICAL_PLACEMENT_REJECTIONS: Mapping[str, str] = {
    "PYC2950": (
        "def flag(value: bool) -> bool:\n"
        "    return value\n\n"
        "def run(a: bool, b: bool) -> bool:\n"
        "    return a and flag(b)\n"
    ),
    "PYC2951": (
        "def value(item: int) -> int:\n"
        "    return item\n\n"
        "def run(a: int, b: int, c: int) -> bool:\n"
        "    return a < b < value(c)\n"
    ),
}

DANGEROUS_REJECTIONS: Mapping[str, tuple[str, str]] = {
    "exceptions": (
        "PYC2931",
        "def run() -> int:\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return 0\n",
    ),
    "closure": (
        "PYC2915",
        "def run() -> int:\n"
        "    value = 1\n"
        "    def inner() -> int:\n"
        "        return value\n"
        "    return inner()\n",
    ),
    "generator": ("PYC2931", "def run() -> int:\n    yield 1\n"),
    "async": ("PYC3509", "async def run() -> int:\n    return 1\n"),
    "keyword-call": (
        "PYC2910",
        "def flag(value: bool) -> bool:\n"
        "    return value\n\n"
        "def run(a: bool, b: bool) -> bool:\n"
        "    return a and flag(value=b)\n",
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
    """Hash the release tree while excluding only 14B self-reference and ephemera."""

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
    """Read a safe single-root gzip tar and omit its release self-reference."""

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
    else:
        fingerprints: list[tuple[int, str]] = []
        for name in files:
            match = re.fullmatch(
                r"transition/phase_(\d+)/release_fingerprint\.json", name
            )
            if match:
                fingerprints.append((int(match.group(1)), name))
        if fingerprints:
            files.pop(max(fingerprints)[1])
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
    """Return the sealed Phase 14B contracts, never the active defaults."""

    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "record_facts": RECORD_FACT_SCHEMA,
        "numeric_facts": NUMERIC_FACT_SCHEMA,
        "conditional_facts": PHASE14B_CONDITIONAL_FACT_SCHEMA,
        "conversion_plan": PHASE14B_CONVERSION_PLAN_SCHEMA,
        "c_ir": PHASE14B_C_IR_SCHEMA,
        "generated_c": PHASE14B_GENERATED_C_SCHEMA,
        "conversion_summary": PHASE14B_CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": PHASE14B_DECISION_TRACE_SCHEMA,
        "result_serialization": RESULT_SCHEMA_VERSION,
        "rule_set": PHASE14B_RULE_SET,
        "renderer": PHASE14B_RENDERER,
        "semantic_policy": DEFAULT_SEMANTIC_POLICY,
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


def _fingerprint_value(value: object) -> str | None:
    candidate = getattr(value, "value", None)
    return candidate if isinstance(candidate, str) else None


def _conditional_evidence(result: object) -> dict[str, object]:
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
        f"r=PythonToCConverter().convert(ConversionRequest.from_source({CONDITIONAL_SOURCE!r},"
        f"rule_set_version={PHASE14B_RULE_SET!r},renderer_version={PHASE14B_RENDERER!r}),"
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
    expected = _conditional_evidence(result)
    return [] if actual == expected else ["fresh Python process changed deterministic fingerprints"]


def accepted_conditional_errors(
    root: Path = ROOT, *, fresh_process: bool = True
) -> list[str]:
    """Validate the exact 14B vertical slice without executing generated C."""

    errors: list[str] = []
    request = ConversionRequest.from_source(
        CONDITIONAL_SOURCE,
        rule_set_version=PHASE14B_RULE_SET,
        renderer_version=PHASE14B_RENDERER,
    )
    observation = ObservationOptions("Full", False)
    first = PythonToCConverter().convert(request, observation=observation)
    second = PythonToCConverter().convert(request, observation=observation)
    if first.status is not ResultStatus.CONVERTED or first.generated_c is None:
        return ["accepted Phase 14B conditional witness did not convert"]
    if second.status is not ResultStatus.CONVERTED or second.generated_c is None:
        return ["repeated Phase 14B conditional witness did not convert"]
    if first.stage_artifact is None:
        return ["accepted Phase 14B conditional witness omitted its final artifact"]
    if result_to_json(first) != result_to_json(second):
        errors.append("Phase 14B conditional conversion is not deterministic")
    if fresh_process:
        errors.extend(_fresh_process_errors(Path(root), first))
    if not validate_c_text(first.generated_c).accepted:
        errors.append("Phase 14B generated C failed textual conformance")
    if sha256_bytes(first.generated_c.encode("utf-8")) != CONDITIONAL_GENERATED_C_SHA256:
        errors.append("Phase 14B conditional generated-C hash changed")

    artifact = first.stage_artifact
    payload = artifact.payload
    if (
        artifact.kind != "generated_c"
        or artifact.schema_version != "0.14.1"
        or payload.get("schema_version") != PHASE14B_GENERATED_C_SCHEMA
        or payload.get("c_ir_schema") != PHASE14B_C_IR_SCHEMA
        or payload.get("rule_set_version") != PHASE14B_RULE_SET
        or payload.get("renderer_version") != PHASE14B_RENDERER
        or payload.get("numeric_policy_version") != DEFAULT_NUMERIC_POLICY
        or not isinstance(payload.get("c_ir"), dict)
        or payload["c_ir"].get("schema_version") != PHASE14B_C_IR_SCHEMA
    ):
        errors.append("accepted witness does not publish exact active Phase 14B identities")

    tables = [
        item
        for item in payload.get("fact_tables", ())
        if isinstance(item, dict) and item.get("table_id") == CONDITIONAL_REGION_TABLE_ID
    ]
    table = tables[0] if len(tables) == 1 else {}
    records = table.get("records", ()) if isinstance(table, dict) else ()
    facts = [item.get("value", {}) for item in records if isinstance(item, dict)]
    fact_kinds = [item.get("region_kind") for item in facts]
    if (
        len(tables) != 1
        or table.get("schema_version") != PHASE14B_CONDITIONAL_FACT_SCHEMA
        or table.get("producer_stage") != "analysis.plan"
        or table.get("key_domain") != CONDITIONAL_REGION_KEY_DOMAIN
        or table.get("completeness") != "complete"
        or tuple(table.get("invalidation_dependencies", ()))
        != CONDITIONAL_REGION_TABLE_DEPENDENCIES
        or fact_kinds.count("boolean-short-circuit") != 2
        or fact_kinds.count("chained-comparison") != 1
    ):
        errors.append("accepted witness has an incomplete conditional-region fact table")
    else:
        for record, fact in zip(records, facts):
            operands = list(fact.get("operand_node_ids", ()))
            placements = list(fact.get("placements", ()))
            prefix = 1 if fact.get("region_kind") == "boolean-short-circuit" else 2
            prerequisites = list(
                dict.fromkeys(
                    node_id
                    for placement in placements
                    for node_id in placement.get("prerequisite_node_ids", ())
                )
            )
            if (
                record.get("key") != fact.get("region_node_id")
                or tuple(record.get("provenance", {}).get("evidence", ()))
                != CONDITIONAL_REGION_PROVENANCE_EVIDENCE
                or fact.get("unconditional_prefix_count") != prefix
                or fact.get("guarded_operand_node_ids") != operands[prefix:]
                or fact.get("evaluation_order") != operands
                or len(placements) != len(operands)
                or fact.get("prerequisite_node_ids") != prerequisites
                or fact.get("operands_evaluated_once") is not True
                or fact.get("lowering_shape") != CONDITIONAL_REGION_LOWERING_SHAPE
                or fact.get("result_category") != "boolean-like"
                or fact.get("result_c_type") != "bool"
                or fact.get("allocation_model") != "none"
                or fact.get("cleanup_model") != "none"
                or fact.get("runtime_failure_channel") != "unchanged"
                or fact.get("target_contract") != DEFAULT_TARGET_CONTRACT
            ):
                errors.append("conditional-region fact proof or provenance is incomplete")
                break
            for ordinal, placement in enumerate(placements):
                unconditional = ordinal < prefix
                expected_polarity = (
                    "none"
                    if unconditional
                    else "when-result-false"
                    if fact.get("operator_kinds") == ["Or"]
                    else "when-result-true"
                )
                if (
                    placement.get("operand_node_id") != operands[ordinal]
                    or placement.get("ordinal") != ordinal
                    or placement.get("evaluation_mode")
                    != ("unconditional" if unconditional else "guarded")
                    or placement.get("guard_polarity") != expected_polarity
                    or placement.get("guard_after_operand_ordinal")
                    != (None if unconditional else ordinal - 1)
                    or placement.get("requires_statement_prelude")
                    is not bool(placement.get("prerequisite_node_ids"))
                ):
                    errors.append("conditional operand placement proof is incomplete")
                    break

    plans = [
        item
        for item in payload.get("rule_plans", ())
        if isinstance(item, dict)
        and str(item.get("rule_id", "")).startswith("phase14.conditional.")
    ]
    if (
        len(plans) != 3
        or {item.get("rule_id") for item in plans}
        != {
            "phase14.conditional.boolean_region",
            "phase14.conditional.comparison_region",
        }
        or any(
            item.get("rule_version") != "0.14.1"
            or item.get("support_state") != "SupportedDirect"
            or tuple(item.get("semantic_obligations", ()))
            != CONDITIONAL_REGION_OBLIGATIONS
            or item.get("resolved_obligations") != item.get("semantic_obligations")
            or item.get("unresolved_obligations")
            or item.get("helper_requirements")
            for item in plans
        )
    ):
        errors.append("accepted witness does not publish three closed Phase 14B RulePlans")

    c_ir = payload.get("c_ir", {})
    guards = [
        item
        for item in _walk_dicts(c_ir)
        if item.get("kind") == "CIfStatement"
        and str(item.get("node_id", "")).startswith(
            ("c-bool-region-if-", "c-chain-region-if-")
        )
    ]
    if (
        len(guards) != 5
        or any(item.get("else_block") is not None for item in guards)
        or any(
            not any(
                child.get("kind") == "CAssignmentStatement"
                for child in _walk_dicts(item.get("then_block", {}))
            )
            for item in guards
        )
        or any(
            any(
                child is not item
                and child.get("kind") == "CIfStatement"
                and str(child.get("node_id", "")).startswith(
                    ("c-bool-region-if-", "c-chain-region-if-")
                )
                for child in _walk_dicts(item.get("then_block", {}))
            )
            for item in guards
        )
    ):
        errors.append("conditional lowering is not five flat guarded assignment regions")

    helper = FLOOR_DIV_REFERENCE.canonical
    if (
        payload.get("helper_requirements") != [helper]
        or [item.get("reference") for item in payload.get("helper_manifest", ())]
        != [helper]
        or payload.get("helper_registry_fingerprint") != HELPER_REGISTRY_SHA256
        or any(item.get("helper_requirements") for item in plans)
    ):
        errors.append("conditional regions changed numeric-helper ownership")

    summary = first.conversion_summary or {}
    trace = first.decision_trace or {}
    if (
        summary.get("schema_version") != PHASE14B_CONVERSION_SUMMARY_SCHEMA
        or summary.get("rule_set_version") != PHASE14B_RULE_SET
        or summary.get("renderer_version") != PHASE14B_RENDERER
        or list(summary.get("conditional_regions", ())) != facts
        or trace.get("schema_version") != PHASE14B_DECISION_TRACE_SCHEMA
        or trace.get("trace_level") != "Full"
        or trace.get("completeness") != "complete"
        or trace.get("truncated") is not False
        or trace.get("observer_failed") is not False
        or [
            item
            for item in trace.get("rule_decisions", ())
            if str(item.get("rule_id", "")).startswith("phase14.conditional.")
        ]
        != plans
    ):
        errors.append("summary or decision trace omits exact Phase 14B evidence")
    return errors


def historical_phase14a_errors() -> list[str]:
    """Require the explicit 14A request profile and its exact old envelopes."""

    converter = PythonToCConverter()
    observation = ObservationOptions("Full", False)
    historical = converter.convert(
        ConversionRequest.from_source(
            PHASE14A_COMPATIBILITY_SOURCE,
            rule_set_version=PHASE14A_RULE_SET,
            renderer_version=PHASE14A_RENDERER,
        ),
        observation=observation,
    )
    phase14b = converter.convert(
        ConversionRequest.from_source(
            PHASE14A_COMPATIBILITY_SOURCE,
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        ),
        observation=observation,
    )
    if historical.status is not ResultStatus.CONVERTED or historical.generated_c is None:
        return ["explicit historical Phase 14A witness did not convert"]
    if historical.stage_artifact is None:
        return ["explicit historical Phase 14A witness omitted its artifact"]
    payload = historical.stage_artifact.payload
    errors: list[str] = []
    if (
        historical.stage_artifact.schema_version != "0.14"
        or payload.get("schema_version") != PHASE14A_GENERATED_C_SCHEMA
        or payload.get("c_ir_schema") != PHASE14A_C_IR_SCHEMA
        or payload.get("rule_set_version") != PHASE14A_RULE_SET
        or payload.get("renderer_version") != PHASE14A_RENDERER
        or (historical.conversion_summary or {}).get("schema_version")
        != PHASE14A_CONVERSION_SUMMARY_SCHEMA
        or (historical.decision_trace or {}).get("schema_version")
        != PHASE14A_DECISION_TRACE_SCHEMA
        or CONDITIONAL_REGION_TABLE_ID
        in {item.get("table_id") for item in payload.get("fact_tables", ())}
        or "conditional_regions" in (historical.conversion_summary or {})
        or "conditional_regions" in (historical.decision_trace or {})
    ):
        errors.append("explicit Phase 14A witness changed its historical envelopes")
    if sha256_bytes(historical.generated_c.encode("utf-8")) != PHASE14A_COMPATIBILITY_C_SHA256:
        errors.append("explicit Phase 14A compatibility generated-C hash changed")
    if _fingerprint_value(historical.output_fingerprint) != PHASE14A_COMPATIBILITY_OUTPUT_SHA256:
        errors.append("explicit Phase 14A compatibility output fingerprint changed")
    if _fingerprint_value(historical.request_fingerprint) != PHASE14A_COMPATIBILITY_REQUEST_SHA256:
        errors.append("explicit Phase 14A compatibility request fingerprint changed")
    if (
        phase14b.status is not ResultStatus.CONVERTED
        or phase14b.stage_artifact is None
        or phase14b.stage_artifact.schema_version != "0.14.1"
        or phase14b.generated_c != historical.generated_c
        or phase14b.output_fingerprint != historical.output_fingerprint
    ):
        errors.append("Phase 14B no-region conversion changed Phase 14A generated-C compatibility")

    for expected_code, source in HISTORICAL_PLACEMENT_REJECTIONS.items():
        result = converter.convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE14A_RULE_SET,
                renderer_version=PHASE14A_RENDERER,
            )
        )
        result_payload = {} if result.stage_artifact is None else result.stage_artifact.payload
        if (
            result.status is not ResultStatus.REJECTED
            or [item.code for item in result.diagnostics] != [expected_code]
            or result.generated_c is not None
            or result.output_fingerprint is not None
            or result.stage_artifact is None
            or result.stage_artifact.kind != "conversion_plan"
            or result.stage_artifact.schema_version != "0.14"
            or result_payload.get("schema_version") != PHASE14A_CONVERSION_PLAN_SCHEMA
            or CONDITIONAL_REGION_TABLE_ID
            in {item.get("table_id") for item in result_payload.get("fact_tables", ())}
        ):
            errors.append(
                f"explicit Phase 14A placement witness did not reject atomically with {expected_code}"
            )
    return errors


def dangerous_rejection_errors() -> list[str]:
    """Keep neighboring runtime-heavy families outside the sealed 14B slice."""

    errors: list[str] = []
    converter = PythonToCConverter()
    for label, (expected_code, source) in DANGEROUS_REJECTIONS.items():
        result = converter.convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE14B_RULE_SET,
                renderer_version=PHASE14B_RENDERER,
            )
        )
        if (
            result.status is not ResultStatus.REJECTED
            or [item.code for item in result.diagnostics] != [expected_code]
            or result.generated_c is not None
            or result.output_fingerprint is not None
        ):
            errors.append(f"{label} did not remain atomically rejected with {expected_code}")
    return errors


def converter_smoke_errors(root: Path = ROOT) -> list[str]:
    return list(
        dict.fromkeys(
            accepted_conditional_errors(root)
            + historical_phase14a_errors()
            + dangerous_rejection_errors()
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
        "specifications/phase14b_conditional_temporary_regions.md",
        "transition/phase_14b/baseline_fingerprint.json",
        "transition/phase_14b/breadth_and_change_budgets.md",
        "transition/phase_14b/conditional_temporary_regions_decision.md",
        "transition/phase_14b/entry_criteria.md",
        "transition/phase_14b/opening_evidence.md",
        "transition/phase_14b/rollback_conditions.md",
        "evidence/phase_14b/conversion_debt.json",
        "evidence/phase_14b/entry_report.json",
    }


def _promoted_required_files(manifest: Mapping[str, object]) -> set[str]:
    declared = manifest.get("required_contract_files", ())
    names = set(declared) if isinstance(declared, list) else set()
    return names | _opening_required_files() | {
        "PyCForge_Phase_14B_v0_14_1_Project_Handoff.txt",
        "pycforge/converter/conditional_regions/__init__.py",
        "pycforge/converter/conditional_regions/analysis.py",
        "pycforge/converter/conditional_regions/lowering.py",
        "pycforge/converter/conditional_regions/model.py",
        "pycforge/converter/conditional_regions/validation.py",
        "tests/test_phase14b_conditional_contracts.py",
        "tests/test_phase14b_conditional_analysis.py",
        "tests/test_phase14b_conditional_lowering.py",
        "tests/test_phase14b_conditional_hardening.py",
        "tests/test_phase14b_audits.py",
        "tests/test_validate_phase14b.py",
        "tools/validate_phase14b.py",
        "transition/phase_14b/gate_evidence.md",
        "transition/phase_14b/manifest.json",
        "transition/phase_14b/release_fingerprint.json",
        "evidence/phase_14b/release_report.json",
    }


def predecessor_errors(archive: Path) -> list[str]:
    if not archive.is_file():
        return [f"requested predecessor archive is absent: {archive}"]
    errors: list[str] = []
    if archive.stat().st_size != PREDECESSOR_ARCHIVE_SIZE:
        errors.append(f"sealed Phase 14A archive size mismatch: {archive.stat().st_size}")
    digest = sha256_bytes(archive.read_bytes())
    if digest != PREDECESSOR_ARCHIVE_SHA256:
        errors.append(f"sealed Phase 14A archive hash mismatch: {digest}")
        return errors
    try:
        tree_digest = canonical_archive_tree_hash(archive)
        converter_digest = canonical_archive_subtree_hash(archive, "pycforge/converter")
    except (OSError, tarfile.TarError, ValueError) as exc:
        return errors + [f"cannot authenticate predecessor archive: {exc}"]
    if tree_digest != PREDECESSOR_TREE_SHA256:
        errors.append(f"sealed Phase 14A tree hash mismatch: {tree_digest}")
    if converter_digest != PREDECESSOR_CONVERTER_SHA256:
        errors.append(f"sealed Phase 14A converter subtree hash mismatch: {converter_digest}")
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
        "pycforge/converter/conditional_regions/__init__.py",
        "pycforge/converter/conditional_regions/analysis.py",
        "pycforge/converter/conditional_regions/lowering.py",
        "pycforge/converter/conditional_regions/model.py",
        "pycforge/converter/conditional_regions/validation.py",
    }
    if required - names:
        errors.append("wheel omits one or more Phase 14B conditional-region modules")
    if any(name.endswith((".so", ".dll", ".dylib", ".pyd")) for name in names):
        errors.append("wheel unexpectedly contains native binaries")
    return errors


def source_archive_errors(
    archive: Path, fingerprint: Mapping[str, object]
) -> list[str]:
    if not archive.is_file():
        return [f"requested Phase 14B source archive is absent: {archive}"]
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
        return errors + [f"cannot inspect Phase 14B source archive: {exc}"]
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
            errors.append("Phase 14B release fingerprint metadata is invalid")
        expected_tree = fingerprint.get("value")
        if not _is_sha256(expected_tree):
            errors.append("Phase 14B release fingerprint value is not finalized")
        else:
            actual_tree = canonical_release_tree_hash(root)
            if expected_tree != actual_tree:
                errors.append(f"Phase 14B release tree hash mismatch: {actual_tree}")
        if (
            fingerprint.get("predecessor_version") != PREDECESSOR_VERSION
            or fingerprint.get("predecessor_archive_sha256")
            != PREDECESSOR_ARCHIVE_SHA256
            or fingerprint.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or fingerprint.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
        ):
            errors.append("release fingerprint predecessor identity mismatch")
        tests = fingerprint.get("tests", {})
        if (
            not isinstance(tests, dict)
            or not isinstance(tests.get("discovered"), int)
            or tests.get("discovered", 0) < 365
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
        if fingerprint.get("phase_14c_started") is not False:
            errors.append("release fingerprint does not keep Phase 14C closed")
        if fingerprint.get("phase_15_started") is not False:
            errors.append("release fingerprint does not keep Phase 15 closed")
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
    manifest_path = root / "transition/phase_14b/manifest.json"
    manifest = (
        _load_json(manifest_path, "Phase 14B manifest", errors)
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
            errors.append("Phase 14B manifest identity mismatch")
        if require_promoted and manifest.get("status") != "promoted":
            errors.append("Phase 14B manifest is not promoted")
        if (
            manifest.get("predecessor_version") != PREDECESSOR_VERSION
            or manifest.get("predecessor_archive_sha256")
            != PREDECESSOR_ARCHIVE_SHA256
            or manifest.get("predecessor_tree_sha256") != PREDECESSOR_TREE_SHA256
            or manifest.get("predecessor_converter_subtree_sha256")
            != PREDECESSOR_CONVERTER_SHA256
        ):
            errors.append("Phase 14B manifest predecessor identity mismatch")
        schemas = manifest.get("schemas")
        if isinstance(schemas, dict):
            errors.extend(
                exact_mapping_errors(schemas, EXPECTED_CONTRACTS, "Phase 14B manifest contracts")
            )
        elif require_promoted:
            errors.append("Phase 14B manifest contracts are not finalized")
        if require_promoted:
            required_tests = manifest.get("required_tests")
            if not isinstance(required_tests, int) or required_tests < 365:
                errors.append("Phase 14B required-test count is below its predecessor gate")
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
                errors.append("Phase 14B manifest promotion evidence is incomplete")
            phase14c = manifest.get("phase_14c", {})
            phase15 = manifest.get("phase_15", {})
            if not isinstance(phase14c, dict) or phase14c.get("automatic_open") is not False:
                errors.append("Phase 14B manifest does not keep Phase 14C closed")
            if not isinstance(phase15, dict) or phase15.get("automatic_open") is not False:
                errors.append("Phase 14B manifest does not keep Phase 15 closed")

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
            errors.append(f"missing Phase 14B release file: {name}")
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
        ("conditional", lambda: audit_conditional(root)),
        ("determinism", lambda: audit_determinism(root)),
        ("sealed Phase 14A transition", lambda: audit_transition(root, "phase_14")),
        ("Phase 14B opening transition", lambda: audit_transition(root, "phase_14b")),
    ]
    for name, call in audit_calls:
        try:
            report = call()
        except Exception as exc:  # validators report audit failures rather than conceal them
            errors.append(f"{name} audit raised {type(exc).__name__}: {exc}")
        else:
            if report.get("passed") is not True:
                errors.append(f"{name} audit failed: {report}")
            if name == "conditional" and (
                report.get("c_toolchain_invoked") is not False
                or report.get("generated_c_compiled_or_executed") is not False
            ):
                errors.append("conditional audit does not preserve the no-toolchain boundary")
    if converter_smoke:
        errors.extend(converter_smoke_errors(root))
    if predecessor_archive is not None:
        errors.extend(predecessor_errors(Path(predecessor_archive)))

    fingerprint_path = root / RELEASE_FINGERPRINT
    fingerprint = (
        _load_json(fingerprint_path, "Phase 14B release fingerprint", errors)
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

    if require_promoted:
        try:
            state = (root / "CURRENT_STATE.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read CURRENT_STATE: {exc}")
        else:
            state_lower = state.lower()
            if (
                "Current release: `0.14.1`" not in state
                or "Phase 14B" not in state
                or "Release status: promoted" not in state
            ):
                errors.append("CURRENT_STATE does not identify a promoted Phase 14B release")
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


def locate_wheel(root: Path = ROOT) -> Path | None:
    name = "pycforge-0.14.1-py3-none-any.whl"
    candidates = (root / "dist" / name, root / name, root.parent / name)
    return next((path for path in candidates if path.is_file()), None)


def locate_source_archive(root: Path = ROOT) -> Path | None:
    name = "pycforge_phase_14b_v0_14_1.tar.gz"
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
        help="validate implementation and opening evidence before promotion artifacts exist",
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
        errors.append("sealed Phase 14A predecessor archive is required but absent")
    if args.require_wheel and wheel is None:
        errors.append("Phase 14B wheel is required but absent")
    if args.require_source_archive and source_archive is None:
        errors.append("Phase 14B source archive is required but absent")
    if args.run_tests and not errors:
        failure = _run_tests(ROOT)
        if failure:
            errors.append(failure)

    if errors:
        print("PyCForge Phase 14B validation failed")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PyCForge Phase 14B validation passed")
    print(f"Release version: {RELEASE_VERSION}")
    print(f"Release tree SHA-256: {canonical_release_tree_hash(ROOT)}")
    print(f"Sealed Phase 14A predecessor verified: {predecessor is not None}")
    print(f"Phase 14B wheel verified: {wheel is not None}")
    print(f"Phase 14B source archive verified: {source_archive is not None}")
    print("This validator invoked no C compiler, linker, loader, or execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
