"""Build and inspect the deterministic PyCForge Checkpoint E release.

This is packaging infrastructure only.  It builds Python distribution
artifacts, performs source-to-source conversion smokes, and never invokes a C
compiler, linker, loader, foreign-function interface, or generated-C
executable.

The Checkpoint E distribution advances to 0.14.4 while the deterministic
converter contract remains sealed at 0.14.3.
"""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence
import zipfile
import zlib


ROOT = Path(__file__).resolve().parents[1]

RELEASE_VERSION = "0.14.4"
CONVERTER_CONTRACT_VERSION = "0.14.3"
CHECKPOINT = "E"
SOURCE_DATE_EPOCH = 1_700_000_000

SOURCE_ARCHIVE_NAME = "pycforge_checkpoint_e_v0_14_4.tar.gz"
SOURCE_ARCHIVE_ROOT = "pycforge_checkpoint_e_v0_14_4"
WHEEL_NAME = "pycforge-0.14.4-py3-none-any.whl"
PACKAGE_REPORT_NAME = "PyCForge_Checkpoint_E_v0_14_4_Package_Report.json"
CHECKSUMS_NAME = "PyCForge_Checkpoint_E_v0_14_4_Checksums.json"
HANDOFF_NAME = "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt"

RELEASE_FINGERPRINT = PurePosixPath(
    "transition/checkpoint_e/release_fingerprint.json"
)
FINGERPRINT_DOMAIN = "pycforge-checkpoint-e-release-tree-v1"
TREE_HASH_ALGORITHM = "sha256"
GZIP_MTIME = 0
GZIP_LEVEL = 6

