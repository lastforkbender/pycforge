"""Private runtime-boundary and maximum-envelope audits for Phase 15A."""

from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path
import re
from threading import Event, get_ident
from time import monotonic

from pycforge.converter.core.request import ConversionRequest, ObservationOptions
from pycforge.converter.core.resource_policy import ResourcePolicy
from pycforge.converter.frontend.parser import Python311ParserAdapter
from pycforge.converter.frontend.source_document import SourceDocument
from pycforge.ide.model import WorkspaceDocument
from pycforge.ide.revisions import (
    RevisionInput,
    WorkspaceRevisionService,
    build_workspace_revision,
)
from pycforge.ide.search_service import AsyncLiteralSearchService
from pycforge.ide.worker_protocol import (
    MAX_REQUEST_BYTES,
    WorkerProtocolError,
    WorkerRequest,
    bundle_fingerprint_for_request,
    encode_request,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RESOURCE_POLICY = {
    "max_source_bytes": 1_000_000,
    "max_source_lines": 100_000,
    "max_diagnostics": 1_000,
    "max_trace_events": 10_000,
    "max_telemetry_events": 10_000,
    "max_tokens": 250_000,
    "max_ast_nodes": 100_000,
    "max_nesting_depth": 128,
    "max_source_documents": 64,
    "max_import_edges": 4_096,
}

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "cffi",
        "cloudpickle",
        "ctypes",
        "dill",
        "marshal",
        "pickle",
        "shelve",
        "subprocess",
    }
)
_BANNED_DYNAMIC_CALLS = frozenset({"compile", "eval", "exec"})
_BANNED_OBJECT_IPC_CALLS = frozenset({"recv", "send"})
_BANNED_MULTIPROCESSING_OBJECTS = frozenset(
    {"Manager", "Pool", "Queue", "SimpleQueue"}
)
_TOOLCHAIN_EXECUTABLES = frozenset(
    {"cc", "cl.exe", "clang", "clang-cl", "gcc", "ld", "link.exe"}
)


def _audit(name: str, errors: list[str], **evidence: object) -> dict[str, object]:
    return {
        "audit": name,
        "passed": not errors,
        "errors": errors,
        **evidence,
    }


def _call_name(call: ast.Call) -> tuple[str | None, str]:
    if isinstance(call.func, ast.Name):
        return None, call.func.id
    if isinstance(call.func, ast.Attribute):
        owner = call.func.value.id if isinstance(call.func.value, ast.Name) else None
        return owner, call.func.attr
    return None, ""


