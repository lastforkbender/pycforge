"""Validate the headless PyCForge Phase 15A responsiveness/isolation gate.

This validator never invokes a C compiler, linker, loader, foreign-function
interface, or generated program.  Its promotion mode (also accepted as
``full``) exercises process-isolated conversion and maximum-envelope services
on the current host, but makes no
visible-PyQt or cross-platform distribution claim; those remain Phase 15D.
"""

from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import platform
import sys
import tarfile
from time import monotonic, sleep
import tomllib
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge.converter.core.request import (  # noqa: E402
    ConversionRequest,
    ObservationOptions,
)
from pycforge.converter.core.serialization import result_to_json  # noqa: E402
from pycforge.converter.facade import PythonToCConverter  # noqa: E402
from pycforge.ide.controller import WorkspaceController  # noqa: E402
from pycforge.ide.supervisor import (  # noqa: E402
    ConversionCancelled,
    ProcessConversionSupervisor,
)
from pycforge.ide.worker_protocol import bundle_fingerprint_for_request  # noqa: E402
from tools._phase15a_runtime_validation import (  # noqa: E402
    EXPECTED_RESOURCE_POLICY,
    audit_maximum_input_fixtures,
    scan_runtime_boundaries,
)


VALIDATION_SCHEMA = "pycforge.phase15a-validation-report/1"
EXPECTED_PACKAGE_VERSION = "0.15.0"
EXPECTED_CONVERTER_CONTRACT = "0.14.3"
EXPECTED_WORKSPACE_CONTRACT = "pycforge-workspace/0.3"
EXPECTED_WORKER_PROTOCOL = "pycforge.worker-protocol/0.1"
EXPECTED_CONVERTER_SUBTREE_SHA256 = (
    "a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124"
)
CONVERTER_SUBTREE_DOMAIN = (
    "pycforge-checkpoint-e-release-tree-v1:subtree:pycforge/converter"
)

PREDECESSOR_ARCHIVE_NAME = "pycforge_checkpoint_e_v0_14_4.tar.gz"
PREDECESSOR_ARCHIVE_ROOT = "pycforge_checkpoint_e_v0_14_4"
PREDECESSOR_ARCHIVE_SIZE = 1_398_824
PREDECESSOR_ARCHIVE_SHA256 = (
    "b609c761748a4caf96a42df7ba99dc2e74416fb6c880a2ac547f181f5313c5c0"
)

TOOLCHAIN_INVOKED = False
COMPILER_INVOKED = False
LINKER_INVOKED = False
LOADER_INVOKED = False
FOREIGN_FUNCTION_INVOKED = False
GENERATED_C_COMPILED = False
GENERATED_C_LINKED = False
GENERATED_C_LOADED = False
GENERATED_C_EXECUTED = False

def _audit(name: str, errors: list[str], **evidence: object) -> dict[str, object]:
    return {
        "audit": name,
        "passed": not errors,
        "errors": errors,
        **evidence,
    }


def _skipped(name: str) -> dict[str, object]:
    return {
        "audit": name,
        "passed": True,
        "errors": [],
        "status": "skipped-by-mode",
        "required_in_mode": False,
    }


def _literal_assignment(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else (statement.target,)
            )
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in targets
            ):
                value = statement.value
                if value is None:
                    break
                return ast.literal_eval(value)
    raise ValueError(f"{path}: literal assignment {name!r} is absent")


def _hash_file_map(files: Mapping[str, bytes], *, domain: str) -> str:
    digest = sha256()
    domain_bytes = domain.encode("utf-8")
    digest.update(len(domain_bytes).to_bytes(8, "big"))
    digest.update(domain_bytes)
    for name in sorted(files):
        path_bytes = name.encode("utf-8")
        data = files[name]
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def canonical_converter_subtree_hash(root: Path = ROOT) -> tuple[str, int]:
    """Return the sealed Checkpoint-E-domain hash of ``pycforge/converter``."""

    subtree = root / "pycforge" / "converter"
    files = {
        path.relative_to(subtree).as_posix(): path.read_bytes()
        for path in sorted(
            (
                candidate
                for candidate in subtree.rglob("*")
                if candidate.is_file()
                and "__pycache__" not in candidate.parts
                and candidate.suffix not in {".pyc", ".pyo"}
            ),
            key=lambda candidate: candidate.relative_to(subtree).as_posix(),
        )
    }
    if not files:
        raise ValueError("frozen converter subtree is absent or empty")
    return (
        _hash_file_map(files, domain=CONVERTER_SUBTREE_DOMAIN),
        len(files),
    )