NATIVE_SUFFIXES = frozenset(
    {".dll", ".dylib", ".exe", ".pyd", ".so", ".a", ".lib", ".o", ".obj"}
)
EPHEMERAL_DIRECTORY_NAMES = frozenset(
    {
        ".eggs",
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
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
EPHEMERAL_FILE_NAMES = frozenset(
    {
        ".coverage",
        PACKAGE_REPORT_NAME,
        CHECKSUMS_NAME,
        SOURCE_ARCHIVE_NAME,
        WHEEL_NAME,
    }
)
EPHEMERAL_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".tar.gz",
    ".tgz",
    ".whl",
    ".zip",
)

REQUIRED_WHEEL_MEMBERS = frozenset(
    {
        "pycforge/__init__.py",
        "pycforge/_version.py",
        "pycforge/__main__.py",
        "pycforge/converter/facade.py",
        "pycforge/converter/contracts/versions.py",
        "pycforge/ide/__init__.py",
        "pycforge/ide/__main__.py",
        "pycforge/ide/controller.py",
        "pycforge/ide/editor.py",
        "pycforge/ide/find_replace.py",
        "pycforge/ide/model.py",
        "pycforge/ide/panels.py",
        "pycforge/ide/qt.py",
        "pycforge/ide/theme.py",
        "pycforge/laboratory/checkpoint_e.py",
        "pycforge/laboratory/cli.py",
    }
)
EXPECTED_SVG_ASSET_NAMES = frozenset(
    {
        "pycforge/ide/resources/icons/add-document.svg",
        "pycforge/ide/resources/icons/cancel.svg",
        "pycforge/ide/resources/icons/close.svg",
        "pycforge/ide/resources/icons/convert.svg",
        "pycforge/ide/resources/icons/export.svg",
        "pycforge/ide/resources/icons/find.svg",
        "pycforge/ide/resources/icons/link-c.svg",
        "pycforge/ide/resources/icons/move-down.svg",
        "pycforge/ide/resources/icons/move-up.svg",
        "pycforge/ide/resources/icons/next.svg",
        "pycforge/ide/resources/icons/open.svg",
        "pycforge/ide/resources/icons/previous.svg",
        "pycforge/ide/resources/icons/remove-document.svg",
        "pycforge/ide/resources/icons/replace.svg",
        "pycforge/ide/resources/icons/save.svg",
        "pycforge/ide/resources/icons/settings.svg",
        "pycforge/ide/resources/icons/show-c.svg",
    }
)
EXPECTED_CONSOLE_SCRIPTS = {
    "pycforge": "pycforge.laboratory.cli:main",
    "pycforge-workspace": "pycforge.ide.qt:run",
}
PROMOTION_EVIDENCE_FILES = frozenset(
    {
        "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt",
        "transition/checkpoint_e/manifest.json",
        "transition/checkpoint_e/release_fingerprint.json",
        "evidence/checkpoint_e/full_subset_validation.json",
        "evidence/checkpoint_e/release_report.json",
    }
)

GOLDEN_SOURCE = """\
def add(a: int, /, b: int, *, scale: int) -> int:
    return (a + b) * scale

def run() -> int:
    return add(1, b=2, scale=3)
"""
GOLDEN_OUTPUT_FINGERPRINT = (
    "685607a0916efeeef5300966bc30e5a9c5b9ad21c3929b7b681db2c8fe050418"
)
GOLDEN_C_SHA256 = (
    "5c85b6ca4b6ff59f2c6c073df4967db17ef64a5c8d1eda926e528cc45c20eb84"
)

TOOLCHAIN_INVOKED = False
GENERATED_C_COMPILED_OR_EXECUTED = False


class ReleaseBuildError(RuntimeError):
    """Raised when a release invariant cannot be satisfied."""


def canonical_json_bytes(value: object) -> bytes:
    """Serialize machine evidence with stable ordering and one final newline."""

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
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative_path(value: str | PurePosixPath) -> PurePosixPath:
    """Return a normalized, archive-safe relative POSIX path."""

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


def is_release_ephemera(relative: str | PurePosixPath) -> bool:
    """Return whether a relative path is forbidden build/release ephemera."""

    path = safe_relative_path(relative)
    if any(part in EPHEMERAL_DIRECTORY_NAMES for part in path.parts):
        return True
    # The canonical pycforge.egg-info tree is retained as explicit source
    # metadata custody because extracted-source validation reads PKG-INFO.
    # Wheel-local .dist-info trees are build outputs and remain excluded.
    if any(part.endswith(".dist-info") for part in path.parts):
        return True
    if path.name in EPHEMERAL_FILE_NAMES:
        return True
    return path.name.endswith(EPHEMERAL_FILE_SUFFIXES)


def release_file_map(root: Path) -> dict[str, bytes]:
    """Read the exact regular-file release domain from ``root``.

    Symlinks and special files fail closed.  Ephemeral directories and files
    are excluded by name; all retained paths are normalized POSIX paths.
    """

    base = Path(root).resolve()
    if not base.is_dir():
        raise ReleaseBuildError(f"release root is not a directory: {base}")

    files: dict[str, bytes] = {}
    for directory, directory_names, file_names in os.walk(
        base,
        topdown=True,
        followlinks=False,
    ):
        current = Path(directory)
        retained_directories: list[str] = []
        for name in sorted(directory_names):
            candidate = current / name
            relative = safe_relative_path(
                PurePosixPath(candidate.relative_to(base).as_posix())
            )
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise ReleaseBuildError(
                    f"cannot inspect release directory {relative}: {exc}"
                ) from exc
            if stat.S_ISLNK(mode):
                raise ReleaseBuildError(
                    f"release tree contains a symbolic link: {relative}"
                )
            if not stat.S_ISDIR(mode):
                raise ReleaseBuildError(
                    f"release tree contains a non-directory entry: {relative}"
                )
            if not is_release_ephemera(relative):
                retained_directories.append(name)
        directory_names[:] = retained_directories

        for name in sorted(file_names):
            candidate = current / name
            relative = safe_relative_path(
                PurePosixPath(candidate.relative_to(base).as_posix())
            )
            try:
                mode = candidate.lstat().st_mode
            except OSError as exc:
                raise ReleaseBuildError(
                    f"cannot inspect release file {relative}: {exc}"
                ) from exc
            if stat.S_ISLNK(mode):
                raise ReleaseBuildError(
                    f"release tree contains a symbolic link: {relative}"
                )
            if not stat.S_ISREG(mode):
                raise ReleaseBuildError(
                    f"release tree contains a non-regular file: {relative}"
                )
            if not is_release_ephemera(relative):
                key = relative.as_posix()
                if key in files:
                    raise ReleaseBuildError(
                        f"duplicate normalized release path: {key}"
                    )
                files[key] = candidate.read_bytes()

    if not files:
        raise ReleaseBuildError("release tree contains no distributable files")
    return dict(sorted(files.items()))


def hash_file_map(
    files: Mapping[str, bytes],
    *,
    domain: str | None = None,
) -> str:
    """Hash exact path/content pairs with unambiguous length prefixes."""

    digest = hashlib.sha256()
    if domain is not None:
        domain_bytes = domain.encode("utf-8")
        digest.update(len(domain_bytes).to_bytes(8, "big"))
        digest.update(domain_bytes)
    for name in sorted(files):
        path = safe_relative_path(name).as_posix()
        data = files[name]
        if not isinstance(data, bytes):
            raise ReleaseBuildError(f"release member is not bytes: {path}")
        path_bytes = path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def release_tree_hash(root: Path) -> tuple[str, int]:
    """Hash the release tree while omitting its exact self-reference."""

    files = release_file_map(root)
    files.pop(RELEASE_FINGERPRINT.as_posix(), None)
    return hash_file_map(files, domain=FINGERPRINT_DOMAIN), len(files)


def release_subtree_hash(root: Path, prefix: str) -> tuple[str, int]:
    """Hash one release subtree with names relative to that subtree."""

    safe_prefix = safe_relative_path(prefix)
    marker = safe_prefix.as_posix().rstrip("/") + "/"
    selected = {
        name[len(marker) :]: data
        for name, data in release_file_map(root).items()
        if name.startswith(marker)
    }
    if not selected:
        raise ReleaseBuildError(f"release subtree is absent or empty: {prefix}")
    domain = f"{FINGERPRINT_DOMAIN}:subtree:{safe_prefix.as_posix()}"
    return hash_file_map(selected, domain=domain), len(selected)


def canonical_gzip_bytes(raw_tar: bytes) -> bytes:
    """Return the canonical level-6, mtime-zero, Unix gzip member."""

    compressor = zlib.compressobj(
        level=GZIP_LEVEL,
        method=zlib.DEFLATED,
        wbits=-15,
    )
    body = compressor.compress(raw_tar) + compressor.flush()
    header = (
        b"\x1f\x8b\x08\x00"
        + struct.pack("<I", GZIP_MTIME)
        + b"\x00\x03"
    )
    trailer = struct.pack(
        "<II",
        zlib.crc32(raw_tar) & 0xFFFFFFFF,
        len(raw_tar) & 0xFFFFFFFF,
    )
    return header + body + trailer


def normalized_source_archive_bytes(
    files: Mapping[str, bytes],
    *,
    archive_root: str = SOURCE_ARCHIVE_ROOT,
) -> bytes:
    """Construct a normalized regular-file-only USTAR gzip archive."""

    safe_root = safe_relative_path(archive_root)
    if len(safe_root.parts) != 1:
        raise ReleaseBuildError("source archive root must be one path component")
    if not files:
        raise ReleaseBuildError("cannot archive an empty release file map")

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as package:
        for relative_name in sorted(files):
            relative = safe_relative_path(relative_name)
            if is_release_ephemera(relative):
                raise ReleaseBuildError(
                    f"source archive input contains release ephemera: {relative}"
                )
            data = files[relative_name]
            if not isinstance(data, bytes):
                raise ReleaseBuildError(
                    f"source archive member is not bytes: {relative}"
                )
            member_name = (safe_root / relative).as_posix()
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = SOURCE_DATE_EPOCH
            info.type = tarfile.REGTYPE
            try:
                package.addfile(info, io.BytesIO(data))
            except (OSError, ValueError) as exc:
                raise ReleaseBuildError(
                    f"cannot encode normalized USTAR member {relative}: {exc}"
                ) from exc
    return canonical_gzip_bytes(raw.getvalue())


def _decompress_canonical_gzip(compressed: bytes) -> bytes:
    if len(compressed) < 18:
        raise ReleaseBuildError("source archive is too short to be gzip")
    expected_header = (
        b"\x1f\x8b\x08\x00"
        + struct.pack("<I", GZIP_MTIME)
        + b"\x00\x03"
    )
    if compressed[:10] != expected_header:
        raise ReleaseBuildError("source archive gzip header is not canonical")
    decompressor = zlib.decompressobj(wbits=31)
    try:
        raw_tar = decompressor.decompress(compressed) + decompressor.flush()
    except zlib.error as exc:
        raise ReleaseBuildError(f"source archive gzip is invalid: {exc}") from exc
    if not decompressor.eof:
        raise ReleaseBuildError("source archive gzip member is incomplete")
    if decompressor.unused_data or decompressor.unconsumed_tail:
        raise ReleaseBuildError(
            "source archive has concatenated or trailing gzip data"
        )
    if compressed != canonical_gzip_bytes(raw_tar):
        raise ReleaseBuildError("source archive gzip bytes are not canonical")
    return raw_tar


def inspect_source_archive_bytes(
    compressed: bytes,
    *,
    expected_files: Mapping[str, bytes] | None = None,
    archive_root: str = SOURCE_ARCHIVE_ROOT,
) -> dict[str, object]:
    """Inspect normalized source bytes without extracting any member."""

    safe_root = safe_relative_path(archive_root)
    raw_tar = _decompress_canonical_gzip(compressed)
    if len(raw_tar) < 265 or raw_tar[257:265] != b"ustar\x0000":
        raise ReleaseBuildError("source archive is not normalized USTAR")

    files: dict[str, bytes] = {}
    member_names: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as package:
            members = package.getmembers()
            for member in members:
                name = safe_relative_path(member.name)
                if member.name in member_names:
                    raise ReleaseBuildError(
                        f"source archive has duplicate member: {member.name}"
                    )
                member_names.add(member.name)
                if (
                    len(name.parts) < 2
                    or name.parts[0] != safe_root.as_posix()
                ):
                    raise ReleaseBuildError(
                        f"source archive member has the wrong root: {member.name}"
                    )
                if not member.isfile():
                    raise ReleaseBuildError(
                        "source archive contains a non-regular member: "
                        f"{member.name}"
                    )
                relative = PurePosixPath(*name.parts[1:])
                if is_release_ephemera(relative):
                    raise ReleaseBuildError(
                        "source archive contains forbidden release ephemera: "
                        f"{relative}"
                    )
                if (
                    member.mode != 0o644
                    or member.uid != 0
                    or member.gid != 0
                    or member.uname != ""
                    or member.gname != ""
                    or member.mtime != SOURCE_DATE_EPOCH
                    or bool(member.pax_headers)
                ):
                    raise ReleaseBuildError(
                        "source archive member metadata is not normalized: "
                        f"{member.name}"
                    )
                stream = package.extractfile(member)
                if stream is None:
                    raise ReleaseBuildError(
                        f"source archive member cannot be read: {member.name}"
                    )
                relative_name = relative.as_posix()
                if relative_name in files:
                    raise ReleaseBuildError(
                        "source archive has duplicate normalized member: "
                        f"{relative_name}"
                    )
                files[relative_name] = stream.read()
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseBuildError(f"source archive tar is invalid: {exc}") from exc

    if not files:
        raise ReleaseBuildError("source archive contains no files")
    if expected_files is not None and files != dict(expected_files):
        missing = sorted(set(expected_files) - set(files))
        extra = sorted(set(files) - set(expected_files))
        changed = sorted(
            name
            for name in set(files) & set(expected_files)
            if files[name] != expected_files[name]
        )
        raise ReleaseBuildError(
            "source archive file map mismatch "
            f"(missing={missing}, extra={extra}, changed={changed})"
        )
    return {
        "archive_root": safe_root.as_posix(),
        "member_count": len(member_names),
        "regular_file_count": len(files),
        "normalized_ustar": True,
        "canonical_gzip": True,
        "gzip_level": GZIP_LEVEL,
        "gzip_mtime": GZIP_MTIME,
        "member_mtime": SOURCE_DATE_EPOCH,
        "safe_paths": True,
        "regular_files_only": True,
        "file_map_sha256": hash_file_map(files),
    }


def _wheel_safe_name(name: str) -> str:
    if name.endswith("/"):
        raise ReleaseBuildError(f"wheel contains a directory entry: {name!r}")
    return safe_relative_path(name).as_posix()


def _record_digest(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
    return "sha256=" + encoded.rstrip(b"=").decode("ascii")


def inspect_wheel(
    wheel: Path,
    *,
    expected_assets: Mapping[str, bytes] | None = None,
) -> dict[str, object]:
    """Inspect wheel metadata, RECORD coverage, assets, and native members."""

    path = Path(wheel)
    if path.name != WHEEL_NAME:
        raise ReleaseBuildError(
            f"wheel filename is {path.name!r}, expected {WHEEL_NAME!r}"
        )
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if len(names) != len(set(names)):
                raise ReleaseBuildError("wheel contains duplicate member names")
            safe_names = [_wheel_safe_name(name) for name in names]
            corrupt = package.testzip()
            if corrupt is not None:
                raise ReleaseBuildError(f"wheel ZIP integrity failed at {corrupt}")
            member_bytes = {
                name: package.read(name)
                for name in safe_names
            }
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ReleaseBuildError(f"cannot inspect wheel: {exc}") from exc

    name_set = set(member_bytes)
    missing_required = sorted(REQUIRED_WHEEL_MEMBERS - name_set)
    if missing_required:
        raise ReleaseBuildError(
            "wheel omits required Python members: " + ", ".join(missing_required)
        )

    def one_dist_info(suffix: str) -> str:
        matches = sorted(
            name
            for name in name_set
            if name.endswith(f".dist-info/{suffix}")
        )
        if len(matches) != 1:
            raise ReleaseBuildError(
                f"wheel has {len(matches)} .dist-info/{suffix} members"
            )
        return matches[0]

    metadata_name = one_dist_info("METADATA")
    wheel_metadata_name = one_dist_info("WHEEL")
    entry_points_name = one_dist_info("entry_points.txt")
    record_name = one_dist_info("RECORD")
    try:
        metadata = BytesParser(policy=email_policy).parsebytes(
            member_bytes[metadata_name]
        )
        wheel_metadata = BytesParser(policy=email_policy).parsebytes(
            member_bytes[wheel_metadata_name]
        )
    except (UnicodeError, ValueError) as exc:
        raise ReleaseBuildError(f"wheel metadata is invalid: {exc}") from exc
    if metadata.get("Name", "").lower() != "pycforge":
        raise ReleaseBuildError("wheel METADATA project name is not pycforge")
    if metadata.get("Version") != RELEASE_VERSION:
        raise ReleaseBuildError(
            "wheel METADATA version is not " + RELEASE_VERSION
        )
    if metadata.get("Requires-Python") != ">=3.11":
        raise ReleaseBuildError(
            "wheel METADATA Requires-Python is not exactly >=3.11"
        )
    if wheel_metadata.get("Root-Is-Purelib", "").lower() != "true":
        raise ReleaseBuildError("wheel is not marked as pure Python")
    if "py3-none-any" not in wheel_metadata.get_all("Tag", []):
        raise ReleaseBuildError("wheel omits the py3-none-any compatibility tag")
    try:
        entry_points_text = member_bytes[entry_points_name].decode("utf-8")
        entry_points = configparser.ConfigParser(
            interpolation=None,
            strict=True,
        )
        entry_points.optionxform = str
        entry_points.read_string(entry_points_text)
    except (UnicodeError, configparser.Error) as exc:
        raise ReleaseBuildError(f"wheel entry points are invalid: {exc}") from exc
    if set(entry_points.sections()) != {"console_scripts"}:
        raise ReleaseBuildError(
            "wheel entry points must contain only [console_scripts]"
        )
    actual_console_scripts = dict(entry_points.items("console_scripts"))
    if actual_console_scripts != EXPECTED_CONSOLE_SCRIPTS:
        raise ReleaseBuildError(
            "wheel console scripts do not match the frozen PyCForge entry points"
        )

    try:
        record_text = member_bytes[record_name].decode("utf-8")
        rows = list(csv.reader(io.StringIO(record_text)))
    except (UnicodeError, csv.Error) as exc:
        raise ReleaseBuildError(f"wheel RECORD is invalid: {exc}") from exc
    if any(len(row) != 3 for row in rows):
        raise ReleaseBuildError("wheel RECORD has malformed rows")
    record_names = [row[0] for row in rows]
    if len(record_names) != len(set(record_names)):
        raise ReleaseBuildError("wheel RECORD has duplicate member rows")
    if set(record_names) != name_set:
        raise ReleaseBuildError("wheel RECORD does not cover every member exactly")
    for member, digest, size in rows:
        if member == record_name:
            if digest or size:
                raise ReleaseBuildError("wheel RECORD self-entry is not empty")
            continue
        data = member_bytes[member]
        if digest != _record_digest(data) or size != str(len(data)):
            raise ReleaseBuildError(
                f"wheel RECORD digest or size mismatch: {member}"
            )

    svg_assets = {
        name: data
        for name, data in member_bytes.items()
        if name.startswith("pycforge/ide/resources/icons/")
        and name.endswith(".svg")
    }
    if set(svg_assets) != EXPECTED_SVG_ASSET_NAMES:
        raise ReleaseBuildError(
            "wheel does not contain the exact 17-icon PyCForge asset inventory"
        )
    if expected_assets is not None and svg_assets != dict(expected_assets):
        missing = sorted(set(expected_assets) - set(svg_assets))
        extra = sorted(set(svg_assets) - set(expected_assets))
        changed = sorted(
            name
            for name in set(svg_assets) & set(expected_assets)
            if svg_assets[name] != expected_assets[name]
        )
        raise ReleaseBuildError(
            "wheel SVG asset map mismatch "
            f"(missing={missing}, extra={extra}, changed={changed})"
        )

    native_members = sorted(
        name
        for name in name_set
        if PurePosixPath(name).suffix.lower() in NATIVE_SUFFIXES
    )
    if native_members:
        raise ReleaseBuildError(
            "wheel unexpectedly contains native members: "
            + ", ".join(native_members)
        )
    return {
        "filename": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "zip_members": len(name_set),
        "record_entries": len(rows),
        "metadata_name": metadata.get("Name"),
        "metadata_version": metadata.get("Version"),
        "requires_python": metadata.get("Requires-Python"),
        "root_is_purelib": True,
        "tag": "py3-none-any",
        "console_scripts": dict(sorted(actual_console_scripts.items())),
        "svg_assets": len(svg_assets),
        "svg_asset_names": sorted(svg_assets),
        "native_member_count": len(native_members),
        "record_validated": True,
        "zip_integrity_validated": True,
        "safe_member_paths": True,
    }


def _expected_svg_assets(files: Mapping[str, bytes]) -> dict[str, bytes]:
    assets = {
        name: data
        for name, data in files.items()
        if name.startswith("pycforge/ide/resources/icons/")
        and name.endswith(".svg")
    }
    if set(assets) != EXPECTED_SVG_ASSET_NAMES:
        missing = sorted(EXPECTED_SVG_ASSET_NAMES - set(assets))
        extra = sorted(set(assets) - EXPECTED_SVG_ASSET_NAMES)
        raise ReleaseBuildError(
            "source tree does not contain the exact 17-icon PyCForge asset "
            f"inventory (missing={missing}, extra={extra})"
        )
    return assets


def _verify_project_identity(root: Path) -> dict[str, object]:
    try:
        project = tomllib.loads(
            (Path(root) / "pyproject.toml").read_text(encoding="utf-8")
        )
        version = project["project"]["version"]
        name = project["project"]["name"]
    except (
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        raise ReleaseBuildError(f"cannot read project identity: {exc}") from exc
    if str(name).lower() != "pycforge":
        raise ReleaseBuildError(f"project name is {name!r}, expected 'pycforge'")
    if version != RELEASE_VERSION:
        raise ReleaseBuildError(
            f"project version is {version!r}, expected {RELEASE_VERSION!r}"
        )
    return {"name": name, "version": version}


def _load_release_json(
    files: Mapping[str, bytes],
    name: str,
) -> dict[str, object]:
    raw = files.get(name)
    if raw is None:
        raise ReleaseBuildError(f"release tree omits required evidence: {name}")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"{name} is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseBuildError(f"{name} is not a JSON object")
    return value


def _verify_promotion_evidence(
    files: Mapping[str, bytes],
) -> dict[str, object]:
    """Fail closed unless the tree carries complete promotion evidence."""

    missing = sorted(PROMOTION_EVIDENCE_FILES - set(files))
    if missing:
        raise ReleaseBuildError(
            "release tree omits final promotion evidence: " + ", ".join(missing)
        )

    manifest_name = "transition/checkpoint_e/manifest.json"
    release_report_name = "evidence/checkpoint_e/release_report.json"
    validation_name = "evidence/checkpoint_e/full_subset_validation.json"
    manifest = _load_release_json(files, manifest_name)
    release_report = _load_release_json(files, release_report_name)
    validation = _load_release_json(files, validation_name)

    expected_records = (
        (
            manifest_name,
            manifest,
            "pycforge.checkpoint-e-manifest/0.14.4",
            manifest.get("version"),
        ),
        (
            release_report_name,
            release_report,
            "pycforge.checkpoint-e-release-report/0.14.4",
            release_report.get("release_version"),
        ),
    )
    for name, value, schema, version in expected_records:
        if value.get("schema_version") != schema:
            raise ReleaseBuildError(f"{name} has the wrong schema")
        if version != RELEASE_VERSION:
            raise ReleaseBuildError(f"{name} has the wrong release version")
        if value.get("status") != "promoted":
            raise ReleaseBuildError(f"{name} is not promoted")
        if value.get("scope_status") != "sealed":
            raise ReleaseBuildError(f"{name} is not sealed")

    if validation.get("schema") != "pycforge.checkpoint-e-validation-report/1":
        raise ReleaseBuildError("internal Checkpoint E validation schema is wrong")
    if validation.get("mode") != "promotion":
        raise ReleaseBuildError(
            "internal Checkpoint E validation was not run in promotion mode"
        )
    if validation.get("passed") is not True:
        raise ReleaseBuildError("internal Checkpoint E promotion validation failed")
    if validation.get("promotion_eligible") is not True:
        raise ReleaseBuildError(
            "internal Checkpoint E validation is not promotion-eligible"
        )
    if validation.get("promotion_blockers") != []:
        raise ReleaseBuildError(
            "internal Checkpoint E validation records promotion blockers"
        )

    matrix = validation.get("executable_feature_matrix")
    if not isinstance(matrix, dict):
        raise ReleaseBuildError("internal validation omits executable matrix evidence")
    if (
        matrix.get("passed") is not True
        or matrix.get("coverage_complete") is not True
        or matrix.get("matrix_witness_count") != 69
        or matrix.get("unlisted_default_witness_count") != 1
    ):
        raise ReleaseBuildError(
            "internal executable matrix evidence is not complete at 69 plus default"
        )

    subset = validation.get("full_supported_subset")
    if not isinstance(subset, dict):
        raise ReleaseBuildError("internal validation omits full-subset evidence")
    if (
        subset.get("passed") is not True
        or subset.get("fixed_case_count") != 16
        or subset.get("generated_case_count") != 64
        or subset.get("case_count") != 80
        or subset.get("generated_missing_families") != []
    ):
        raise ReleaseBuildError(
            "internal full-subset evidence is not the exact 16+64 promotion corpus"
        )

    equivalence = validation.get("sealed_predecessor_equivalence")
    if not isinstance(equivalence, dict):
        raise ReleaseBuildError(
            "internal validation omits predecessor-equivalence evidence"
        )
    if (
        equivalence.get("passed") is not True
        or equivalence.get("promotion_eligible") is not True
        or equivalence.get("case_count") != 80
        or equivalence.get("matched_case_count") != 80
        or equivalence.get("mismatched_case_count") != 0
        or equivalence.get("exact_result_json_byte_equivalence") is not True
    ):
        raise ReleaseBuildError(
            "internal predecessor equivalence is not an exact 80/80 pass"
        )

    handoff = files[
        "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt"
    ]
    if len(handoff) < 256:
        raise ReleaseBuildError("Checkpoint E handoff is unexpectedly small")
    return {
        "passed": True,
        "manifest": manifest_name,
        "release_report": release_report_name,
        "validation_report": validation_name,
        "validation_mode": validation.get("mode"),
        "matrix_witnesses": matrix.get("matrix_witness_count"),
        "unlisted_default_witnesses": matrix.get(
            "unlisted_default_witness_count"
        ),
        "promotion_cases": subset.get("case_count"),
        "predecessor_exact_matches": equivalence.get("matched_case_count"),
        "handoff": "PyCForge_Checkpoint_E_v0_14_4_Project_Handoff.txt",
    }


def _fingerprint_state(
    files: Mapping[str, bytes],
    *,
    tree_sha256: str,
    tree_file_count: int | None = None,
    required: bool = False,
) -> dict[str, object]:
    """Validate the assigned late-bound fingerprint for a final build."""

    name = RELEASE_FINGERPRINT.as_posix()
    raw = files.get(name)
    if raw is None:
        if required:
            raise ReleaseBuildError(
                "canonical release requires an assigned release fingerprint"
            )
        return {
            "path": name,
            "present": False,
            "self_excluded_from_tree_hash": True,
            "ordering": (
                "Finalize this self-excluding fingerprint before the canonical "
                "release build."
            ),
        }
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError(f"release fingerprint is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseBuildError("release fingerprint is not a JSON object")
    declared_domain = value.get("domain")
    declared_algorithm = value.get("algorithm")
    declared_value = value.get("value")
    declared_status = value.get("status")
    declared_scope_status = value.get("scope_status")
    declared_file_count = value.get("file_count")
    if declared_domain != FINGERPRINT_DOMAIN:
        raise ReleaseBuildError(
            f"release fingerprint domain is {declared_domain!r}, expected "
            f"{FINGERPRINT_DOMAIN!r}"
        )
    if declared_algorithm != TREE_HASH_ALGORITHM:
        raise ReleaseBuildError("release fingerprint algorithm is not sha256")
    if (
        not isinstance(declared_value, str)
        or re.fullmatch(r"[0-9a-f]{64}", declared_value) is None
    ):
        raise ReleaseBuildError(
            "release fingerprint value is not a lowercase SHA-256 digest"
        )
    if declared_value != tree_sha256:
        raise ReleaseBuildError(
            "release fingerprint value does not match the self-excluding tree hash"
        )
    if declared_status != "promoted" or declared_scope_status != "sealed":
        raise ReleaseBuildError(
            "release fingerprint is not declared promoted and sealed"
        )
    if (
        tree_file_count is not None
        and declared_file_count != tree_file_count
    ):
        raise ReleaseBuildError(
            "release fingerprint file_count does not match the release tree"
        )
    return {
        "path": name,
        "present": True,
        "self_excluded_from_tree_hash": True,
        "declared_domain": declared_domain,
        "declared_algorithm": declared_algorithm,
        "declared_value": declared_value,
        "declared_status": declared_status,
        "declared_scope_status": declared_scope_status,
        "declared_file_count": declared_file_count,
        "declarations_match": True,
    }


def _copy_release_tree(files: Mapping[str, bytes], destination: Path) -> None:
    for relative_name, data in files.items():
        relative = safe_relative_path(relative_name)
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o644)
        os.utime(target, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH))


def _subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "SOURCE_DATE_EPOCH": str(SOURCE_DATE_EPOCH),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TZ": "UTC",
        }
    )
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    return environment


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    label: str,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseBuildError(f"{label} could not run: {exc}") from exc
    if completed.returncode != 0:
        stdout_tail = completed.stdout[-4000:]
        stderr_tail = completed.stderr[-4000:]
        raise ReleaseBuildError(
            f"{label} failed with exit code {completed.returncode}; "
            f"stdout={stdout_tail!r}; stderr={stderr_tail!r}"
        )
    return completed


