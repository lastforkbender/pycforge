"""Build the deterministic, source-only PyCForge Phase 15A release.

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
RELEASE_VERSION = "0.15.0"
CONVERTER_CONTRACT_VERSION = "0.14.3"
WORKSPACE_CONTRACT_VERSION = "pycforge-workspace/0.3"
WORKER_PROTOCOL_VERSION = "pycforge.worker-protocol/0.1"
SOURCE_DATE_EPOCH = 1_700_000_000
SOURCE_ARCHIVE_NAME = "pycforge_phase_15a_v0_15_0.tar.gz"
SOURCE_ARCHIVE_ROOT = "pycforge_phase_15a_v0_15_0"
WHEEL_NAME = "pycforge-0.15.0-py3-none-any.whl"
HANDOFF_NAME = "PyCForge_Phase_15A_v0_15_0_Project_Handoff.txt"
PACKAGE_REPORT_NAME = "PyCForge_Phase_15A_v0_15_0_Package_Report.json"
CHECKSUMS_JSON_NAME = "PyCForge_Phase_15A_v0_15_0_Checksums.json"
CHECKSUMS_TEXT_NAME = "PyCForge_Phase_15A_v0_15_0_Checksums.txt"
VALIDATION_REPORT_NAME = "PyCForge_Phase_15A_v0_15_0_Validation_Report.json"
INTERNAL_VALIDATION_REPORT = "evidence/phase_15a/validation_report.json"
RELEASE_FINGERPRINT = PurePosixPath(
    "transition/phase_15a/release_fingerprint.json"
)
FINGERPRINT_DOMAIN = "pycforge-phase15a-release-tree-v1"
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
NATIVE_SUFFIXES = frozenset(
    {".a", ".dll", ".dylib", ".exe", ".lib", ".o", ".obj", ".pyd", ".so"}
)
EXPECTED_CONSOLE_SCRIPTS = {
    "pycforge": "pycforge.laboratory.cli:main",
    "pycforge-workspace": "pycforge.ide.qt:run",
}
REQUIRED_WHEEL_MEMBERS = frozenset(
    {
        "pycforge/__init__.py",
        "pycforge/_version.py",
        "pycforge/converter/facade.py",
        "pycforge/ide/__init__.py",
        "pycforge/ide/controller.py",
        "pycforge/ide/controller_conversion.py",
        "pycforge/ide/controller_io.py",
        "pycforge/ide/editor.py",
        "pycforge/ide/editor_lexical.py",
        "pycforge/ide/editor_sidebars.py",
        "pycforge/ide/editor_syntax.py",
        "pycforge/ide/find_replace.py",
        "pycforge/ide/io_service.py",
        "pycforge/ide/positions.py",
        "pycforge/ide/process_worker.py",
        "pycforge/ide/qt.py",
        "pycforge/ide/qt_close.py",
        "pycforge/ide/qt_contract.py",
        "pycforge/ide/qt_documents.py",
        "pycforge/ide/qt_projection.py",
        "pycforge/ide/qt_shell.py",
        "pycforge/ide/qt_state.py",
        "pycforge/ide/revisions.py",
        "pycforge/ide/search_service.py",
        "pycforge/ide/supervisor.py",
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
        ).encode("utf-8")
        + b"\n"
    )


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


def release_file_map(root: Path) -> dict[str, bytes]:
    base = root.resolve()
    if not base.is_dir():
        raise ReleaseBuildError(f"release root is not a directory: {base}")
    files: dict[str, bytes] = {}
    for directory, directory_names, file_names in os.walk(
        base, topdown=True, followlinks=False
    ):
        current = Path(directory)
        retained: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = safe_relative_path(candidate.relative_to(base).as_posix())
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ReleaseBuildError(f"release tree contains symlink: {relative}")
            if _is_ephemeral(relative):
                continue
            if not stat.S_ISDIR(mode):
                raise ReleaseBuildError(
                    f"release tree contains special directory: {relative}"
                )
            retained.append(name)
        directory_names[:] = retained
        for name in sorted(file_names):
            candidate = current / name
            relative = safe_relative_path(candidate.relative_to(base).as_posix())
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ReleaseBuildError(
                    f"release tree contains non-regular file: {relative}"
                )
            if _is_ephemeral(relative):
                continue
            files[relative.as_posix()] = candidate.read_bytes()
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
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
        members = tar.getmembers()
        for member in members:
            path = safe_relative_path(member.name)
            if path.parts[0] != SOURCE_ARCHIVE_ROOT or not member.isfile():
                raise ReleaseBuildError(
                    f"source archive member is not a regular rooted file: {path}"
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


def inspect_wheel(path: Path) -> dict[str, object]:
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
    if len(svg) != 17:
        raise ReleaseBuildError(f"wheel contains {len(svg)} SVG assets, expected 17")

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
    if metadata.get("Name", "").lower() != "pycforge":
        raise ReleaseBuildError("wheel project name is not pycforge")
    if metadata.get("Version") != RELEASE_VERSION:
        raise ReleaseBuildError("wheel version is not " + RELEASE_VERSION)
    if wheel_metadata.get("Root-Is-Purelib", "").lower() != "true":
        raise ReleaseBuildError("wheel is not pure Python")
    if "py3-none-any" not in wheel_metadata.get_all("Tag", []):
        raise ReleaseBuildError("wheel tag is not py3-none-any")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(members[entry_points_name].decode("utf-8"))
    scripts = dict(parser.items("console_scripts"))
    if scripts != EXPECTED_CONSOLE_SCRIPTS:
        raise ReleaseBuildError("wheel console scripts do not match")
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
        "console_scripts": dict(sorted(scripts.items())),
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
from pycforge.ide import WORKSPACE_CONTRACT_VERSION
from pycforge.ide.supervisor import ProcessConversionSupervisor
from pycforge.ide.worker_protocol import (
    PROTOCOL_SCHEMA,
    bundle_fingerprint_for_request,
)


def main():
    assert __version__ == "0.15.0"
    assert CONVERTER_CONTRACT_VERSION == "0.14.3"
    assert WORKSPACE_CONTRACT_VERSION == "pycforge-workspace/0.3"
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
    source_script = source_root / "_phase15a_package_smoke.py"
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


def _validate_tree_records(
    root: Path, files: Mapping[str, bytes], tree_hash: str, tree_count: int
) -> dict[str, object]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"]["version"] != RELEASE_VERSION:
        raise ReleaseBuildError("pyproject release version does not match")
    for name in (HANDOFF_NAME, INTERNAL_VALIDATION_REPORT):
        if name not in files:
            raise ReleaseBuildError(f"release tree omits {name}")
    validation = json.loads(files[INTERNAL_VALIDATION_REPORT])
    if (
        validation.get("schema") != "pycforge.phase15a-validation-report/1"
        or not validation.get("passed")
    ):
        raise ReleaseBuildError("internal Phase 15A validation is not passing")
    fingerprint = json.loads(files.get(RELEASE_FINGERPRINT.as_posix(), b"{}"))
    expected = {
        "algorithm": "sha256",
        "domain": FINGERPRINT_DOMAIN,
        "file_count": tree_count,
        "scope_status": "sealed",
        "status": "promoted",
        "value": tree_hash,
    }
    if any(fingerprint.get(key) != value for key, value in expected.items()):
        raise ReleaseBuildError("release fingerprint is absent or does not match")
    converter_hash, converter_files = release_subtree_hash(
        root,
        "pycforge/converter",
        domain=CONVERTER_CUSTODY_DOMAIN,
    )
    if converter_hash != CONVERTER_SUBTREE_SHA256:
        raise ReleaseBuildError(
            f"converter subtree changed: {converter_hash}"
        )
    return {
        "fingerprint": fingerprint,
        "validation": validation,
        "converter_subtree_sha256": converter_hash,
        "converter_subtree_files": converter_files,
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
    files = release_file_map(source_root)
    unhashed = dict(files)
    unhashed.pop(RELEASE_FINGERPRINT.as_posix(), None)
    tree_hash = hash_file_map(unhashed, domain=FINGERPRINT_DOMAIN)
    records = _validate_tree_records(source_root, files, tree_hash, len(unhashed))

    with tempfile.TemporaryDirectory(prefix="pycforge-phase15a-build-") as name:
        work = Path(name)
        wheel_one = _build_wheel(files, work, 1)
        wheel_two = _build_wheel(files, work, 2)
        wheel_bytes = wheel_one.read_bytes()
        if wheel_bytes != wheel_two.read_bytes():
            raise ReleaseBuildError("fixed-epoch wheel builds differ")
        wheel_inspection = inspect_wheel(wheel_one)
        source_one = normalized_source_archive_bytes(files)
        source_two = normalized_source_archive_bytes(
            dict(reversed(tuple(files.items())))
        )
        if source_one != source_two:
            raise ReleaseBuildError("normalized source archive builds differ")
        source_inspection = inspect_source_archive(source_one, files)
        smokes = _package_smokes(wheel_one, source_one, work)

        output.mkdir(parents=True)
        _write(output / WHEEL_NAME, wheel_bytes)
        _write(output / SOURCE_ARCHIVE_NAME, source_one)
        _write(output / HANDOFF_NAME, files[HANDOFF_NAME])
        _write(
            output / VALIDATION_REPORT_NAME,
            files[INTERNAL_VALIDATION_REPORT],
        )

    core = [
        _artifact(output / SOURCE_ARCHIVE_NAME),
        _artifact(output / WHEEL_NAME),
        _artifact(output / HANDOFF_NAME),
        _artifact(output / VALIDATION_REPORT_NAME),
    ]
    report = {
        "schema": "pycforge.phase15a-release-report/0.15.0",
        "phase": "15A",
        "release_version": RELEASE_VERSION,
        "converter_contract_version": CONVERTER_CONTRACT_VERSION,
        "workspace_contract_version": WORKSPACE_CONTRACT_VERSION,
        "worker_protocol_version": WORKER_PROTOCOL_VERSION,
        "release_tree": {
            "algorithm": "sha256",
            "domain": FINGERPRINT_DOMAIN,
            "files": len(unhashed),
            "self_excluded": RELEASE_FINGERPRINT.as_posix(),
            "sha256": tree_hash,
        },
        "custody": records,
        "wheel": {
            **_artifact(output / WHEEL_NAME),
            "fixed_epoch_builds_compared": 2,
            "byte_identical": True,
            "inspection": wheel_inspection,
        },
        "source_archive": {
            **_artifact(output / SOURCE_ARCHIVE_NAME),
            "archive_root": SOURCE_ARCHIVE_ROOT,
            "normalized_builds_compared": 2,
            "byte_identical": True,
            "inspection": source_inspection,
        },
        "smokes": smokes,
        "safety": {
            "python_to_c_source_transpilation_only": True,
            "c_toolchain_invoked": False,
            "generated_c_compiled_or_executed": False,
        },
        "passed": True,
    }
    _write(output / PACKAGE_REPORT_NAME, canonical_json_bytes(report))
    core.append(_artifact(output / PACKAGE_REPORT_NAME))
    checksums = {
        "schema": "pycforge.release-checksums/1",
        "algorithm": "sha256",
        "phase": "15A",
        "release_version": RELEASE_VERSION,
        "artifacts": sorted(core, key=lambda item: str(item["filename"])),
    }
    _write(output / CHECKSUMS_JSON_NAME, canonical_json_bytes(checksums))
    text_records = core + [_artifact(output / CHECKSUMS_JSON_NAME)]
    checksum_text = "".join(
        f"{item['sha256']}  {item['filename']}\n"
        for item in sorted(text_records, key=lambda item: str(item["filename"]))
    ).encode("utf-8")
    _write(output / CHECKSUMS_TEXT_NAME, checksum_text)
    return {
        **report,
        "artifacts": [
            _artifact(output / name)
            for name in (
                SOURCE_ARCHIVE_NAME,
                WHEEL_NAME,
                HANDOFF_NAME,
                PACKAGE_REPORT_NAME,
                CHECKSUMS_JSON_NAME,
                CHECKSUMS_TEXT_NAME,
                VALIDATION_REPORT_NAME,
            )
        ],
        "output_directory": str(output),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic PyCForge Phase 15A source-only artifacts."
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
                    "schema": "pycforge.phase15a-package-build-error/1",
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