def audit_contract_identities(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    identities: dict[str, object] = {}
    try:
        project = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )
        identities["project_package"] = project["project"]["version"]
        identities["module_package"] = _literal_assignment(
            root / "pycforge" / "_version.py", "__version__"
        )
        identities["converter"] = _literal_assignment(
            root / "pycforge" / "converter" / "contracts" / "versions.py",
            "CONVERTER_CONTRACT_VERSION",
        )
        identities["workspace"] = _literal_assignment(
            root / "pycforge" / "ide" / "__init__.py",
            "WORKSPACE_CONTRACT_VERSION",
        )
        identities["worker_protocol"] = _literal_assignment(
            root / "pycforge" / "ide" / "_worker_protocol_types.py",
            "PROTOCOL_SCHEMA",
        )
    except (
        OSError,
        UnicodeError,
        SyntaxError,
        ValueError,
        KeyError,
        TypeError,
        tomllib.TOMLDecodeError,
    ) as exc:
        errors.append(f"cannot establish Phase 15A contract identities: {exc}")
    expected = {
        "project_package": EXPECTED_PACKAGE_VERSION,
        "module_package": EXPECTED_PACKAGE_VERSION,
        "converter": EXPECTED_CONVERTER_CONTRACT,
        "workspace": EXPECTED_WORKSPACE_CONTRACT,
        "worker_protocol": EXPECTED_WORKER_PROTOCOL,
    }
    for key, value in expected.items():
        if identities.get(key) != value:
            errors.append(
                f"{key} identity is {identities.get(key)!r}, expected {value!r}"
            )
    return _audit(
        "phase15a-contract-identities",
        errors,
        identities=identities,
        expected=expected,
    )


def audit_frozen_converter_subtree(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    actual: str | None = None
    file_count = 0
    try:
        actual, file_count = canonical_converter_subtree_hash(root)
    except (OSError, ValueError) as exc:
        errors.append(f"cannot hash frozen converter subtree: {exc}")
    if actual != EXPECTED_CONVERTER_SUBTREE_SHA256:
        errors.append(
            "frozen converter subtree changed: "
            f"{actual or '<unavailable>'}"
        )
    return _audit(
        "frozen-converter-subtree",
        errors,
        expected_sha256=EXPECTED_CONVERTER_SUBTREE_SHA256,
        actual_sha256=actual,
        file_count=file_count,
        converter_semantics_modified=False if not errors else None,
    )


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_ARCHIVE_NAME,
        root.parent / PREDECESSOR_ARCHIVE_NAME,
        root.parent
        / "checkpoint_e_release"
        / "final_0_14_4"
        / PREDECESSOR_ARCHIVE_NAME,
        root.parent / "final_0_14_4" / PREDECESSOR_ARCHIVE_NAME,
        root.parent / "final" / PREDECESSOR_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def _archive_file_map(path: Path) -> tuple[dict[str, bytes], str]:
    files: dict[str, bytes] = {}
    roots: set[str] = set()
    names: set[str] = set()
    with tarfile.open(path, mode="r:gz") as package:
        for member in package.getmembers():
            pure = PurePosixPath(member.name)
            if (
                pure.is_absolute()
                or not pure.parts
                or any(part in {"", ".", ".."} for part in pure.parts)
                or member.name in names
            ):
                raise ValueError(f"unsafe or duplicate archive member: {member.name}")
            names.add(member.name)
            roots.add(pure.parts[0])
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"non-regular archive member: {member.name}")
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError(f"unreadable archive member: {member.name}")
            relative = PurePosixPath(*pure.parts[1:]).as_posix()
            if not relative or relative in files:
                raise ValueError(f"invalid normalized archive member: {member.name}")
            files[relative] = stream.read()
    if roots != {PREDECESSOR_ARCHIVE_ROOT} or not files:
        raise ValueError("predecessor archive has the wrong root or is empty")
    return files, next(iter(roots))