def _build_wheel_once(
    files: Mapping[str, bytes],
    *,
    work_root: Path,
    build_number: int,
) -> Path:
    source_root = work_root / f"wheel-source-{build_number}"
    output = work_root / f"wheel-output-{build_number}"
    source_root.mkdir()
    output.mkdir()
    _copy_release_tree(files, source_root)
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
            str(source_root),
        ),
        cwd=work_root,
        environment=_subprocess_environment(),
        label=f"fixed-epoch wheel build {build_number}",
    )
    wheels = sorted(output.glob("*.whl"))
    if [item.name for item in wheels] != [WHEEL_NAME]:
        raise ReleaseBuildError(
            f"wheel build {build_number} emitted "
            f"{[item.name for item in wheels]!r}, expected {[WHEEL_NAME]!r}"
        )
    return wheels[0]


def _venv_python(environment_root: Path) -> Path:
    if os.name == "nt":
        return environment_root / "Scripts" / "python.exe"
    return environment_root / "bin" / "python"


def _smoke_script(expected_source_root: Path | None) -> str:
    expected_root = (
        repr(str(expected_source_root.resolve()))
        if expected_source_root is not None
        else "None"
    )
    source_prelude = (
        f"import sys\nsys.path.insert(0, {expected_root})\n"
        if expected_source_root is not None
        else ""
    )
    return f"""\
{source_prelude}
import hashlib
import importlib.util
import json
from pathlib import Path

import pycforge
from pycforge import ConversionRequest, PythonToCConverter
from pycforge.converter.contracts.versions import CONVERTER_CONTRACT_VERSION
from pycforge.ide import QT_AVAILABLE, WORKSPACE_CONTRACT_VERSION

expected_root = {expected_root}
module_path = Path(pycforge.__file__).resolve()
if expected_root is not None:
    module_path.relative_to(Path(expected_root).resolve())
assert pycforge.__version__ == {RELEASE_VERSION!r}
assert CONVERTER_CONTRACT_VERSION == {CONVERTER_CONTRACT_VERSION!r}
assert WORKSPACE_CONTRACT_VERSION == "pycforge-workspace/0.2"
assert importlib.util.find_spec("PyQt5") is None
assert QT_AVAILABLE is False
source = {GOLDEN_SOURCE!r}
result = PythonToCConverter().convert(ConversionRequest.from_source(source))
assert result.status.value == "Converted"
assert result.output_fingerprint.value == {GOLDEN_OUTPUT_FINGERPRINT!r}
assert hashlib.sha256(result.generated_c.encode("utf-8")).hexdigest() == {GOLDEN_C_SHA256!r}
print(json.dumps({{
    "package_version": pycforge.__version__,
    "converter_contract_version": CONVERTER_CONTRACT_VERSION,
    "module_path": str(module_path),
    "pyqt_available": QT_AVAILABLE,
    "status": result.status.value,
    "output_fingerprint": result.output_fingerprint.value,
    "generated_c_sha256": hashlib.sha256(result.generated_c.encode("utf-8")).hexdigest(),
}}, sort_keys=True, separators=(",", ":")))
"""