def scan_runtime_boundaries(root: Path = ROOT) -> dict[str, object]:
    """Reject GUI conversion authority, object IPC, and execution surfaces."""

    errors: list[str] = []
    files = sorted(
        (
            *(root / "pycforge" / "converter").rglob("*.py"),
            *(root / "pycforge" / "ide").rglob("*.py"),
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    facade_authorities: list[str] = []
    byte_pipe_calls = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{relative}: cannot scan runtime source: {exc}")
            continue
        imported_names: set[str] = set()
        multiprocessing_aliases: set[str] = set()
        object_ipc_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name.split(".", 1)[0])
                    if alias.name == "multiprocessing":
                        multiprocessing_aliases.add(
                            alias.asname or "multiprocessing"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module.split(".", 1)[0])
                if node.module == "pycforge.converter.facade":
                    facade_authorities.append(relative)
                    if relative != "pycforge/ide/process_worker.py":
                        errors.append(
                            f"{relative}: GUI-side converter facade import"
                        )
                if (
                    relative != "pycforge/ide/process_worker.py"
                    and any(alias.name == "PythonToCConverter" for alias in node.names)
                ):
                    errors.append(
                        f"{relative}: in-process converter authority imported"
                    )
                if node.module == "multiprocessing":
                    for alias in node.names:
                        if alias.name in _BANNED_MULTIPROCESSING_OBJECTS:
                            object_ipc_names.add(alias.asname or alias.name)
                            errors.append(
                                f"{relative}: object IPC {alias.name} is forbidden"
                            )
        for imported in sorted(imported_names & _BANNED_IMPORT_ROOTS):
            errors.append(f"{relative}: forbidden runtime import {imported}")

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            owner, name = _call_name(node)
            if owner is None and name in _BANNED_DYNAMIC_CALLS:
                errors.append(f"{relative}: forbidden dynamic call {name}")
            if name in _BANNED_OBJECT_IPC_CALLS:
                errors.append(f"{relative}: object Connection.{name} is forbidden")
            if (
                (owner is None and name in object_ipc_names)
                or (
                    owner in multiprocessing_aliases
                    and name in _BANNED_MULTIPROCESSING_OBJECTS
                )
            ):
                errors.append(f"{relative}: object IPC {name} is forbidden")
            if owner == "os" and (
                name in {"popen", "system"} or name.startswith("spawn")
            ):
                errors.append(f"{relative}: forbidden host process call os.{name}")
            if owner == "shutil" and name == "which":
                errors.append(f"{relative}: forbidden host tool discovery")
            if (
                relative.startswith("pycforge/ide/")
                and relative != "pycforge/ide/process_worker.py"
                and name == "convert"
            ):
                errors.append(f"{relative}: GUI-side in-process convert call")
            if name in {"send_bytes", "recv_bytes"}:
                byte_pipe_calls += 1

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                tokens = set(
                    re.findall(r"[A-Za-z0-9_.+-]+", node.value.casefold())
                )
                found = sorted(tokens & _TOOLCHAIN_EXECUTABLES)
                if found:
                    errors.append(
                        f"{relative}: compiler/toolchain token {found[0]!r}"
                    )

    expected_authority = ["pycforge/ide/process_worker.py"]
    if sorted(set(facade_authorities)) != expected_authority:
        errors.append(
            "converter facade authority is not confined to process_worker.py: "
            + ",".join(sorted(set(facade_authorities)))
        )
    protocol_path = root / "pycforge" / "ide" / "_worker_protocol_types.py"
    try:
        protocol_tree = ast.parse(protocol_path.read_text(encoding="utf-8"))
        byte_connection = next(
            node
            for node in protocol_tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ByteConnection"
        )
        methods = {
            node.name
            for node in byte_connection.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
    except (OSError, UnicodeError, SyntaxError, StopIteration) as exc:
        errors.append(f"cannot inspect byte-only protocol interface: {exc}")
        methods = set()
    if methods != {"close", "recv_bytes", "send_bytes"}:
        errors.append(f"ByteConnection exposes unsafe methods: {sorted(methods)}")
    if byte_pipe_calls < 3:
        errors.append("byte-only worker transport calls are unexpectedly absent")

    return _audit(
        "runtime-isolation-and-toolchain-boundary",
        sorted(set(errors)),
        scanned_files=len(files),
        converter_facade_authorities=sorted(set(facade_authorities)),
        byte_connection_methods=sorted(methods),
        byte_transport_call_sites=byte_pipe_calls,
        pickle_transport_allowed=False,
        object_connection_transport_allowed=False,
        subprocess_allowed=False,
        toolchain_allowed=False,
        gui_in_process_conversion_allowed=False,
    )


def _maximum_document(text: str) -> WorkspaceDocument:
    return WorkspaceDocument(
        document_id="doc-main",
        module_id="main",
        logical_name="maximum.py",
        text=text,
        is_primary=True,
    )


def audit_maximum_input_fixtures() -> dict[str, object]:
    """Measure deterministic near-ceiling fixtures without a GUI/toolchain."""

    errors: list[str] = []
    policy = ResourcePolicy().to_dict()
    if policy != EXPECTED_RESOURCE_POLICY:
        errors.append(f"resource policy changed: {policy}")

    simultaneous = "#12345678\n" * 99_999 + "#12345678"
    byte_fixture = "x" * EXPECTED_RESOURCE_POLICY["max_source_bytes"]
    token_fixture = "x=0;" * 62_498 + "x=0\n"
    ast_fixture = "x=(" + "0," * 99_990 + ")\n"
    caller_thread = get_ident()
    builder_threads: list[int] = []

    def builder(value: RevisionInput):
        builder_threads.append(get_ident())
        return build_workspace_revision(value)

    service = WorkspaceRevisionService(builder=builder)
    revision_submitted_at = monotonic()
    try:
        revision_future = service.submit(
            1,
            (_maximum_document(simultaneous),),
            "doc-main",
        )
        revision_submit_seconds = monotonic() - revision_submitted_at
        revision = revision_future.result(timeout=20)
        revision_total_seconds = monotonic() - revision_submitted_at
    except Exception as exc:
        errors.append(f"maximum revision/index fixture failed: {exc}")
        revision = None
        revision_submit_seconds = None
        revision_total_seconds = None
    finally:
        service.close(wait=True, timeout=3)
    if not builder_threads or builder_threads[0] == caller_thread:
        errors.append("maximum revision/index work ran on the caller thread")
    if (
        revision_submit_seconds is not None
        and revision_submit_seconds >= 0.100
    ):
        errors.append(
            "maximum revision submission exceeded the 100 ms caller budget"
        )

    search_text = "abcdefghijklmnopqr\n" * 50_000
    search_completed = Event()
    search_results = []
    search = AsyncLiteralSearchService()
    search_submitted_at = monotonic()
    search_submit_seconds: float | None = None
    search_total_seconds: float | None = None
    try:
        search.submit(
            search_text,
            "a",
            callback=lambda result: (
                search_results.append(result),
                search_completed.set(),
            ),
        )
        search_submit_seconds = monotonic() - search_submitted_at
        if not search_completed.wait(10):
            errors.append("maximum dense literal search timed out")
            search_total_seconds = None
        else:
            search_total_seconds = monotonic() - search_submitted_at
    except Exception as exc:
        errors.append(f"maximum dense literal search failed: {exc}")
    finally:
        search.close()
    if (
        search_submit_seconds is not None
        and search_submit_seconds >= 0.100
    ):
        errors.append("dense search submission exceeded the 100 ms caller budget")
    search_result = search_results[0] if search_results else None
    if (
        search_result is not None
        and (
            search_result.total_count != 50_000
            or len(search_result.ranges) != 5_000
            or not search_result.truncated
        )
    ):
        errors.append("dense search count or bounded projection is incorrect")

    try:
        simultaneous_document = Python311ParserAdapter().tokenize(
            SourceDocument.create("simultaneous-limit.py", simultaneous)
        )
        simultaneous_tokens = len(simultaneous_document.tokens)
        del simultaneous_document
        simultaneous_ast_nodes = sum(
            1 for _node in ast.walk(ast.parse(simultaneous))
        )
        token_document = Python311ParserAdapter().tokenize(
            SourceDocument.create("token-limit.py", token_fixture)
        )
        token_count = len(token_document.tokens)
        del token_document
    except Exception as exc:
        errors.append(f"token measurement fixture failed: {exc}")
        simultaneous_tokens = None
        simultaneous_ast_nodes = None
        token_count = None
    try:
        ast_count = sum(1 for _node in ast.walk(ast.parse(ast_fixture)))
    except (SyntaxError, MemoryError) as exc:
        errors.append(f"near-AST-limit fixture failed: {exc}")
        ast_count = None

    simultaneous_bytes = len(simultaneous.encode("utf-8"))
    simultaneous_lines = simultaneous.count("\n") + 1
    if revision is not None:
        if revision.total_utf8_size != simultaneous_bytes:
            errors.append("maximum revision byte index is incorrect")
        if revision.active_index.line_count != simultaneous_lines:
            errors.append("maximum revision line index is incorrect")
    if not (
        999_000
        <= simultaneous_bytes
        <= EXPECTED_RESOURCE_POLICY["max_source_bytes"]
        and simultaneous_lines == EXPECTED_RESOURCE_POLICY["max_source_lines"]
    ):
        errors.append("simultaneous maximum fixture is below its declared envelope")
    if simultaneous_tokens is None or simultaneous_tokens > 250_000:
        errors.append("simultaneous maximum fixture exceeds the token ceiling")
    if simultaneous_ast_nodes is None or simultaneous_ast_nodes > 100_000:
        errors.append("simultaneous maximum fixture exceeds the AST ceiling")
    if token_count is None or not 249_900 <= token_count <= 250_000:
        errors.append(f"near-token-limit count is outside the envelope: {token_count}")
    if ast_count is None or not 99_900 <= ast_count <= 100_000:
        errors.append(f"near-AST-limit count is outside the envelope: {ast_count}")

    request = ConversionRequest.from_source(byte_fixture)
    try:
        worker_request = WorkerRequest.create(
            1,
            bundle_fingerprint_for_request(request),
            request,
            ObservationOptions("None", False),
        )
        frame_size = len(encode_request(worker_request))
    except Exception as exc:
        errors.append(f"exact byte-ceiling worker request failed: {exc}")
        frame_size = None
    if frame_size is not None and frame_size > MAX_REQUEST_BYTES:
        errors.append("exact byte-ceiling request exceeds transport frame bound")
    oversized_rejected = False
    try:
        oversized = ConversionRequest.from_source(
            "x" * (EXPECTED_RESOURCE_POLICY["max_source_bytes"] + 1)
        )
        WorkerRequest.create(
            2,
            bundle_fingerprint_for_request(oversized),
            oversized,
            ObservationOptions("None", False),
        )
    except WorkerProtocolError:
        oversized_rejected = True
    if not oversized_rejected:
        errors.append("over-byte-ceiling worker request was not rejected")

    fixtures = {
        "simultaneous_valid_syntax": {
            "utf8_bytes": simultaneous_bytes,
            "source_lines": simultaneous_lines,
            "tokens": simultaneous_tokens,
            "ast_nodes": simultaneous_ast_nodes,
            "sha256": sha256(simultaneous.encode("utf-8")).hexdigest(),
        },
        "exact_byte_ceiling": {
            "utf8_bytes": len(byte_fixture),
            "request_frame_bytes": frame_size,
            "oversized_rejected": oversized_rejected,
        },
        "near_token_ceiling": {
            "tokens": token_count,
            "utf8_bytes": len(token_fixture.encode("utf-8")),
            "sha256": sha256(token_fixture.encode("utf-8")).hexdigest(),
        },
        "near_ast_ceiling": {
            "ast_nodes": ast_count,
            "utf8_bytes": len(ast_fixture.encode("utf-8")),
            "sha256": sha256(ast_fixture.encode("utf-8")).hexdigest(),
        },
    }
    return _audit(
        "bounded-maximum-input-fixtures",
        errors,
        policy=policy,
        fixtures=fixtures,
        measurements_seconds={
            "revision_submit": revision_submit_seconds,
            "revision_index_total": revision_total_seconds,
            "dense_search_submit": search_submit_seconds,
            "dense_search_total": search_total_seconds,
            "dense_search_worker": (
                None
                if search_result is None
                else search_result.elapsed_seconds
            ),
        },
        dense_search={
            "utf8_bytes": len(search_text.encode("utf-8")),
            "total_matches": (
                None if search_result is None else search_result.total_count
            ),
            "stored_ranges": (
                None if search_result is None else len(search_result.ranges)
            ),
            "projection_cap": 5_000,
            "off_caller_thread": True,
        },
        revision_index_off_caller_thread=(
            bool(builder_threads) and builder_threads[0] != caller_thread
        ),
        gui_event_loop_measured=False,
        visible_ui_measured=False,
        generated_c_executed=False,
    )


__all__ = [
    "EXPECTED_RESOURCE_POLICY",
    "audit_maximum_input_fixtures",
    "scan_runtime_boundaries",
]