def audit_predecessor_archive(
    path: Path | None,
    *,
    required: bool,
) -> dict[str, object]:
    if path is None:
        errors = ["sealed Checkpoint E predecessor archive is absent"] if required else []
        return _audit(
            "checkpoint-e-predecessor-authentication",
            errors,
            status="missing-required" if required else "not-present-optional",
            required=required,
            archive_authenticated=False,
            archive_extracted=False,
        )

    errors: list[str] = []
    actual_size: int | None = None
    actual_sha256: str | None = None
    converter_sha256: str | None = None
    file_count = 0
    try:
        actual_size = path.stat().st_size
        actual_sha256 = sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        errors.append(f"cannot read predecessor archive: {exc}")
    else:
        if path.name != PREDECESSOR_ARCHIVE_NAME:
            errors.append(f"predecessor archive name mismatch: {path.name}")
        if actual_size != PREDECESSOR_ARCHIVE_SIZE:
            errors.append(f"predecessor archive size mismatch: {actual_size}")
        if actual_sha256 != PREDECESSOR_ARCHIVE_SHA256:
            errors.append(f"predecessor archive SHA-256 mismatch: {actual_sha256}")
        if not errors:
            try:
                files, _root_name = _archive_file_map(path)
                selected = {
                    name.removeprefix("pycforge/converter/"): data
                    for name, data in files.items()
                    if name.startswith("pycforge/converter/")
                }
                file_count = len(files)
                converter_sha256 = _hash_file_map(
                    selected,
                    domain=CONVERTER_SUBTREE_DOMAIN,
                )
            except (OSError, tarfile.TarError, ValueError) as exc:
                errors.append(f"cannot inspect predecessor archive safely: {exc}")
            else:
                if converter_sha256 != EXPECTED_CONVERTER_SUBTREE_SHA256:
                    errors.append(
                        "predecessor converter subtree mismatch: "
                        f"{converter_sha256}"
                    )
    return _audit(
        "checkpoint-e-predecessor-authentication",
        errors,
        status="authenticated" if not errors else "failed",
        required=required,
        archive_name=path.name,
        expected_size=PREDECESSOR_ARCHIVE_SIZE,
        actual_size=actual_size,
        expected_sha256=PREDECESSOR_ARCHIVE_SHA256,
        actual_sha256=actual_sha256,
        converter_subtree_sha256=converter_sha256,
        regular_file_count=file_count,
        archive_authenticated=not errors,
        archive_extracted=False,
    )


_EQUIVALENCE_CASES = (
    (
        "single-module",
        ConversionRequest.from_source(
            "def add(a: int, b: int) -> int:\n    return a + b\n"
        ),
    ),
    (
        "keyword-only",
        ConversionRequest.from_source(
            "def scale(value: int, *, factor: int) -> int:\n"
            "    return value * factor\n\n"
            "def main() -> int:\n"
            "    return scale(3, factor=4)\n"
        ),
    ),
)


def audit_direct_isolated_equivalence() -> dict[str, object]:
    errors: list[str] = []
    cases: list[dict[str, object]] = []
    for generation, (name, request) in enumerate(_EQUIVALENCE_CASES, start=1):
        supervisor = ProcessConversionSupervisor()
        try:
            direct = PythonToCConverter().convert(
                request,
                observation=ObservationOptions("Full", True),
            )
            isolated = supervisor.submit(
                generation=generation,
                bundle_fingerprint=bundle_fingerprint_for_request(request),
                request=request,
            ).result(timeout=15)
            direct_json = result_to_json(direct)
            isolated_json = result_to_json(isolated)
            equivalent = direct_json == isolated_json
            snapshot = supervisor.snapshot
            if not equivalent:
                errors.append(f"{name}: isolated result differs from direct facade")
            if not supervisor.wait_idle(timeout=3):
                errors.append(f"{name}: isolated supervisor did not become idle")
            if snapshot.maximum_simultaneous_workers > 1:
                errors.append(f"{name}: more than one worker was active")
            cases.append(
                {
                    "case": name,
                    "equivalent": equivalent,
                    "result_sha256": sha256(direct_json.encode("utf-8")).hexdigest(),
                    "output_fingerprint": (
                        None
                        if direct.output_fingerprint is None
                        else direct.output_fingerprint.value
                    ),
                }
            )
        except Exception as exc:
            errors.append(f"{name}: isolated equivalence failed: {exc}")
        finally:
            supervisor.close(wait=True, timeout=3)
    return _audit(
        "direct-vs-isolated-equivalence",
        errors,
        cases=cases,
        same_public_facade=True,
        generated_c_executed=False,
    )