def _run_python_smokes(
    python: Path,
    *,
    cwd: Path,
    expected_source_root: Path | None,
    label: str,
) -> dict[str, object]:
    environment = _subprocess_environment()
    direct = _run(
        (str(python), "-I", "-c", _smoke_script(expected_source_root)),
        cwd=cwd,
        environment=environment,
        label=f"{label} import and golden conversion smoke",
    )
    try:
        direct_report = json.loads(direct.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseBuildError(
            f"{label} direct smoke emitted invalid JSON: {exc}"
        ) from exc

    def cli_command(arguments: Sequence[str]) -> tuple[str, ...]:
        if expected_source_root is None:
            return (str(python), "-I", "-m", "pycforge", *arguments)
        bootstrap = (
            "import runpy,sys;"
            f"sys.path.insert(0,{str(expected_source_root.resolve())!r});"
            f"sys.argv={['pycforge', *arguments]!r};"
            "runpy.run_module('pycforge',run_name='__main__')"
        )
        return (str(python), "-I", "-c", bootstrap)

    help_result = _run(
        cli_command(("--help",)),
        cwd=cwd,
        environment=environment,
        label=f"{label} headless CLI help smoke",
    )
    if "Headless PyCForge conversion laboratory" not in help_result.stdout:
        raise ReleaseBuildError(f"{label} CLI help omitted the headless identity")

    with tempfile.TemporaryDirectory(prefix="pycforge-cli-source-") as temp_name:
        source_path = Path(temp_name) / "golden.py"
        source_path.write_text(GOLDEN_SOURCE, encoding="utf-8", newline="\n")
        cli_command_line = cli_command(
            ("--format", "json", "convert", str(source_path))
        )
        cli = _run(
            cli_command_line,
            cwd=cwd,
            environment=environment,
            label=f"{label} headless CLI conversion smoke",
        )
        repeated_cli = _run(
            cli_command_line,
            cwd=cwd,
            environment=environment,
            label=f"{label} repeated headless CLI conversion smoke",
        )
    if cli.stdout != repeated_cli.stdout:
        raise ReleaseBuildError(
            f"{label} repeated CLI conversion was not byte-deterministic"
        )
    try:
        cli_report = json.loads(cli.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseBuildError(
            f"{label} CLI conversion emitted invalid JSON: {exc}"
        ) from exc
    if cli_report.get("status") != "Converted":
        raise ReleaseBuildError(f"{label} CLI conversion was not Converted")
    output = cli_report.get("output_fingerprint")
    if (
        not isinstance(output, dict)
        or re.fullmatch(r"[0-9a-f]{64}", str(output.get("value"))) is None
    ):
        raise ReleaseBuildError(
            f"{label} CLI conversion omitted a valid output fingerprint"
        )
    return {
        "passed": True,
        "package_version": direct_report.get("package_version"),
        "converter_contract_version": direct_report.get(
            "converter_contract_version"
        ),
        "module_origin": (
            "source-archive-root"
            if expected_source_root is not None
            else "isolated-wheel-site-packages"
        ),
        "pyqt_available": direct_report.get("pyqt_available"),
        "golden_status": direct_report.get("status"),
        "golden_output_fingerprint": direct_report.get("output_fingerprint"),
        "golden_c_sha256": direct_report.get("generated_c_sha256"),
        "headless_cli_help_passed": True,
        "headless_cli_conversion_passed": True,
        "headless_cli_repeat_byte_identical": True,
        "generated_c_compiled_or_executed": False,
    }


def _extract_validated_source_archive(
    compressed: bytes,
    destination: Path,
) -> Path:
    """Write validated regular members without using tarfile.extractall."""

    inspect_source_archive_bytes(compressed)
    raw_tar = _decompress_canonical_gzip(compressed)
    release_root = destination / SOURCE_ARCHIVE_ROOT
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as package:
        for member in package.getmembers():
            name = safe_relative_path(member.name)
            relative = PurePosixPath(*name.parts[1:])
            target = release_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = package.extractfile(member)
            if stream is None:
                raise ReleaseBuildError(
                    f"validated source member became unreadable: {member.name}"
                )
            target.write_bytes(stream.read())
            target.chmod(0o644)
    return release_root


def _isolated_install_and_smokes(
    wheel: Path,
    source_archive: bytes,
    *,
    work_root: Path,
) -> dict[str, object]:
    environment_root = work_root / "isolated-venv"
    _run(
        (sys.executable, "-m", "venv", str(environment_root)),
        cwd=work_root,
        environment=_subprocess_environment(),
        label="isolated virtual environment creation",
    )
    python = _venv_python(environment_root)
    if not python.is_file():
        raise ReleaseBuildError("isolated virtual environment has no Python")
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
        cwd=work_root,
        environment=_subprocess_environment(),
        label="isolated wheel install",
    )

    wheel_cwd = work_root / "wheel-smoke-cwd"
    wheel_cwd.mkdir()
    wheel_smoke = _run_python_smokes(
        python,
        cwd=wheel_cwd,
        expected_source_root=None,
        label="isolated wheel",
    )

    source_destination = work_root / "source-smoke"
    source_destination.mkdir()
    source_root = _extract_validated_source_archive(
        source_archive,
        source_destination,
    )
    source_smoke = _run_python_smokes(
        python,
        cwd=source_root,
        expected_source_root=source_root,
        label="source archive",
    )
    return {
        "isolated_install_passed": True,
        "dependencies_installed": False,
        "pyqt_installed": False,
        "wheel": wheel_smoke,
        "source_archive": source_smoke,
    }


def _ensure_output_is_outside_source(root: Path, output: Path) -> None:
    source = Path(root).resolve()
    destination = Path(output).resolve()
    try:
        destination.relative_to(source)
    except ValueError:
        return
    raise ReleaseBuildError(
        "release output directory must be outside the source tree"
    )


def _write_output(
    target: Path,
    data: bytes,
    *,
    replace: bool,
) -> None:
    if target.exists() and not replace:
        raise ReleaseBuildError(
            f"release output already exists (use --replace explicitly): {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _artifact_record(path: Path) -> dict[str, object]:
    return {
        "filename": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_release(
    root: Path,
    output_directory: Path,
    *,
    replace: bool = False,
    run_smokes: bool = True,
) -> dict[str, object]:
    """Build canonical artifacts and write external machine-readable evidence."""

    if replace:
        raise ReleaseBuildError(
            "canonical Checkpoint E release publication never replaces outputs"
        )
    if not run_smokes:
        raise ReleaseBuildError(
            "canonical Checkpoint E release requires isolated package smokes"
        )
    source_root = Path(root).resolve()
    output = Path(output_directory).resolve()
    _ensure_output_is_outside_source(source_root, output)
    if output.exists():
        raise ReleaseBuildError(
            "canonical release output directory must be fresh and absent"
        )

    project = _verify_project_identity(source_root)
    files = release_file_map(source_root)
    promotion_evidence = _verify_promotion_evidence(files)
    tree_files = dict(files)
    tree_files.pop(RELEASE_FINGERPRINT.as_posix(), None)
    tree_sha256 = hash_file_map(tree_files, domain=FINGERPRINT_DOMAIN)
    fingerprint = _fingerprint_state(
        files,
        tree_sha256=tree_sha256,
        tree_file_count=len(tree_files),
        required=True,
    )
    subtree_records = {}
    for prefix in (
        "pycforge/converter",
        "pycforge/ide",
        "pycforge/laboratory",
        "schemas",
        "specifications",
    ):
        marker = prefix + "/"
        selected = {
            name[len(marker) :]: data
            for name, data in files.items()
            if name.startswith(marker)
        }
        if selected:
            subtree_records[prefix] = {
                "files": len(selected),
                "sha256": hash_file_map(
                    selected,
                    domain=f"{FINGERPRINT_DOMAIN}:subtree:{prefix}",
                ),
            }

    with tempfile.TemporaryDirectory(prefix="pycforge-checkpoint-e-build-") as temp:
        work_root = Path(temp)
        first_wheel = _build_wheel_once(
            files,
            work_root=work_root,
            build_number=1,
        )
        second_wheel = _build_wheel_once(
            files,
            work_root=work_root,
            build_number=2,
        )
        first_wheel_bytes = first_wheel.read_bytes()
        second_wheel_bytes = second_wheel.read_bytes()
        if first_wheel_bytes != second_wheel_bytes:
            raise ReleaseBuildError(
                "fixed-epoch wheel builds are not byte-identical "
                f"({sha256_bytes(first_wheel_bytes)} != "
                f"{sha256_bytes(second_wheel_bytes)})"
            )
        wheel_inspection = inspect_wheel(
            first_wheel,
            expected_assets=_expected_svg_assets(files),
        )

        first_archive = normalized_source_archive_bytes(files)
        second_archive = normalized_source_archive_bytes(dict(reversed(list(files.items()))))
        if first_archive != second_archive:
            raise ReleaseBuildError(
                "normalized source archive builds are not byte-identical"
            )
        source_inspection = inspect_source_archive_bytes(
            first_archive,
            expected_files=files,
        )

        smokes = _isolated_install_and_smokes(
            first_wheel,
            first_archive,
            work_root=work_root,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir()
        _write_output(
            output / WHEEL_NAME,
            first_wheel_bytes,
            replace=replace,
        )
        _write_output(
            output / SOURCE_ARCHIVE_NAME,
            first_archive,
            replace=replace,
        )
        _write_output(
            output / HANDOFF_NAME,
            files[HANDOFF_NAME],
            replace=replace,
        )

    wheel_record = _artifact_record(output / WHEEL_NAME)
    source_record = _artifact_record(output / SOURCE_ARCHIVE_NAME)
    handoff_record = _artifact_record(output / HANDOFF_NAME)
    report: dict[str, object] = {
        "schema": "pycforge.checkpoint-e-package-report/1",
        "checkpoint": CHECKPOINT,
        "release_version": RELEASE_VERSION,
        "converter_contract_version": CONVERTER_CONTRACT_VERSION,
        "project": project,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "release_tree": {
            "algorithm": TREE_HASH_ALGORITHM,
            "domain": FINGERPRINT_DOMAIN,
            "sha256": tree_sha256,
            "files": len(tree_files),
            "self_excluded": RELEASE_FINGERPRINT.as_posix(),
            "subtrees": subtree_records,
        },
        "release_fingerprint": fingerprint,
        "promotion_evidence": promotion_evidence,
        "wheel": {
            **wheel_record,
            "canonical_filename": WHEEL_NAME,
            "fixed_epoch_builds_compared": 2,
            "fixed_epoch_builds_byte_identical": True,
            "inspection": wheel_inspection,
        },
        "source_archive": {
            **source_record,
            "canonical_filename": SOURCE_ARCHIVE_NAME,
            "archive_root": SOURCE_ARCHIVE_ROOT,
            "normalized_builds_compared": 2,
            "normalized_builds_byte_identical": True,
            "inspection": source_inspection,
        },
        "handoff": handoff_record,
        "smokes": smokes,
        "safety": {
            "python_source_to_c_source_only": True,
            "toolchain_invoked": TOOLCHAIN_INVOKED,
            "compiler_invoked": False,
            "linker_invoked": False,
            "loader_invoked": False,
            "foreign_function_invoked": False,
            "generated_c_compiled_or_executed": (
                GENERATED_C_COMPILED_OR_EXECUTED
            ),
        },
        "checksums": {
            "algorithm": TREE_HASH_ALGORITHM,
            "filename": CHECKSUMS_NAME,
            "covers": [
                WHEEL_NAME,
                SOURCE_ARCHIVE_NAME,
                HANDOFF_NAME,
                PACKAGE_REPORT_NAME,
            ],
        },
        "passed": True,
    }
    report_bytes = canonical_json_bytes(report)
    _write_output(
        output / PACKAGE_REPORT_NAME,
        report_bytes,
        replace=replace,
    )
    checksum_artifacts = [
        _artifact_record(output / WHEEL_NAME),
        _artifact_record(output / SOURCE_ARCHIVE_NAME),
        _artifact_record(output / HANDOFF_NAME),
        _artifact_record(output / PACKAGE_REPORT_NAME),
    ]
    checksums = {
        "schema": "pycforge.release-checksums/1",
        "algorithm": TREE_HASH_ALGORITHM,
        "checkpoint": CHECKPOINT,
        "release_version": RELEASE_VERSION,
        "artifacts": checksum_artifacts,
    }
    _write_output(
        output / CHECKSUMS_NAME,
        canonical_json_bytes(checksums),
        replace=replace,
    )
    return {
        **report,
        "package_report": _artifact_record(output / PACKAGE_REPORT_NAME),
        "checksum_report": _artifact_record(output / CHECKSUMS_NAME),
        "handoff_artifact": _artifact_record(output / HANDOFF_NAME),
        "output_directory": str(output),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic PyCForge Checkpoint E source and wheel "
            "artifacts without invoking a C toolchain."
        )
    )
    parser.add_argument(
        "output_directory",
        type=Path,
        help="directory outside the source tree for release artifacts/evidence",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="PyCForge source root (defaults to the tool's project root)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_release(
            args.root,
            args.output_directory,
        )
    except ReleaseBuildError as exc:
        print(
            json.dumps(
                {
                    "schema": "pycforge.checkpoint-e-package-build-error/1",
                    "passed": False,
                    "error": str(exc),
                    "toolchain_invoked": False,
                    "generated_c_compiled_or_executed": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "passed": report["passed"],
                "output_directory": report["output_directory"],
                "artifacts": {
                    "wheel": report["wheel"],
                    "source_archive": report["source_archive"],
                    "handoff": report["handoff_artifact"],
                    "package_report": report["package_report"],
                    "checksums": report["checksum_report"],
                },
                "toolchain_invoked": False,
                "generated_c_compiled_or_executed": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
