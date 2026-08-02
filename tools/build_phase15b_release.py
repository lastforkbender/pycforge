"""Build the deterministic, source-only PyCForge Phase 15B release.

This packaging tool builds Python source and wheel artifacts, validates their
custody, and runs direct-versus-isolated transpilation smokes.  It never invokes
a C compiler, linker, loader, foreign-function interface, or generated-C
executable.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from typing import Mapping, Sequence
import zipfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._phase15b_release_contract import (
    assert_clean_scan,
    scan_file_map,
    scan_named_bytes,
    scan_source_archive_bytes,
    scan_wheel,
)

RELEASE_VERSION = "0.15.1"
CONVERTER_CONTRACT_VERSION = "0.14.3"
WORKSPACE_CONTRACT_VERSION = "pycforge-workspace/0.4"
WORKER_PROTOCOL_VERSION = "pycforge.worker-protocol/0.1"
ACTION_REGISTRY_VERSION = "pycforge.action-registry/0.1"
VISUAL_SYSTEM_VERSION = "pycforge.visual-system/0.1"
SOURCE_DATE_EPOCH = 1_700_000_000
SOURCE_ARCHIVE_NAME = "pycforge_phase_15b_v0_15_1.tar.gz"
SOURCE_ARCHIVE_ROOT = "pycforge_phase_15b_v0_15_1"
WHEEL_NAME = "pycforge-0.15.1-py3-none-any.whl"
HANDOFF_NAME = "PyCForge_Phase_15B_v0_15_1_Project_Handoff.txt"
PACKAGE_REPORT_NAME = "PyCForge_Phase_15B_v0_15_1_Package_Report.json"
CHECKSUMS_JSON_NAME = "PyCForge_Phase_15B_v0_15_1_Checksums.json"
CHECKSUMS_TEXT_NAME = "PyCForge_Phase_15B_v0_15_1_Checksums.txt"
VALIDATION_REPORT_NAME = "PyCForge_Phase_15B_v0_15_1_Validation_Report.json"
INTERNAL_VALIDATION_REPORT = "evidence/phase_15b/validation_report.json"
RELEASE_FINGERPRINT = PurePosixPath(
    "transition/phase_15b/release_fingerprint.json"
)
TRANSITION_MANIFEST = PurePosixPath("transition/phase_15b/manifest.json")
FINGERPRINT_DOMAIN = "pycforge-phase15b-release-tree-v1"
VALIDATION_SUBJECT_DOMAIN = "pycforge-phase15b-validation-subject-v1"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_15a_v0_15_0.tar.gz"
PREDECESSOR_ARCHIVE_SIZE = 1_480_105
PREDECESSOR_ARCHIVE_SHA256 = (
    "da33821ef82d948a9204af76baa5495ae2ff5df4500b12f4a67c12663cd95a06"
)
PREDECESSOR_TREE_FINGERPRINT = (
    "52014b9bd92912fe25b5d2faf42a388e98e828be66a3b371277d552666cf172a"
)
CONVERTER_SUBTREE_SHA256 = (
    "a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124"
)
CONVERTER_CUSTODY_DOMAIN = (
    "pycforge-checkpoint-e-release-tree-v1:subtree:pycforge/converter"
)
GZIP_LEVEL = 6
GZIP_MTIME = 0

EXTERNAL_ARTIFACTS = frozenset(
    {
        SOURCE_ARCHIVE_NAME,
        WHEEL_NAME,
        PACKAGE_REPORT_NAME,
        CHECKSUMS_JSON_NAME,
        CHECKSUMS_TEXT_NAME,
        VALIDATION_REPORT_NAME,
    }
)
EPHEMERAL_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "venv",
        "wheelhouse",
    }
)
EPHEMERAL_SUFFIXES = (".pyc", ".pyo", ".tar.gz", ".tgz", ".whl", ".zip")
MAX_RELEASE_SNAPSHOT_FILE_BYTES = 8 * 1024 * 1024
MAX_RELEASE_SNAPSHOT_TOTAL_BYTES = 64 * 1024 * 1024
RELEASE_SNAPSHOT_READ_BYTES = 1024 * 1024
NATIVE_SUFFIXES = frozenset(
    {".a", ".dll", ".dylib", ".exe", ".lib", ".o", ".obj", ".pyd", ".so"}
)
EXPECTED_CONSOLE_SCRIPTS = {
    "pycforge": "pycforge.laboratory.cli:main",
    "pycforge-workspace": "pycforge.ide.qt:run",
}
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
EXPECTED_BUILD_ENVIRONMENT = {
    "python": "3.12.13",
    "implementation": "cpython",
    "zlib": "1.3.1",
    "packages": {
        "pip": "26.0.1",
        "setuptools": "82.0.1",
        "wheel": "0.47.0",
    },
}
EXPECTED_PROJECT_CONFIGURATION = {
    "build-system": {
        "requires": ["setuptools==82.0.1"],
        "build-backend": "setuptools.build_meta",
    },
    "project": {
        "name": "pycforge",
        "version": RELEASE_VERSION,
        "description": "Deterministic bounded Python-to-C source transpiler",
        "requires-python": ">=3.11",
        "scripts": EXPECTED_CONSOLE_SCRIPTS,
        "optional-dependencies": {
            "workspace": ["PyQt5>=5.15,<6"],
        },
    },
    "tool": {
        "setuptools": {
            "packages": {"find": {"include": ["pycforge*"]}},
            "package-data": {
                "pycforge.ide": ["resources/icons/*.svg"],
            },
        },
        "pytest": {"ini_options": {"testpaths": ["tests"]}},
    },
}
REQUIRED_WHEEL_MEMBERS = frozenset(
    {
        "pycforge/__init__.py",
        "pycforge/_version.py",
        "pycforge/converter/facade.py",
        "pycforge/ide/__init__.py",
        "pycforge/ide/action_contract.py",
        "pycforge/ide/controller.py",
        "pycforge/ide/controller_conversion.py",
        "pycforge/ide/controller_io.py",
        "pycforge/ide/editor.py",
        "pycforge/ide/editor_lexical.py",
        "pycforge/ide/editor_sidebars.py",
        "pycforge/ide/editor_syntax.py",
        "pycforge/ide/find_replace.py",
        "pycforge/ide/icons.py",
        "pycforge/ide/io_service.py",
        "pycforge/ide/positions.py",
        "pycforge/ide/process_worker.py",
        "pycforge/ide/qt.py",
        "pycforge/ide/qt_actions.py",
        "pycforge/ide/qt_close.py",
        "pycforge/ide/qt_contract.py",
        "pycforge/ide/qt_documents.py",
        "pycforge/ide/qt_menus.py",
        "pycforge/ide/qt_projection.py",
        "pycforge/ide/qt_shell.py",
        "pycforge/ide/qt_state.py",
        "pycforge/ide/revisions.py",
        "pycforge/ide/search_service.py",
        "pycforge/ide/supervisor.py",
        "pycforge/ide/theme.py",
        "pycforge/ide/theme_stylesheet.py",
        "pycforge/ide/visual_tokens.py",
        "pycforge/ide/worker_protocol.py",
    }
)


class ReleaseBuildError(RuntimeError):
    """A deterministic release invariant was not satisfied."""


def canonical_json_bytes(value: object) -> bytes:
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


def strict_json_loads(
    payload: bytes,
    *,
    label: str,
    canonical: bool,
) -> object:
    def object_without_duplicates(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite number: {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=object_without_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReleaseBuildError(f"{label} is not strict JSON: {exc}") from exc
    if canonical and canonical_json_bytes(value) != payload:
        raise ReleaseBuildError(f"{label} is not canonical JSON")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_path(value: str | PurePosixPath) -> PurePosixPath:
    text = value.as_posix() if isinstance(value, PurePosixPath) else value
    path = PurePosixPath(text)
    if (
        not text
        or "\x00" in text
        or "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ReleaseBuildError(f"unsafe release path: {text!r}")
    return path


def _is_ephemeral(path: PurePosixPath) -> bool:
    return (
        any(part in EPHEMERAL_DIRECTORIES for part in path.parts)
        or any(part.endswith(".dist-info") for part in path.parts)
        or path.name in EXTERNAL_ARTIFACTS
        or path.name == ".coverage"
        or path.name.endswith(EPHEMERAL_SUFFIXES)
    )


def _snapshot_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _snapshot_entry_state(
    name: str,
    *,
    directory_fd: int,
    relative: PurePosixPath,
) -> os.stat_result:
    try:
        return os.stat(
            name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot inspect release tree entry safely: {relative}: {exc}"
        ) from exc


def _read_release_snapshot_file(
    name: str,
    *,
    directory_fd: int,
    relative: PurePosixPath,
    expected: os.stat_result,
) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        file_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot open release snapshot file safely: {relative}: {exc}"
        ) from exc

    try:
        opened = os.fstat(file_fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _snapshot_state(opened) != _snapshot_state(expected)
        ):
            raise ReleaseBuildError(
                f"release tree entry changed before snapshot read: {relative}"
            )

        remaining = expected.st_size
        payload = bytearray()
        while remaining:
            try:
                block = os.read(
                    file_fd,
                    min(RELEASE_SNAPSHOT_READ_BYTES, remaining),
                )
            except OSError as exc:
                raise ReleaseBuildError(
                    f"cannot read release snapshot file safely: {relative}: {exc}"
                ) from exc
            if not block:
                raise ReleaseBuildError(
                    f"release tree entry changed while snapshotting: {relative}"
                )
            payload.extend(block)
            remaining -= len(block)

        try:
            grew = os.read(file_fd, 1)
            final = os.fstat(file_fd)
        except OSError as exc:
            raise ReleaseBuildError(
                f"cannot verify release snapshot file safely: {relative}: {exc}"
            ) from exc
        if (
            grew
            or len(payload) != expected.st_size
            or _snapshot_state(final) != _snapshot_state(opened)
        ):
            raise ReleaseBuildError(
                f"release tree entry changed while snapshotting: {relative}"
            )
        return bytes(payload)
    finally:
        os.close(file_fd)


def release_file_map(root: Path) -> dict[str, bytes]:
    if not hasattr(os, "fwalk") or not hasattr(os, "O_NOFOLLOW"):
        raise ReleaseBuildError(
            "release snapshots require descriptor-bound filesystem access"
        )

    requested = Path(root)
    try:
        requested_state = requested.lstat()
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot inspect release root safely: {requested}: {exc}"
        ) from exc
    if stat.S_ISLNK(requested_state.st_mode):
        raise ReleaseBuildError(
            f"release root must not be a symlink: {requested}"
        )
    if not stat.S_ISDIR(requested_state.st_mode):
        raise ReleaseBuildError(
            f"release root is not a directory: {requested}"
        )

    try:
        base = requested.resolve(strict=True)
        root_state = os.stat(base, follow_symlinks=False)
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot resolve release root safely: {requested}: {exc}"
        ) from exc
    if (
        not stat.S_ISDIR(root_state.st_mode)
        or _snapshot_state(root_state) != _snapshot_state(requested_state)
    ):
        raise ReleaseBuildError(
            f"release root changed before snapshot traversal: {requested}"
        )

    files: dict[str, bytes] = {}
    total_bytes = 0
    expected_directories = {"": _snapshot_state(root_state)}

    def fail_walk(error: OSError) -> None:
        raise ReleaseBuildError(
            f"cannot traverse release tree safely: {error}"
        ) from error

    try:
        walker = os.fwalk(
            base,
            topdown=True,
            onerror=fail_walk,
            follow_symlinks=False,
        )
        for directory, directory_names, file_names, directory_fd in walker:
            try:
                relative_directory = Path(directory).relative_to(base)
            except ValueError as exc:
                raise ReleaseBuildError(
                    "release traversal escaped its authenticated root"
                ) from exc
            directory_key = (
                ""
                if relative_directory == Path(".")
                else safe_relative_path(
                    relative_directory.as_posix()
                ).as_posix()
            )
            expected_directory = expected_directories.pop(
                directory_key,
                None,
            )
            opened_directory = os.fstat(directory_fd)
            opened_directory_state = _snapshot_state(opened_directory)
            if (
                expected_directory is None
                or not stat.S_ISDIR(opened_directory.st_mode)
                or opened_directory_state != expected_directory
            ):
                label = directory_key or "."
                raise ReleaseBuildError(
                    "release directory changed before snapshot traversal: "
                    f"{label}"
                )

            retained: list[str] = []
            for name in sorted(directory_names):
                relative = safe_relative_path(
                    f"{directory_key}/{name}"
                    if directory_key
                    else name
                )
                entry = _snapshot_entry_state(
                    name,
                    directory_fd=directory_fd,
                    relative=relative,
                )
                if stat.S_ISLNK(entry.st_mode):
                    raise ReleaseBuildError(
                        f"release tree contains symlink: {relative}"
                    )
                if _is_ephemeral(relative):
                    continue
                if not stat.S_ISDIR(entry.st_mode):
                    raise ReleaseBuildError(
                        "release tree contains special directory: "
                        f"{relative}"
                    )
                expected_directories[relative.as_posix()] = (
                    _snapshot_state(entry)
                )
                retained.append(name)
            directory_names[:] = retained

            for name in sorted(file_names):
                relative = safe_relative_path(
                    f"{directory_key}/{name}"
                    if directory_key
                    else name
                )
                entry = _snapshot_entry_state(
                    name,
                    directory_fd=directory_fd,
                    relative=relative,
                )
                if stat.S_ISLNK(entry.st_mode):
                    raise ReleaseBuildError(
                        f"release tree contains symlink: {relative}"
                    )
                if not stat.S_ISREG(entry.st_mode):
                    raise ReleaseBuildError(
                        "release tree contains non-regular file: "
                        f"{relative}"
                    )
                if _is_ephemeral(relative):
                    continue
                if (
                    entry.st_size < 0
                    or entry.st_size > MAX_RELEASE_SNAPSHOT_FILE_BYTES
                ):
                    raise ReleaseBuildError(
                        "release snapshot file exceeds per-file byte limit: "
                        f"{relative}"
                    )
                if (
                    total_bytes
                    > MAX_RELEASE_SNAPSHOT_TOTAL_BYTES - entry.st_size
                ):
                    raise ReleaseBuildError(
                        "release snapshot exceeds total byte limit"
                    )
                payload = _read_release_snapshot_file(
                    name,
                    directory_fd=directory_fd,
                    relative=relative,
                    expected=entry,
                )
                files[relative.as_posix()] = payload
                total_bytes += len(payload)

            if _snapshot_state(os.fstat(directory_fd)) != (
                opened_directory_state
            ):
                label = directory_key or "."
                raise ReleaseBuildError(
                    "release directory changed while snapshotting: "
                    f"{label}"
                )
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot traverse release tree safely: {exc}"
        ) from exc

    if expected_directories:
        missing = min(expected_directories)
        raise ReleaseBuildError(
            "release directory disappeared during snapshot traversal: "
            f"{missing}"
        )
    try:
        final_requested_state = requested.lstat()
        final_root_state = os.stat(base, follow_symlinks=False)
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot verify release root safely: {requested}: {exc}"
        ) from exc
    if (
        _snapshot_state(final_requested_state)
        != _snapshot_state(requested_state)
        or _snapshot_state(final_root_state) != _snapshot_state(root_state)
    ):
        raise ReleaseBuildError(
            f"release root changed while snapshotting: {requested}"
        )
    if not files:
        raise ReleaseBuildError("release tree contains no regular files")
    return dict(sorted(files.items()))


def hash_file_map(files: Mapping[str, bytes], *, domain: str) -> str:
    digest = hashlib.sha256()
    domain_bytes = domain.encode("utf-8")
    digest.update(len(domain_bytes).to_bytes(8, "big"))
    digest.update(domain_bytes)
    for name in sorted(files):
        path = safe_relative_path(name).as_posix().encode("utf-8")
        data = files[name]
        digest.update(len(path).to_bytes(8, "big"))
        digest.update(path)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validation_subject_hash(
    files: Mapping[str, bytes],
) -> tuple[str, int]:
    subject = dict(files)
    subject.pop(INTERNAL_VALIDATION_REPORT, None)
    subject.pop(RELEASE_FINGERPRINT.as_posix(), None)
    return (
        hash_file_map(subject, domain=VALIDATION_SUBJECT_DOMAIN),
        len(subject),
    )


def release_tree_hash(root: Path) -> tuple[str, int]:
    files = release_file_map(root)
    files.pop(RELEASE_FINGERPRINT.as_posix(), None)
    return hash_file_map(files, domain=FINGERPRINT_DOMAIN), len(files)


def release_subtree_hash(
    root: Path,
    prefix: str,
    *,
    domain: str | None = None,
) -> tuple[str, int]:
    files = release_file_map(root)
    marker = safe_relative_path(prefix).as_posix().rstrip("/") + "/"
    selected = {
        name[len(marker) :]: data
        for name, data in files.items()
        if name.startswith(marker)
    }
    if not selected:
        raise ReleaseBuildError(f"release subtree is absent: {prefix}")
    return (
        hash_file_map(
            selected,
            domain=domain or f"{FINGERPRINT_DOMAIN}:subtree:{prefix}",
        ),
        len(selected),
    )


def canonical_gzip_bytes(raw_tar: bytes) -> bytes:
    compressor = zlib.compressobj(GZIP_LEVEL, zlib.DEFLATED, -15)
    body = compressor.compress(raw_tar) + compressor.flush()
    header = b"\x1f\x8b\x08\x00" + struct.pack("<I", GZIP_MTIME) + b"\x00\x03"
    trailer = struct.pack(
        "<II", zlib.crc32(raw_tar) & 0xFFFFFFFF, len(raw_tar) & 0xFFFFFFFF
    )
    return header + body + trailer


def normalized_source_archive_bytes(
    files: Mapping[str, bytes],
    *,
    archive_root: str = SOURCE_ARCHIVE_ROOT,
) -> bytes:
    root = safe_relative_path(archive_root)
    if len(root.parts) != 1:
        raise ReleaseBuildError("archive root must be one path component")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(files):
            relative = safe_relative_path(name)
            data = files[name]
            info = tarfile.TarInfo((root / relative).as_posix())
            info.size = len(data)
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = SOURCE_DATE_EPOCH
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    return canonical_gzip_bytes(raw.getvalue())


def inspect_source_archive(
    payload: bytes, expected_files: Mapping[str, bytes]
) -> dict[str, object]:
    if payload[:10] != b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03":
        raise ReleaseBuildError("source archive gzip header is not canonical")
    try:
        raw = zlib.decompress(payload, wbits=31)
    except zlib.error as exc:
        raise ReleaseBuildError(f"source archive gzip is invalid: {exc}") from exc
    if canonical_gzip_bytes(raw) != payload:
        raise ReleaseBuildError("source archive gzip bytes are not canonical")
    if normalized_source_archive_bytes(expected_files) != payload:
        raise ReleaseBuildError(
            "source archive bytes are not the normalized release encoding"
        )
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        members = tar.getmembers()
        expected_names = [
            (PurePosixPath(SOURCE_ARCHIVE_ROOT) / safe_relative_path(name))
            .as_posix()
            for name in sorted(expected_files)
        ]
        if [member.name for member in members] != expected_names:
            raise ReleaseBuildError(
                "source archive member order or inventory is not canonical"
            )
        for member in members:
            path = safe_relative_path(member.name)
            if (
                path.parts[0] != SOURCE_ARCHIVE_ROOT
                or not member.isfile()
                or member.type != tarfile.REGTYPE
                or member.mode != 0o644
                or member.uid != 0
                or member.gid != 0
                or member.uname
                or member.gname
                or member.mtime != SOURCE_DATE_EPOCH
                or member.pax_headers
            ):
                raise ReleaseBuildError(
                    "source archive member metadata is not normalized: "
                    f"{path}"
                )
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in files:
                raise ReleaseBuildError(f"duplicate archive member: {relative}")
            stream = tar.extractfile(member)
            if stream is None:
                raise ReleaseBuildError(f"unreadable archive member: {relative}")
            files[relative] = stream.read()
    if files != dict(expected_files):
        raise ReleaseBuildError("source archive does not match the release tree")
    return {
        "archive_root": SOURCE_ARCHIVE_ROOT,
        "member_count": len(files),
        "regular_files_only": True,
        "safe_paths": True,
        "canonical_gzip": True,
        "normalized_ustar": True,
    }


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "SOURCE_DATE_EPOCH": str(SOURCE_DATE_EPOCH),
            "TZ": "UTC",
        }
    )
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    return environment


def _run(command: Sequence[str], *, cwd: Path, label: str) -> str:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseBuildError(f"{label} could not run: {exc}") from exc
    if completed.returncode:
        raise ReleaseBuildError(
            f"{label} failed ({completed.returncode}): "
            f"{completed.stderr[-4000:]!r}"
        )
    return completed.stdout


def _copy_tree(files: Mapping[str, bytes], destination: Path) -> None:
    for name, data in files.items():
        target = destination.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o644)
        os.utime(target, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))


def _build_wheel(
    files: Mapping[str, bytes], work: Path, build_number: int
) -> Path:
    source = work / f"wheel-source-{build_number}"
    output = work / f"wheel-output-{build_number}"
    source.mkdir()
    output.mkdir()
    _copy_tree(files, source)
    _run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            "--no-index",
            "--no-cache-dir",
            "--wheel-dir",
            str(output),
            str(source),
        ),
        cwd=work,
        label=f"wheel build {build_number}",
    )
    wheels = tuple(output.glob("*.whl"))
    if len(wheels) != 1 or wheels[0].name != WHEEL_NAME:
        raise ReleaseBuildError(f"unexpected wheel inventory: {wheels!r}")
    return wheels[0]


def _record_digest(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return "sha256=" + digest.rstrip(b"=").decode("ascii")


def inspect_wheel(
    path: Path,
    *,
    expected_package_files: Mapping[str, bytes] | None = None,
) -> dict[str, object]:
    vocabulary = scan_wheel(path)
    assert_clean_scan(vocabulary, label="wheel")
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if len(names) != len(set(names)) or package.testzip() is not None:
                raise ReleaseBuildError("wheel ZIP inventory is invalid")
            members = {safe_relative_path(name).as_posix(): package.read(name)
                       for name in names}
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReleaseBuildError(f"cannot inspect wheel: {exc}") from exc
    missing = sorted(REQUIRED_WHEEL_MEMBERS - set(members))
    if missing:
        raise ReleaseBuildError("wheel omits required members: " + ", ".join(missing))
    package_members = {
        name for name in members if name.startswith("pycforge/")
    }
    expected_files = (
        {
            name: payload
            for name, payload in release_file_map(ROOT).items()
            if name.startswith("pycforge/")
            and (
                name.endswith(".py")
                or (
                    name.startswith("pycforge/ide/resources/icons/")
                    and name.endswith(".svg")
                )
            )
        }
        if expected_package_files is None
        else dict(expected_package_files)
    )
    expected_members = set(expected_files)
    if package_members != expected_members:
        extra = len(package_members - expected_members)
        omitted = len(expected_members - package_members)
        raise ReleaseBuildError(
            "wheel package inventory differs from the exact source map "
            f"(extra={extra}, omitted={omitted})"
        )
    byte_mismatches = [
        name
        for name in sorted(expected_members)
        if members[name] != expected_files[name]
    ]
    if byte_mismatches:
        raise ReleaseBuildError(
            "wheel package bytes differ from the audited source map "
            f"(members={len(byte_mismatches)})"
        )
    dist_info_roots = {
        PurePosixPath(name).parts[0]
        for name in members
        if ".dist-info/" in name
    }
    expected_dist_info = f"pycforge-{RELEASE_VERSION}.dist-info"
    if dist_info_roots != {expected_dist_info}:
        raise ReleaseBuildError("wheel dist-info root is not exact")
    allowed_dist_info = {
        f"{expected_dist_info}/{name}"
        for name in (
            "METADATA",
            "WHEEL",
            "entry_points.txt",
            "top_level.txt",
            "RECORD",
        )
    }
    if set(members) != package_members | allowed_dist_info:
        raise ReleaseBuildError("wheel contains an undeclared metadata member")
    for name, payload in members.items():
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReleaseBuildError(
                f"wheel member is not source text: {name}"
            ) from exc
        if b"\x00" in payload:
            raise ReleaseBuildError(
                f"wheel member contains binary null bytes: {name}"
            )
    native = sorted(
        name for name in members
        if PurePosixPath(name).suffix.lower() in NATIVE_SUFFIXES
    )
    if native:
        raise ReleaseBuildError("wheel contains native code: " + ", ".join(native))
    svg = sorted(
        name for name in members
        if name.startswith("pycforge/ide/resources/icons/") and name.endswith(".svg")
    )
    if len(svg) != 41:
        raise ReleaseBuildError(f"wheel contains {len(svg)} SVG assets, expected 41")

    def unique(suffix: str) -> str:
        matches = [name for name in members if name.endswith(f".dist-info/{suffix}")]
        if len(matches) != 1:
            raise ReleaseBuildError(f"wheel has {len(matches)} {suffix} members")
        return matches[0]

    metadata_name = unique("METADATA")
    wheel_metadata_name = unique("WHEEL")
    entry_points_name = unique("entry_points.txt")
    record_name = unique("RECORD")
    metadata = BytesParser(policy=email_policy).parsebytes(members[metadata_name])
    wheel_metadata = BytesParser(policy=email_policy).parsebytes(
        members[wheel_metadata_name]
    )
    if metadata.get("Metadata-Version") != "2.4":
        raise ReleaseBuildError("wheel metadata schema is not exact")
    if metadata.get("Name") != "pycforge":
        raise ReleaseBuildError("wheel project name is not pycforge")
    if metadata.get("Version") != RELEASE_VERSION:
        raise ReleaseBuildError("wheel version is not " + RELEASE_VERSION)
    if metadata.get("Summary") != EXPECTED_PROJECT_CONFIGURATION[
        "project"
    ]["description"]:
        raise ReleaseBuildError("wheel project summary is not exact")
    if metadata.get("Requires-Python") != ">=3.11":
        raise ReleaseBuildError("wheel Python requirement is not exact")
    if metadata.get_all("Provides-Extra", []) != ["workspace"]:
        raise ReleaseBuildError("wheel optional extra inventory is not exact")
    if metadata.get_all("Requires-Dist", []) != [
        'PyQt5<6,>=5.15; extra == "workspace"'
    ]:
        raise ReleaseBuildError("wheel dependency inventory is not exact")
    if wheel_metadata.get("Wheel-Version") != "1.0":
        raise ReleaseBuildError("wheel schema version is not exact")
    if wheel_metadata.get("Root-Is-Purelib") != "true":
        raise ReleaseBuildError("wheel is not pure Python")
    if wheel_metadata.get_all("Tag", []) != ["py3-none-any"]:
        raise ReleaseBuildError("wheel tag inventory is not exact")
    expected_generator = f"setuptools ({package_version('setuptools')})"
    if wheel_metadata.get("Generator") != expected_generator:
        raise ReleaseBuildError("wheel generator identity is not exact")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(members[entry_points_name].decode("utf-8"))
    if parser.sections() != ["console_scripts"] or parser.defaults():
        raise ReleaseBuildError("wheel entry-point groups are not exact")
    scripts = dict(parser.items("console_scripts"))
    if scripts != EXPECTED_CONSOLE_SCRIPTS:
        raise ReleaseBuildError("wheel console scripts do not match")
    top_level_name = unique("top_level.txt")
    if members[top_level_name] != b"pycforge\n":
        raise ReleaseBuildError("wheel top-level package record is not exact")
    rows = list(csv.reader(io.StringIO(members[record_name].decode("utf-8"))))
    if len(rows) != len(members) or {row[0] for row in rows} != set(members):
        raise ReleaseBuildError("wheel RECORD coverage is incomplete")
    for name, digest, size in rows:
        if name == record_name:
            if digest or size:
                raise ReleaseBuildError("wheel RECORD self-row is not empty")
        elif digest != _record_digest(members[name]) or size != str(len(members[name])):
            raise ReleaseBuildError(f"wheel RECORD mismatch: {name}")
    return {
        "zip_members": len(members),
        "record_entries": len(rows),
        "metadata_version": metadata.get("Version"),
        "tag": "py3-none-any",
        "pure_python": True,
        "svg_assets": len(svg),
        "native_members": 0,
        "package_members_exact": True,
        "package_bytes_exact": True,
        "console_scripts": dict(sorted(scripts.items())),
        "vocabulary_custody": vocabulary.to_report(),
    }


def _extract_source(payload: bytes, destination: Path) -> Path:
    raw = zlib.decompress(payload, wbits=31)
    root = destination / SOURCE_ARCHIVE_ROOT
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        for member in tar.getmembers():
            path = safe_relative_path(member.name)
            relative = PurePosixPath(*path.parts[1:])
            target = root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = tar.extractfile(member)
            if stream is None:
                raise ReleaseBuildError(f"source member is unreadable: {path}")
            target.write_bytes(stream.read())
    return root


SMOKE_SCRIPT = """\
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pycforge import ConversionRequest, PythonToCConverter, __version__
from pycforge.converter.contracts.versions import CONVERTER_CONTRACT_VERSION
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_json
from pycforge.ide import (
    ACTION_REGISTRY_VERSION,
    VISUAL_SYSTEM_VERSION,
    WORKSPACE_CONTRACT_VERSION,
)
from pycforge.ide.supervisor import ProcessConversionSupervisor
from pycforge.ide.worker_protocol import (
    PROTOCOL_SCHEMA,
    bundle_fingerprint_for_request,
)