def _wait_until(predicate, timeout: float) -> bool:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return True
        sleep(0.002)
    return bool(predicate())


def audit_hundred_cycle_supervision() -> dict[str, object]:
    errors: list[str] = []
    supervisor = ProcessConversionSupervisor()
    controller = WorkspaceController(supervisor=supervisor)
    snapshot = supervisor.snapshot
    futures = []
    canceled = 0
    active_cancel_cycles = 0
    try:
        for cycle in range(100):
            controller.set_source(
                "def value() -> int:\n"
                f"    return {cycle % 4}\n"
                f"# revision {cycle}\n"
            )
            if not _wait_until(
                lambda: controller.snapshot.revision_authenticated,
                3,
            ):
                errors.append(f"cycle {cycle}: revision authentication timed out")
                break
            future = controller.convert_async()
            # Exercise actual child-process retirement regularly while keeping
            # the remaining cycles as an adversarial rapid pending-cancel burst.
            if cycle % 10 == 0:
                expected_generation = controller.snapshot.request_sequence
                if _wait_until(
                    lambda: (
                        supervisor.snapshot.active_generation
                        == expected_generation
                    ),
                    3,
                ):
                    active_cancel_cycles += 1
                else:
                    errors.append(
                        f"cycle {cycle}: isolated worker did not become active"
                    )
            controller.cancel()
            futures.append(future)
        for cycle, future in enumerate(futures):
            try:
                future.result(timeout=5)
            except ConversionCancelled:
                canceled += 1
            except Exception as exc:
                errors.append(f"cycle {cycle}: unexpected terminal failure: {exc}")
            else:
                errors.append(f"cycle {cycle}: canceled request published a result")
        if len(futures) != 100:
            errors.append(f"only {len(futures)} of 100 cycles were submitted")
        if not supervisor.wait_idle(timeout=6):
            errors.append("supervisor did not become idle after 100 cycles")
        snapshot = supervisor.snapshot
        if snapshot.active_generation is not None:
            errors.append("active generation remained after stress cycles")
        if snapshot.pending_generation is not None:
            errors.append("pending generation remained after stress cycles")
        if snapshot.active_pid is not None:
            errors.append("worker process remained after stress cycles")
        if snapshot.started_workers != snapshot.reaped_workers:
            errors.append("started and reaped worker counts differ")
        if active_cancel_cycles != 10 or snapshot.started_workers < 10:
            errors.append("ten scheduled active-worker cancellation cycles were not exercised")
        if snapshot.maximum_simultaneous_workers > 1:
            errors.append("more than one conversion worker was simultaneous")
    finally:
        controller.close(wait=True)
        supervisor.close(wait=True, timeout=4)
    return _audit(
        "hundred-edit-convert-cancel-cycles",
        errors,
        requested_cycles=100,
        submitted_cycles=len(futures),
        canceled_cycles=canceled,
        active_worker_cancel_cycles=active_cancel_cycles,
        started_workers=snapshot.started_workers,
        reaped_workers=snapshot.reaped_workers,
        maximum_simultaneous_workers=snapshot.maximum_simultaneous_workers,
        active_pid_after_gate=snapshot.active_pid,
        pending_generation_after_gate=snapshot.pending_generation,
    )


def audit_platform_scope() -> dict[str, object]:
    try:
        physical_memory_bytes = (
            os.sysconf("SC_PAGE_SIZE")
            * os.sysconf("SC_PHYS_PAGES")
        )
    except (AttributeError, OSError, TypeError, ValueError):
        physical_memory_bytes = None
    return _audit(
        "honest-platform-scope",
        [],
        validation_scope="headless-phase15a-current-host",
        current_host_platform=sys.platform,
        platform_description=platform.platform(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        physical_memory_bytes=physical_memory_bytes,
        process_start_method="spawn",
        real_pyqt_widgets_exercised=False,
        visible_windows_11_exercised=False,
        visible_linux_desktop_exercised=False,
        display_scaling_matrix_exercised=False,
        distribution_install_exercised=False,
        phase_15d_platform_gate_required=True,
    )


def audit_safety_scope() -> dict[str, object]:
    safety = {
        "toolchain_invoked": TOOLCHAIN_INVOKED,
        "compiler_invoked": COMPILER_INVOKED,
        "linker_invoked": LINKER_INVOKED,
        "loader_invoked": LOADER_INVOKED,
        "foreign_function_invoked": FOREIGN_FUNCTION_INVOKED,
        "generated_c_compiled": GENERATED_C_COMPILED,
        "generated_c_linked": GENERATED_C_LINKED,
        "generated_c_loaded": GENERATED_C_LOADED,
        "generated_c_executed": GENERATED_C_EXECUTED,
    }
    errors = [key for key, value in safety.items() if value]
    return _audit(
        "source-transpiler-safety",
        [f"forbidden safety flag is true: {key}" for key in errors],
        **safety,
    )


def _safe_audit(name: str, function, *args, **kwargs) -> dict[str, object]:
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        return _audit(
            name,
            [
                "validator audit failed closed: "
                f"{type(exc).__name__}: {exc}"
            ],
            status="internal-error",
        )
    if not isinstance(result, dict) or "passed" not in result:
        return _audit(
            name,
            ["validator audit returned a malformed result"],
            status="internal-error",
        )
    return result


def run_validation(
    *,
    root: Path = ROOT,
    mode: str = "promotion",
    predecessor: Path | None = None,
    search_predecessor: bool = True,
) -> dict[str, object]:
    if mode not in {"quick", "full", "promotion"}:
        raise ValueError(
            "validation mode must be 'quick', 'full', or 'promotion'"
        )
    normalized_mode = "promotion" if mode in {"full", "promotion"} else "quick"
    selected_predecessor = predecessor
    if selected_predecessor is None and search_predecessor:
        selected_predecessor = locate_predecessor_archive(root)
    predecessor_required = predecessor is not None
    audits = [
        _safe_audit(
            "phase15a-contract-identities",
            audit_contract_identities,
            root,
        ),
        _safe_audit(
            "frozen-converter-subtree",
            audit_frozen_converter_subtree,
            root,
        ),
        _safe_audit(
            "checkpoint-e-predecessor-authentication",
            audit_predecessor_archive,
            selected_predecessor,
            required=predecessor_required,
        ),
        _safe_audit(
            "runtime-isolation-and-toolchain-boundary",
            scan_runtime_boundaries,
            root,
        ),
    ]
    if normalized_mode == "promotion":
        audits.extend(
            (
                _safe_audit(
                    "direct-vs-isolated-equivalence",
                    audit_direct_isolated_equivalence,
                ),
                _safe_audit(
                    "bounded-maximum-input-fixtures",
                    audit_maximum_input_fixtures,
                ),
                _safe_audit(
                    "hundred-edit-convert-cancel-cycles",
                    audit_hundred_cycle_supervision,
                ),
            )
        )
    else:
        audits.extend(
            (
                _skipped("direct-vs-isolated-equivalence"),
                _skipped("bounded-maximum-input-fixtures"),
                _skipped("hundred-edit-convert-cancel-cycles"),
            )
        )
    audits.extend(
        (
            _safe_audit("honest-platform-scope", audit_platform_scope),
            _safe_audit("source-transpiler-safety", audit_safety_scope),
        )
    )
    passed = all(bool(audit["passed"]) for audit in audits)
    phase_15a_eligible = passed and normalized_mode == "promotion"
    return {
        "schema": VALIDATION_SCHEMA,
        "mode": normalized_mode,
        "scope": "phase-15a-headless-only",
        "passed": passed,
        "promotion_eligible": phase_15a_eligible,
        "promotion_scope": "phase-15a-headless-milestone-only",
        "phase_15a_gate_eligible": phase_15a_eligible,
        "visible_ui_promotion_eligible": False,
        "distribution_promotion_eligible": False,
        "phase_15b_opened": False,
        "phase_15c_opened": False,
        "phase_15d_opened": False,
        "audits": audits,
    }


def _json_bytes(value: object) -> bytes:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the headless PyCForge Phase 15A gate."
    )
    parser.add_argument(
        "--mode",
        choices=("quick", "full", "promotion"),
        default="promotion",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--predecessor", type=Path)
    parser.add_argument(
        "--no-predecessor-search",
        action="store_true",
        help="do not search the fixed optional predecessor locations",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_validation(
        root=args.root.resolve(),
        mode=args.mode,
        predecessor=(
            None if args.predecessor is None else args.predecessor.resolve()
        ),
        search_predecessor=not args.no_predecessor_search,
    )
    payload = _json_bytes(report)
    if args.output is not None:
        args.output.write_bytes(payload)
    sys.stdout.buffer.write(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