def main():
    assert __version__ == "0.15.1"
    assert CONVERTER_CONTRACT_VERSION == "0.14.3"
    assert WORKSPACE_CONTRACT_VERSION == "pycforge-workspace/0.4"
    assert ACTION_REGISTRY_VERSION == "pycforge.action-registry/0.1"
    assert VISUAL_SYSTEM_VERSION == "pycforge.visual-system/0.1"
    assert PROTOCOL_SCHEMA == "pycforge.worker-protocol/0.1"
    source = "def add(a: int, b: int) -> int:\\n    return a + b\\n"
    request = ConversionRequest.from_source(source)
    observation = ObservationOptions("Full", True)
    direct = PythonToCConverter().convert(
        request,
        observation=observation,
    )
    supervisor = ProcessConversionSupervisor()
    try:
        isolated = supervisor.submit(
            generation=1,
            bundle_fingerprint=bundle_fingerprint_for_request(request),
            request=request,
            observation=observation,
        ).result(timeout=30)
    finally:
        supervisor.close(timeout=3)
    direct_json = result_to_json(direct)
    isolated_json = result_to_json(isolated)
    assert isolated_json == direct_json
    print(json.dumps({
        "direct_isolated_exact": True,
        "generated_c_sha256": hashlib.sha256(
            direct.generated_c.encode("utf-8")
        ).hexdigest(),
        "module_path": str(Path(sys.modules["pycforge"].__file__).resolve()),
        "status": direct.status.value,
    }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
"""


def _package_smokes(
    wheel: Path, source_payload: bytes, work: Path
) -> dict[str, object]:
    environment = work / "venv"
    _run((sys.executable, "-m", "venv", str(environment)), cwd=work, label="venv")
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _run(
        (
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            str(wheel),
        ),
        cwd=work,
        label="isolated wheel install",
    )
    wheel_dir = work / "wheel-smoke"
    wheel_dir.mkdir()
    wheel_script = wheel_dir / "smoke.py"
    wheel_script.write_text(SMOKE_SCRIPT, encoding="utf-8")
    wheel_report = json.loads(
        _run((str(python), "-I", str(wheel_script)), cwd=wheel_dir, label="wheel smoke")
    )
    wheel_module = Path(str(wheel_report.pop("module_path"))).resolve()
    try:
        wheel_module.relative_to(environment.resolve())
    except ValueError as exc:
        raise ReleaseBuildError(
            "wheel smoke did not import from the isolated environment"
        ) from exc
    wheel_report["module_origin"] = "isolated-installed-wheel"
    source_dir = work / "source-smoke"
    source_dir.mkdir()
    source_root = _extract_source(source_payload, source_dir)
    source_script = source_root / "_phase15b_package_smoke.py"
    source_script.write_text(SMOKE_SCRIPT, encoding="utf-8")
    try:
        source_report = json.loads(
            _run(
                (str(python), "-I", str(source_script)),
                cwd=source_root,
                label="source archive smoke",
            )
        )
        source_module = Path(str(source_report.pop("module_path"))).resolve()
        try:
            source_module.relative_to(source_root.resolve())
        except ValueError as exc:
            raise ReleaseBuildError(
                "source smoke did not import from the extracted archive"
            ) from exc
        source_report["module_origin"] = "extracted-source-archive"
    finally:
        source_script.unlink(missing_ok=True)
    return {
        "isolated_wheel_install": True,
        "wheel": wheel_report,
        "source_archive": source_report,
        "direct_isolated_exact": True,
        "generated_c_compiled_or_executed": False,
    }


def _artifact(path: Path) -> dict[str, object]:
    return {
        "filename": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _write(path: Path, data: bytes) -> None:
    if path.exists():
        raise ReleaseBuildError(f"release output already exists: {path}")
    path.write_bytes(data)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_release_directory(stage: Path, output: Path) -> None:
    """Durably publish one complete sibling directory under an exclusive lock."""

    if not stage.is_dir() or stage.parent != output.parent:
        raise ReleaseBuildError(
            "release staging and output directories must be siblings"
        )
    lock = output.with_name(f".{output.name}.publish.lock")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        lock_fd = os.open(lock, flags, 0o600)
    except FileExistsError as exc:
        raise ReleaseBuildError(
            "another release publication holds the output lock"
        ) from exc
    except OSError as exc:
        raise ReleaseBuildError(
            f"cannot acquire the release publication lock: {exc}"
        ) from exc
    try:
        if os.path.lexists(output):
            raise ReleaseBuildError(
                "release output directory appeared during the build"
            )
        for artifact in sorted(stage.iterdir(), key=lambda path: path.name):
            if not artifact.is_file() or artifact.is_symlink():
                raise ReleaseBuildError(
                    "release staging contains a non-regular artifact"
                )
            with artifact.open("rb") as stream:
                os.fsync(stream.fileno())
        _fsync_directory(stage)
        try:
            os.rename(stage, output)
        except OSError as exc:
            raise ReleaseBuildError(
                f"cannot publish release directory atomically: {exc}"
            ) from exc
        _fsync_directory(output.parent)
    finally:
        os.close(lock_fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        else:
            _fsync_directory(output.parent)


def _validate_promotion_report(
    validation: object,
    *,
    candidate_files: Mapping[str, bytes],
    candidate_root: Path,
) -> None:
    if not isinstance(validation, dict):
        raise ReleaseBuildError("internal validation report is not an object")
    expected_keys = {
        "schema",
        "mode",
        "scope",
        "passed",
        "promotion_eligible",
        "promotion_scope",
        "phase_15b_gate_eligible",
        "visible_ui_promotion_eligible",
        "distribution_promotion_eligible",
        "phase_15b_opened",
        "phase_15c_opened",
        "phase_15d_opened",
        "audits",
    }
    if set(validation) != expected_keys:
        raise ReleaseBuildError(
            "internal validation report field inventory is not exact"
        )
    expected = {
        "schema": "pycforge.phase15b-validation-report/1",
        "mode": "promotion",
        "scope": "phase-15b-application-shell-current-host",
        "passed": True,
        "promotion_eligible": True,
        "promotion_scope": "phase-15b-milestone-only",
        "phase_15b_gate_eligible": True,
        "visible_ui_promotion_eligible": False,
        "distribution_promotion_eligible": False,
        "phase_15b_opened": True,
        "phase_15c_opened": False,
        "phase_15d_opened": False,
    }
    if any(
        validation.get(key) != value
        or type(validation.get(key)) is not type(value)
        for key, value in expected.items()
    ):
        raise ReleaseBuildError(
            "internal Phase 15B promotion validation is not exact"
        )
    audits = validation.get("audits")
    required_audits = {
        "validator-root-custody",
        "phase15b-contract-identities",
        "frozen-converter-subtree",
        "phase15a-predecessor-authentication",
        "retired-theme-vocabulary-custody",
        "declarative-action-and-menu-contract",
        "pycforge-visual-system",
        "phase15b-validation-subject",
        "runtime-isolation-and-toolchain-boundary",
        "direct-vs-isolated-equivalence",
        "bounded-maximum-input-fixtures",
        "hundred-edit-convert-cancel-cycles",
        "honest-platform-scope",
        "source-transpiler-safety",
    }
    if (
        not isinstance(audits, list)
        or not audits
        or any(
            not isinstance(audit, dict)
            or audit.get("passed") is not True
            or audit.get("errors") != []
            for audit in audits
        )
    ):
        raise ReleaseBuildError(
            "internal Phase 15B validation audits are not all passing"
        )
    audit_names = [
        audit.get("audit") for audit in audits if isinstance(audit, dict)
    ]
    if (
        len(audit_names) != len(required_audits)
        or set(audit_names) != required_audits
    ):
        raise ReleaseBuildError(
            "internal Phase 15B validation audit inventory is not exact"
        )
    by_name = {
        str(audit["audit"]): audit
        for audit in audits
        if isinstance(audit, dict)
    }
    root_custody = by_name["validator-root-custody"]
    validation_subject = by_name["phase15b-validation-subject"]
    predecessor = by_name["phase15a-predecessor-authentication"]
    vocabulary = by_name["retired-theme-vocabulary-custody"]
    converter = by_name["frozen-converter-subtree"]
    actions = by_name["declarative-action-and-menu-contract"]
    visual = by_name["pycforge-visual-system"]
    isolation = by_name["runtime-isolation-and-toolchain-boundary"]
    equivalence = by_name["direct-vs-isolated-equivalence"]
    maximums = by_name["bounded-maximum-input-fixtures"]
    cycles = by_name["hundred-edit-convert-cancel-cycles"]
    platform_scope = by_name["honest-platform-scope"]
    safety = by_name["source-transpiler-safety"]
    expected_root = str(candidate_root.resolve())
    if (
        root_custody.get("imported_candidate_exercised") is not True
        or root_custody.get("requested_root") != expected_root
        or root_custody.get("imported_root") != expected_root
    ):
        raise ReleaseBuildError("validator root custody is not authenticated")
    subject_hash, subject_count = validation_subject_hash(candidate_files)
    if (
        validation_subject.get("domain") != VALIDATION_SUBJECT_DOMAIN
        or validation_subject.get("sha256") != subject_hash
        or validation_subject.get("file_count") != subject_count
        or validation_subject.get("excluded")
        != [
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT.as_posix(),
        ]
    ):
        raise ReleaseBuildError(
            "validation subject is not bound to the release snapshot"
        )
    if (
        predecessor.get("required") is not True
        or predecessor.get("archive_authenticated") is not True
        or predecessor.get("status") != "authenticated"
        or predecessor.get("archive_name") != PREDECESSOR_ARCHIVE_NAME
        or predecessor.get("expected_size") != PREDECESSOR_ARCHIVE_SIZE
        or predecessor.get("actual_size") != PREDECESSOR_ARCHIVE_SIZE
        or predecessor.get("expected_sha256") != PREDECESSOR_ARCHIVE_SHA256
        or predecessor.get("actual_sha256") != PREDECESSOR_ARCHIVE_SHA256
        or predecessor.get("expected_tree_fingerprint")
        != PREDECESSOR_TREE_FINGERPRINT
        or predecessor.get("actual_tree_fingerprint")
        != PREDECESSOR_TREE_FINGERPRINT
        or predecessor.get("converter_subtree_sha256")
        != CONVERTER_SUBTREE_SHA256
        or predecessor.get("archive_extracted") is not False
    ):
        raise ReleaseBuildError("Phase 15A predecessor is not authenticated")
    if (
        vocabulary.get("path_match_count") != 0
        or vocabulary.get("content_match_count") != 0
    ):
        raise ReleaseBuildError("release vocabulary custody is not clean")
    if (
        converter.get("actual_sha256") != CONVERTER_SUBTREE_SHA256
        or converter.get("file_count") != 92
    ):
        raise ReleaseBuildError("converter custody evidence is not exact")
    if (
        actions.get("actions") != 33
        or actions.get("generated_c_mutation_actions") != 0
        or actions.get("qaction_constructor_owners") != ["qt_actions.py"]
    ):
        raise ReleaseBuildError("action-registry evidence is not exact")
    if (
        visual.get("svg_assets") != 41
        or visual.get("high_dpi_attributes_before_application") is not True
        or visual.get("window_brand_mark") is not True
    ):
        raise ReleaseBuildError("visual-system evidence is not exact")
    isolation_false_flags = (
        "pickle_transport_allowed",
        "object_connection_transport_allowed",
        "subprocess_allowed",
        "toolchain_allowed",
        "gui_in_process_conversion_allowed",
    )
    if (
        isolation.get("converter_facade_authorities")
        != ["pycforge/ide/process_worker.py"]
        or isolation.get("byte_connection_methods")
        != ["close", "recv_bytes", "send_bytes"]
        or type(isolation.get("byte_transport_call_sites")) is not int
        or isolation.get("byte_transport_call_sites", 0) < 3
        or any(isolation.get(key) is not False for key in isolation_false_flags)
    ):
        raise ReleaseBuildError("runtime-isolation evidence is not exact")
    cases = equivalence.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != 2
        or {
            case.get("case")
            for case in cases
            if isinstance(case, dict)
        }
        != {"single-module", "keyword-only"}
        or any(
            not isinstance(case, dict)
            or case.get("equivalent") is not True
            or not isinstance(case.get("case"), str)
            or not isinstance(case.get("result_sha256"), str)
            or len(case["result_sha256"]) != 64
            for case in cases
        )
        or equivalence.get("same_public_facade") is not True
        or equivalence.get("generated_c_executed") is not False
    ):
        raise ReleaseBuildError(
            "direct-isolated equivalence evidence is not exact"
        )
    fixtures = maximums.get("fixtures")
    dense_search = maximums.get("dense_search")
    if (
        maximums.get("policy") != EXPECTED_RESOURCE_POLICY
        or not isinstance(fixtures, dict)
        or set(fixtures)
        != {
            "simultaneous_valid_syntax",
            "exact_byte_ceiling",
            "near_token_ceiling",
            "near_ast_ceiling",
        }
        or not isinstance(dense_search, dict)
        or dense_search.get("total_matches") != 50_000
        or dense_search.get("stored_ranges") != 5_000
        or dense_search.get("projection_cap") != 5_000
        or dense_search.get("off_caller_thread") is not True
        or maximums.get("revision_index_off_caller_thread") is not True
        or maximums.get("gui_event_loop_measured") is not False
        or maximums.get("visible_ui_measured") is not False
        or maximums.get("generated_c_executed") is not False
    ):
        raise ReleaseBuildError("maximum-input evidence is not exact")
    simultaneous = fixtures["simultaneous_valid_syntax"]
    byte_ceiling = fixtures["exact_byte_ceiling"]
    token_ceiling = fixtures["near_token_ceiling"]
    ast_ceiling = fixtures["near_ast_ceiling"]
    if (
        not isinstance(simultaneous, dict)
        or simultaneous.get("utf8_bytes") != 999_999
        or simultaneous.get("source_lines") != 100_000
        or type(simultaneous.get("tokens")) is not int
        or simultaneous.get("tokens", 250_001) > 250_000
        or type(simultaneous.get("ast_nodes")) is not int
        or simultaneous.get("ast_nodes", 100_001) > 100_000
        or not isinstance(byte_ceiling, dict)
        or byte_ceiling.get("utf8_bytes") != 1_000_000
        or type(byte_ceiling.get("request_frame_bytes")) is not int
        or byte_ceiling.get("request_frame_bytes", 0) <= 1_000_000
        or byte_ceiling.get("request_frame_bytes", 8_388_609) > 8_388_608
        or byte_ceiling.get("oversized_rejected") is not True
        or not isinstance(token_ceiling, dict)
        or type(token_ceiling.get("tokens")) is not int
        or not 249_900 <= token_ceiling.get("tokens", 0) <= 250_000
        or not isinstance(ast_ceiling, dict)
        or type(ast_ceiling.get("ast_nodes")) is not int
        or not 99_900 <= ast_ceiling.get("ast_nodes", 0) <= 100_000
    ):
        raise ReleaseBuildError(
            "maximum-input fixture evidence is not exact"
        )
    cycle_ints = {
        key: cycles.get(key)
        for key in (
            "requested_cycles",
            "submitted_cycles",
            "canceled_cycles",
            "active_worker_cancel_cycles",
            "started_workers",
            "reaped_workers",
            "maximum_simultaneous_workers",
        )
    }
    if (
        any(type(value) is not int for value in cycle_ints.values())
        or cycle_ints["requested_cycles"] != 100
        or cycle_ints["submitted_cycles"] != 100
        or cycle_ints["canceled_cycles"] != 100
        or cycle_ints["active_worker_cancel_cycles"] != 10
        or cycle_ints["started_workers"] != cycle_ints["reaped_workers"]
        or cycle_ints["started_workers"] < 10
        or cycle_ints["maximum_simultaneous_workers"] != 1
        or cycles.get("active_pid_after_gate") is not None
        or cycles.get("pending_generation_after_gate") is not None
    ):
        raise ReleaseBuildError("stress-cycle evidence is not exact")
    if (
        platform_scope.get("visible_windows_11_exercised") is not False
        or platform_scope.get("visible_linux_desktop_exercised") is not False
        or platform_scope.get("phase_15d_platform_gate_required") is not True
    ):
        raise ReleaseBuildError("platform-scope evidence is not honest")
    safety_flags = (
        "toolchain_invoked",
        "compiler_invoked",
        "linker_invoked",
        "loader_invoked",
        "foreign_function_invoked",
        "generated_c_compiled",
        "generated_c_linked",
        "generated_c_loaded",
        "generated_c_executed",
    )
    if any(safety.get(key) is not False for key in safety_flags):
        raise ReleaseBuildError("source-transpiler safety evidence is not exact")


def _validate_transition_manifest(manifest: object) -> None:
    if not isinstance(manifest, dict):
        raise ReleaseBuildError("Phase 15B transition manifest is not an object")
    expected_keys = {
        "schema",
        "phase",
        "version",
        "converter_contract_version",
        "workspace_contract_version",
        "worker_protocol_version",
        "action_registry_version",
        "visual_system_version",
        "settings_schema_version",
        "status",
        "scope_status",
        "opened_on",
        "roadmap_revision",
        "predecessor",
        "accepted_scope",
        "required_files",
        "release_artifacts",
        "platform_evidence",
        "promotion",
        "non_goals",
        "phase_15c",
        "phase_15d",
    }
    if set(manifest) != expected_keys:
        raise ReleaseBuildError(
            "Phase 15B transition manifest field inventory is not exact"
        )
    expected = {
        "schema": "pycforge.phase15b-manifest/0.15.1",
        "phase": "15B",
        "version": RELEASE_VERSION,
        "converter_contract_version": CONVERTER_CONTRACT_VERSION,
        "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
        "worker_protocol_version": WORKER_PROTOCOL_VERSION,
        "action_registry_version": ACTION_REGISTRY_VERSION,
        "visual_system_version": VISUAL_SYSTEM_VERSION,
        "status": "promoted",
        "scope_status": "sealed",
    }
    if any(
        manifest.get(key) != value
        or type(manifest.get(key)) is not type(value)
        for key, value in expected.items()
    ):
        raise ReleaseBuildError(
            "Phase 15B transition manifest is not promoted and exact"
        )
    expected_predecessor = {
        "phase": "15A",
        "version": "0.15.0",
        "archive": PREDECESSOR_ARCHIVE_NAME,
        "archive_root": "pycforge_phase_15a_v0_15_0",
        "archive_size": PREDECESSOR_ARCHIVE_SIZE,
        "archive_sha256": PREDECESSOR_ARCHIVE_SHA256,
        "tree_sha256": PREDECESSOR_TREE_FINGERPRINT,
        "converter_subtree_sha256": CONVERTER_SUBTREE_SHA256,
        "authenticated_before_work": True,
    }
    expected_scope = {
        "single_declarative_action_registry": True,
        "native_backed_custom_main_menus": True,
        "native_backed_custom_context_menus": True,
        "required_context_surfaces": 8,
        "generated_c_context_read_only": True,
        "semantic_visual_tokens": True,
        "packaged_scalable_svg_icons": 41,
        "keyboard_and_mnemonic_contract": True,
        "logical_high_dpi_metrics": True,
        "accessibility_metadata": True,
        "phase_15a_process_isolation_preserved": True,
        "bounded_inspector_projection": True,
        "validation_subject_bound_to_release_snapshot": True,
        "atomic_staged_release_publication": True,
        "retired_theme_vocabulary_release_gate": True,
    }
    expected_required_files = [
        "README.md",
        "CURRENT_STATE.md",
        "CHANGELOG.md",
        HANDOFF_NAME,
        "specifications/pycforge_workspace.md",
        "pycforge/ide/action_contract.py",
        "pycforge/ide/qt_actions.py",
        "pycforge/ide/qt_menus.py",
        "pycforge/ide/icons.py",
        "pycforge/ide/visual_tokens.py",
        "pycforge/ide/theme.py",
        "pycforge/ide/theme_stylesheet.py",
        "pycforge/ide/panels.py",
        "pycforge/ide/qt_documents.py",
        "pycforge/ide/qt_projection.py",
        "pycforge/ide/qt_shell.py",
        "transition/phase_15b/entry_criteria.md",
        "transition/phase_15b/application_shell_decision.md",
        "transition/phase_15b/rollback_conditions.md",
        "transition/phase_15b/gate_evidence.md",
        "transition/phase_15b/manifest.json",
        RELEASE_FINGERPRINT.as_posix(),
        "evidence/phase_15b/action_registry_evidence.json",
        "evidence/phase_15b/visual_system_evidence.json",
        INTERNAL_VALIDATION_REPORT,
        "tools/_phase15b_release_contract.py",
        "tools/validate_phase15b.py",
        "tools/build_phase15b_release.py",
        "tests/test_phase15b_action_foundation.py",
        "tests/test_phase15b_action_integration.py",
        "tests/test_phase15b_visual_foundation.py",
        "tests/test_phase15b_visual_integration.py",
        "tests/test_phase15b_release_contract.py",
        "tests/test_validate_phase15b.py",
        "tests/test_phase15b_release_packaging.py",
    ]
    expected_artifacts = {
        "source_archive": SOURCE_ARCHIVE_NAME,
        "wheel": WHEEL_NAME,
        "handoff": HANDOFF_NAME,
        "package_report": PACKAGE_REPORT_NAME,
        "checksums_json": CHECKSUMS_JSON_NAME,
        "checksums_text": CHECKSUMS_TEXT_NAME,
        "validation_report": VALIDATION_REPORT_NAME,
        "release_tree_authentication": RELEASE_FINGERPRINT.as_posix(),
    }
    expected_platform = {
        "current_host_supporting_evidence": True,
        "visible_pyqt": False,
        "visible_windows_11": False,
        "visible_linux_desktop": False,
        "display_scaling_matrix": False,
        "assistive_technology": False,
        "phase_15d_required": True,
    }
    expected_non_goals = [
        "new transpiler semantics or converter-contract changes",
        "compiler, linker, runner, debugger, terminal, toolchain, plugin, or external command integration",
        "project explorer, recursive scan, host import or package discovery",
        "generated-C editing",
        "Phase 15C wider IDE workspace",
        "Phase 15D distribution and visible platform claims",
    ]
    if (
        manifest.get("settings_schema_version") != 1
        or manifest.get("opened_on") != "2026-07-26"
        or manifest.get("roadmap_revision")
        != "3.1-plus-3.2-and-3.3-addenda"
        or manifest.get("predecessor") != expected_predecessor
        or manifest.get("accepted_scope") != expected_scope
        or manifest.get("required_files") != expected_required_files
        or manifest.get("release_artifacts") != expected_artifacts
        or manifest.get("platform_evidence") != expected_platform
        or manifest.get("non_goals") != expected_non_goals
    ):
        raise ReleaseBuildError(
            "Phase 15B transition manifest evidence is not exact"
        )
    promotion = manifest.get("promotion")
    required_true = (
        "phase_15b_implemented",
        "phase_15b_validated",
        "phase_15b_promoted",
        "phase_15b_sealed",
        "release_fingerprint_assigned",
        "packaging_validated",
    )
    required_false = (
        "c_toolchain_invoked",
        "generated_c_compiled",
        "generated_c_linked",
        "generated_c_loaded",
        "generated_c_executed",
    )
    if (
        not isinstance(promotion, dict)
        or set(promotion) != set(required_true) | set(required_false)
        or any(promotion.get(key) is not True for key in required_true)
        or any(promotion.get(key) is not False for key in required_false)
        or manifest.get("phase_15c") != {"status": "not-opened"}
        or manifest.get("phase_15d") != {"status": "not-opened"}
    ):
        raise ReleaseBuildError(
            "Phase 15B transition promotion flags are not exact"
        )


def _validate_project_configuration(
    configuration: object,
    files: Mapping[str, bytes],
) -> dict[str, object]:
    if configuration != EXPECTED_PROJECT_CONFIGURATION:
        raise ReleaseBuildError(
            "pyproject build and package configuration is not exact"
        )
    forbidden_build_files = sorted(
        name for name in ("setup.py", "setup.cfg") if name in files
    )
    if forbidden_build_files:
        raise ReleaseBuildError(
            "release tree contains an undeclared executable build file"
        )
    return {
        "build_backend": "setuptools.build_meta",
        "build_requirements": ["setuptools==82.0.1"],
        "project_name": "pycforge",
        "requires_python": ">=3.11",
        "console_scripts": dict(EXPECTED_CONSOLE_SCRIPTS),
        "workspace_extra": ["PyQt5>=5.15,<6"],
        "undeclared_build_files": 0,
        "exact": True,
    }


def _build_environment_evidence() -> dict[str, object]:
    packages: dict[str, str | None] = {}
    for name in ("pip", "setuptools", "wheel"):
        try:
            packages[name] = package_version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "python": sys.version.split()[0],
        "implementation": sys.implementation.name,
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "packages": packages,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "python_hash_seed": "0",
        "timezone": "UTC",
    }


def _validate_build_environment() -> dict[str, object]:
    evidence = _build_environment_evidence()
    exact = {
        "python": evidence["python"],
        "implementation": evidence["implementation"],
        "zlib": evidence["zlib"],
        "packages": evidence["packages"],
    }
    if exact != EXPECTED_BUILD_ENVIRONMENT:
        raise ReleaseBuildError(
            "release build environment does not match the pinned toolchain"
        )
    return evidence


def _validate_tree_records(
    root: Path, files: Mapping[str, bytes], tree_hash: str, tree_count: int
) -> dict[str, object]:
    vocabulary = scan_file_map(files)
    assert_clean_scan(vocabulary, label="release file map")
    try:
        project = tomllib.loads(files["pyproject.toml"].decode("utf-8"))
    except (
        KeyError,
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
    ) as exc:
        raise ReleaseBuildError(
            f"cannot parse snapshotted pyproject configuration: {exc}"
        ) from exc
    project_configuration = _validate_project_configuration(project, files)
    for name in (
        HANDOFF_NAME,
        INTERNAL_VALIDATION_REPORT,
        TRANSITION_MANIFEST.as_posix(),
    ):
        if name not in files:
            raise ReleaseBuildError(f"release tree omits {name}")
    validation = strict_json_loads(
        files[INTERNAL_VALIDATION_REPORT],
        label="internal validation report",
        canonical=True,
    )
    _validate_promotion_report(
        validation,
        candidate_files=files,
        candidate_root=root,
    )
    manifest = strict_json_loads(
        files[TRANSITION_MANIFEST.as_posix()],
        label="Phase 15B transition manifest",
        canonical=False,
    )
    _validate_transition_manifest(manifest)
    fingerprint = strict_json_loads(
        files.get(RELEASE_FINGERPRINT.as_posix(), b"{}"),
        label="release fingerprint",
        canonical=True,
    )
    expected = {
        "algorithm": "sha256",
        "domain": FINGERPRINT_DOMAIN,
        "file_count": tree_count,
        "scope_status": "sealed",
        "status": "promoted",
        "value": tree_hash,
    }
    if (
        not isinstance(fingerprint, dict)
        or any(
            fingerprint.get(key) != value
            for key, value in expected.items()
        )
    ):
        raise ReleaseBuildError("release fingerprint is absent or does not match")
    converter_prefix = "pycforge/converter/"
    converter_map = {
        name.removeprefix(converter_prefix): payload
        for name, payload in files.items()
        if name.startswith(converter_prefix)
    }
    if not converter_map:
        raise ReleaseBuildError("converter subtree is absent from the snapshot")
    converter_hash = hash_file_map(
        converter_map,
        domain=CONVERTER_CUSTODY_DOMAIN,
    )
    converter_files = len(converter_map)
    if converter_hash != CONVERTER_SUBTREE_SHA256:
        raise ReleaseBuildError(
            f"converter subtree changed: {converter_hash}"
        )
    return {
        "fingerprint": fingerprint,
        "validation": validation,
        "manifest": manifest,
        "project_configuration": project_configuration,
        "converter_subtree_sha256": converter_hash,
        "converter_subtree_files": converter_files,
        "vocabulary_custody": vocabulary.to_report(),
    }


def build_release(root: Path, output_directory: Path) -> dict[str, object]:
    source_root = root.resolve()
    output = output_directory.resolve()
    try:
        output.relative_to(source_root)
    except ValueError:
        pass
    else:
        raise ReleaseBuildError("release output must be outside the source tree")
    if output.exists():
        raise ReleaseBuildError("release output directory must be fresh")
    build_environment = _validate_build_environment()
    files = release_file_map(source_root)
    unhashed = dict(files)
    unhashed.pop(RELEASE_FINGERPRINT.as_posix(), None)
    tree_hash = hash_file_map(unhashed, domain=FINGERPRINT_DOMAIN)
    records = _validate_tree_records(source_root, files, tree_hash, len(unhashed))

    with tempfile.TemporaryDirectory(prefix="pycforge-phase15b-build-") as name:
        work = Path(name)
        wheel_one = _build_wheel(files, work, 1)
        wheel_two = _build_wheel(files, work, 2)
        wheel_bytes = wheel_one.read_bytes()
        if wheel_bytes != wheel_two.read_bytes():
            raise ReleaseBuildError("fixed-epoch wheel builds differ")
        sealed_wheel_directory = work / "sealed-wheel"
        sealed_wheel_directory.mkdir()
        sealed_wheel = sealed_wheel_directory / WHEEL_NAME
        _write(sealed_wheel, wheel_bytes)
        expected_package_files = {
            name: payload
            for name, payload in files.items()
            if name.startswith("pycforge/")
            and (
                name.endswith(".py")
                or (
                    name.startswith("pycforge/ide/resources/icons/")
                    and name.endswith(".svg")
                )
            )
        }
        wheel_inspection = inspect_wheel(
            sealed_wheel,
            expected_package_files=expected_package_files,
        )
        source_one = normalized_source_archive_bytes(files)
        source_two = normalized_source_archive_bytes(
            dict(reversed(tuple(files.items())))
        )
        if source_one != source_two:
            raise ReleaseBuildError("normalized source archive builds differ")
        source_inspection = inspect_source_archive(source_one, files)
        source_vocabulary = scan_source_archive_bytes(source_one)
        assert_clean_scan(source_vocabulary, label="source archive")
        source_inspection["vocabulary_custody"] = (
            source_vocabulary.to_report()
        )
        smokes = _package_smokes(sealed_wheel, source_one, work)
        if sealed_wheel.read_bytes() != wheel_bytes:
            raise ReleaseBuildError(
                "inspected wheel changed before release publication"
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".pycforge-phase15b-stage-",
            dir=output.parent,
        ) as stage_name:
            stage = Path(stage_name)
            _write(stage / WHEEL_NAME, wheel_bytes)
            _write(stage / SOURCE_ARCHIVE_NAME, source_one)
            _write(stage / HANDOFF_NAME, files[HANDOFF_NAME])
            _write(
                stage / VALIDATION_REPORT_NAME,
                files[INTERNAL_VALIDATION_REPORT],
            )

            core = [
                _artifact(stage / SOURCE_ARCHIVE_NAME),
                _artifact(stage / WHEEL_NAME),
                _artifact(stage / HANDOFF_NAME),
                _artifact(stage / VALIDATION_REPORT_NAME),
            ]
            core_vocabulary = scan_named_bytes(
                (path.name, path.read_bytes())
                for path in (
                    stage / SOURCE_ARCHIVE_NAME,
                    stage / WHEEL_NAME,
                    stage / HANDOFF_NAME,
                    stage / VALIDATION_REPORT_NAME,
                )
            )
            assert_clean_scan(
                core_vocabulary,
                label="core release artifacts",
            )
            report = {
                "schema": "pycforge.phase15b-release-report/0.15.1",
                "phase": "15B",
                "release_version": RELEASE_VERSION,
                "converter_contract_version": CONVERTER_CONTRACT_VERSION,
                "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
                "worker_protocol_version": WORKER_PROTOCOL_VERSION,
                "action_registry_version": ACTION_REGISTRY_VERSION,
                "visual_system_version": VISUAL_SYSTEM_VERSION,
                "release_tree": {
                    "algorithm": "sha256",
                    "domain": FINGERPRINT_DOMAIN,
                    "files": len(unhashed),
                    "self_excluded": RELEASE_FINGERPRINT.as_posix(),
                    "sha256": tree_hash,
                },
                "custody": records,
                "wheel": {
                    **_artifact(stage / WHEEL_NAME),
                    "fixed_epoch_builds_compared": 2,
                    "byte_identical": True,
                    "inspection": wheel_inspection,
                },
                "source_archive": {
                    **_artifact(stage / SOURCE_ARCHIVE_NAME),
                    "archive_root": SOURCE_ARCHIVE_ROOT,
                    "normalized_builds_compared": 2,
                    "byte_identical": True,
                    "inspection": source_inspection,
                },
                "smokes": smokes,
                "build_environment": build_environment,
                "vocabulary_custody": {
                    "core_artifacts": core_vocabulary.to_report(),
                    "release_tree": records["vocabulary_custody"],
                    "source_archive": (
                        source_inspection["vocabulary_custody"]
                    ),
                    "wheel": wheel_inspection["vocabulary_custody"],
                },
                "safety": {
                    "python_to_c_source_transpilation_only": True,
                    "c_toolchain_invoked": False,
                    "generated_c_compiled_or_executed": False,
                },
                "passed": True,
            }
            _write(
                stage / PACKAGE_REPORT_NAME,
                canonical_json_bytes(report),
            )
            core.append(_artifact(stage / PACKAGE_REPORT_NAME))
            checksums = {
                "schema": "pycforge.release-checksums/1",
                "algorithm": "sha256",
                "phase": "15B",
                "release_version": RELEASE_VERSION,
                "artifacts": sorted(
                    core,
                    key=lambda item: str(item["filename"]),
                ),
            }
            _write(
                stage / CHECKSUMS_JSON_NAME,
                canonical_json_bytes(checksums),
            )
            text_records = core + [
                _artifact(stage / CHECKSUMS_JSON_NAME)
            ]
            checksum_text = "".join(
                f"{item['sha256']}  {item['filename']}\n"
                for item in sorted(
                    text_records,
                    key=lambda item: str(item["filename"]),
                )
            ).encode("utf-8")
            _write(stage / CHECKSUMS_TEXT_NAME, checksum_text)
            final_vocabulary = scan_named_bytes(
                (path.name, path.read_bytes())
                for path in sorted(
                    stage.iterdir(),
                    key=lambda value: value.name,
                )
                if path.is_file()
            )
            assert_clean_scan(
                final_vocabulary,
                label="complete release artifacts",
            )
            result = {
                **report,
                "artifacts": [
                    _artifact(stage / artifact_name)
                    for artifact_name in (
                        SOURCE_ARCHIVE_NAME,
                        WHEEL_NAME,
                        HANDOFF_NAME,
                        PACKAGE_REPORT_NAME,
                        CHECKSUMS_JSON_NAME,
                        CHECKSUMS_TEXT_NAME,
                        VALIDATION_REPORT_NAME,
                    )
                ],
                "complete_artifact_vocabulary_custody": (
                    final_vocabulary.to_report()
                ),
                "output_directory": str(output),
            }
            _publish_release_directory(stage, output)
            return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic PyCForge Phase 15B source-only artifacts."
    )
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_release(args.root, args.output_directory)
    except ReleaseBuildError as exc:
        print(
            json.dumps(
                {
                    "schema": "pycforge.phase15b-package-build-error/1",
                    "passed": False,
                    "error": str(exc),
                    "c_toolchain_invoked": False,
                    "generated_c_compiled_or_executed": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
