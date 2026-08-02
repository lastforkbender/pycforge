"""Verify the exact public PyCForge wheel and source distribution."""

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
from pathlib import Path, PurePosixPath
import tarfile
from zipfile import ZipFile


VERSION = "0.15.2"
EXPECTED_DEPENDENCY = "PyQt5<6,>=5.15.11"
EXPECTED_CONSOLE_SCRIPTS = {
    "pycforge": "pycforge.laboratory.cli:main",
}
EXPECTED_GUI_SCRIPTS = {
    "pycforge-workspace": "pycforge.ide.qt:run",
}
EXPECTED_LICENSE_EXPRESSION = "GPL-3.0-only"
EXPECTED_SUMMARY = "Deterministic bounded Python-to-C source transpiler"
EXPECTED_REQUIRES_PYTHON = ">=3.11"
EXPECTED_SCREENSHOT = Path("docs/images/pycforge-workspace-0.15.2.png")
EXPECTED_PROGRAMMER_GUIDE = Path(
    "docs/PyCForge_v0_15_2_Conversion_Examples_Reference_Edition.pdf"
)
EXPECTED_README_SNIPPETS = (
    "python -m pip install pycforge",
    "PyQt5 and the desktop application as required",
    "https://raw.githubusercontent.com/lastforkbender/pycforge/main/"
    "docs/images/pycforge-workspace-0.15.2.png",
    "https://github.com/lastforkbender/pycforge/blob/main/docs/"
    "PyCForge_v0_15_2_Conversion_Examples_Reference_Edition.pdf",
)
EXPECTED_PROJECT_URLS = [
    "Homepage, https://github.com/lastforkbender/pycforge",
    "Repository, https://github.com/lastforkbender/pycforge",
    "Issues, https://github.com/lastforkbender/pycforge/issues",
    "Changelog, https://github.com/lastforkbender/pycforge/blob/main/CHANGELOG.md",
]
EXPECTED_CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Environment :: X11 Applications :: Qt",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Code Generators",
]
DIST_INFO = f"pycforge-{VERSION}.dist-info"
NATIVE_SUFFIXES = {
    ".a", ".dll", ".dylib", ".exe", ".lib", ".o", ".obj", ".pyd", ".so"
}
ROOT = Path(__file__).resolve().parents[1]


class DistributionVerificationError(RuntimeError):
    """A public distribution invariant failed."""


def _safe_member_name(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise DistributionVerificationError(
            f"distribution contains an unsafe member name: {value!r}"
        )
    return path


def _source_payloads() -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    for path in sorted((ROOT / "pycforge").rglob("*")):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in {".py", ".svg"}
        ):
            payloads[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    return payloads


def _verify_public_readme(payload: bytes) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DistributionVerificationError("README.md is not UTF-8") from exc
    missing = [value for value in EXPECTED_README_SNIPPETS if value not in text]
    if missing:
        raise DistributionVerificationError(
            f"README.md is missing required release content: {missing}"
        )
    screenshot = ROOT / EXPECTED_SCREENSHOT
    if not screenshot.is_file() or not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise DistributionVerificationError(
            "README.md application screenshot is missing or is not PNG"
        )
    guide = ROOT / EXPECTED_PROGRAMMER_GUIDE
    if not guide.is_file() or not guide.read_bytes().startswith(b"%PDF-"):
        raise DistributionVerificationError(
            "README.md programmer guide is missing or is not PDF"
        )


def _verify_core_metadata(metadata: object) -> None:
    if metadata.get("Name") != "pycforge" or metadata.get("Version") != VERSION:
        raise DistributionVerificationError("distribution identity is not exact")
    if metadata.get("Summary") != EXPECTED_SUMMARY:
        raise DistributionVerificationError("distribution summary is not exact")
    if metadata.get("Requires-Python") != EXPECTED_REQUIRES_PYTHON:
        raise DistributionVerificationError("Requires-Python is not exact")
    if metadata.get_all("Requires-Dist", []) != [EXPECTED_DEPENDENCY]:
        raise DistributionVerificationError(
            "PyQt5 is not the exact unconditional runtime dependency"
        )
    if metadata.get_all("Provides-Extra", []):
        raise DistributionVerificationError("distribution unexpectedly exposes an extra")
    if metadata.get("Description-Content-Type") != "text/markdown":
        raise DistributionVerificationError("long description is not Markdown")
    if metadata.get("License-Expression") != EXPECTED_LICENSE_EXPRESSION:
        raise DistributionVerificationError("license expression is not GPLv3")
    if metadata.get_all("Project-URL", []) != EXPECTED_PROJECT_URLS:
        raise DistributionVerificationError("project URLs are not exact")
    if metadata.get_all("Classifier", []) != EXPECTED_CLASSIFIERS:
        raise DistributionVerificationError("classifiers are not exact")
    readme_payload = (ROOT / "README.md").read_bytes()
    _verify_public_readme(readme_payload)
    if metadata.get_payload(decode=True) != readme_payload:
        raise DistributionVerificationError("long description differs from README.md")


def _verify_entry_points(payload: bytes) -> None:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(payload.decode("utf-8"))
    if parser.sections() != ["console_scripts", "gui_scripts"]:
        raise DistributionVerificationError("entry-point groups are not exact")
    if dict(parser.items("console_scripts")) != EXPECTED_CONSOLE_SCRIPTS:
        raise DistributionVerificationError("console entry point is not exact")
    if dict(parser.items("gui_scripts")) != EXPECTED_GUI_SCRIPTS:
        raise DistributionVerificationError("GUI entry point is not exact")


def _record_digest(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
    return "sha256=" + encoded.rstrip(b"=").decode("ascii")


def _verify_record(members: dict[str, bytes], record_name: str) -> None:
    try:
        rows = list(
            csv.reader(
                io.StringIO(members[record_name].decode("utf-8"), newline="")
            )
        )
    except (KeyError, UnicodeDecodeError, csv.Error) as exc:
        raise DistributionVerificationError("wheel RECORD is unreadable") from exc
    if any(len(row) != 3 for row in rows):
        raise DistributionVerificationError("wheel RECORD row shape is invalid")
    recorded_names = [row[0] for row in rows]
    if len(recorded_names) != len(set(recorded_names)):
        raise DistributionVerificationError("wheel RECORD contains duplicate paths")
    if set(recorded_names) != set(members):
        raise DistributionVerificationError("wheel RECORD coverage is not exact")
    for name, digest, size in rows:
        if name == record_name:
            if digest or size:
                raise DistributionVerificationError(
                    "wheel RECORD must leave its own hash and size empty"
                )
            continue
        payload = members[name]
        if digest != _record_digest(payload) or size != str(len(payload)):
            raise DistributionVerificationError(
                f"wheel RECORD hash or size is invalid for {name}"
            )


def verify_wheel(path: Path) -> dict[str, object]:
    with ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise DistributionVerificationError("wheel contains duplicate members")
        for name in names:
            _safe_member_name(name)
        members = {name: archive.read(name) for name in names}

    source_payloads = _source_payloads()
    expected_dist_info = {
        f"{DIST_INFO}/METADATA",
        f"{DIST_INFO}/WHEEL",
        f"{DIST_INFO}/entry_points.txt",
        f"{DIST_INFO}/top_level.txt",
        f"{DIST_INFO}/licenses/LICENSE",
        f"{DIST_INFO}/RECORD",
    }
    expected_names = set(source_payloads) | expected_dist_info
    name_set = set(members)
    if name_set != expected_names:
        missing = sorted(expected_names - name_set)
        unexpected = sorted(name_set - expected_names)
        raise DistributionVerificationError(
            f"wheel member map is not exact; missing={missing}, unexpected={unexpected}"
        )
    for name, expected_payload in source_payloads.items():
        if members[name] != expected_payload:
            raise DistributionVerificationError(
                f"wheel payload differs from source: {name}"
            )

    metadata_name = f"{DIST_INFO}/METADATA"
    wheel_name = f"{DIST_INFO}/WHEEL"
    entry_points_name = f"{DIST_INFO}/entry_points.txt"
    license_name = f"{DIST_INFO}/licenses/LICENSE"
    record_name = f"{DIST_INFO}/RECORD"

    metadata = BytesParser(policy=email_policy).parsebytes(members[metadata_name])
    wheel_metadata = BytesParser(policy=email_policy).parsebytes(members[wheel_name])
    _verify_core_metadata(metadata)
    if members[license_name] != (ROOT / "LICENSE").read_bytes():
        raise DistributionVerificationError("wheel license text differs from source")
    if members[f"{DIST_INFO}/top_level.txt"] != b"pycforge\n":
        raise DistributionVerificationError("wheel top-level declaration is not exact")
    if wheel_metadata.get("Wheel-Version") != "1.0":
        raise DistributionVerificationError("wheel metadata version is not 1.0")
    if wheel_metadata.get("Root-Is-Purelib") != "true":
        raise DistributionVerificationError("wheel is not pure Python")
    if wheel_metadata.get_all("Tag", []) != ["py3-none-any"]:
        raise DistributionVerificationError("wheel tag is not py3-none-any")

    _verify_entry_points(members[entry_points_name])
    _verify_record(members, record_name)

    icons = [
        name
        for name in names
        if name.startswith("pycforge/ide/resources/icons/")
        and name.endswith(".svg")
    ]
    if len(icons) != 55:
        raise DistributionVerificationError(
            f"wheel contains {len(icons)} SVG icons, expected 55"
        )
    native = [
        name for name in names if PurePosixPath(name).suffix.lower() in NATIVE_SUFFIXES
    ]
    if native:
        raise DistributionVerificationError("wheel contains native payloads")
    return {
        "path": str(path),
        "members": len(names),
        "dependency": EXPECTED_DEPENDENCY,
        "extras": 0,
        "icons": len(icons),
        "license": EXPECTED_LICENSE_EXPRESSION,
        "pure_python": True,
    }


def verify_sdist(path: Path) -> dict[str, object]:
    expected_root = f"pycforge-{VERSION}"
    names: list[str] = []
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            safe = _safe_member_name(member.name)
            if safe.parts[0] != expected_root:
                raise DistributionVerificationError("sdist root is not exact")
            if not (member.isfile() or member.isdir()):
                raise DistributionVerificationError(
                    "sdist contains a link or special-file member"
                )
            names.append(member.name)
            if member.isdir():
                directories.add(member.name.rstrip("/"))
            else:
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise DistributionVerificationError(
                        f"sdist file member is unreadable: {member.name}"
                    )
                files[member.name] = extracted.read()
    if len(names) != len(set(names)):
        raise DistributionVerificationError("sdist contains duplicate members")

    public_files = {
        name: (ROOT / name).read_bytes()
        for name in (
            "CHANGELOG.md",
            "CURRENT_STATE.md",
            "LICENSE",
            "MANIFEST.in",
            "README.md",
            "RELEASE_NOTES.md",
            "pyproject.toml",
        )
    }
    source_payloads = _source_payloads()
    generated_files = {
        "PKG-INFO",
        "setup.cfg",
        "pycforge.egg-info/PKG-INFO",
        "pycforge.egg-info/SOURCES.txt",
        "pycforge.egg-info/dependency_links.txt",
        "pycforge.egg-info/entry_points.txt",
        "pycforge.egg-info/requires.txt",
        "pycforge.egg-info/top_level.txt",
    }
    expected_relative_files = (
        set(public_files) | set(source_payloads) | generated_files
    )
    actual_relative_files = {
        PurePosixPath(name).relative_to(expected_root).as_posix() for name in files
    }
    if actual_relative_files != expected_relative_files:
        missing = sorted(expected_relative_files - actual_relative_files)
        unexpected = sorted(actual_relative_files - expected_relative_files)
        raise DistributionVerificationError(
            f"sdist file map is not exact; missing={missing}, unexpected={unexpected}"
        )
    expected_directories = {expected_root}
    for relative_name in expected_relative_files:
        parent = PurePosixPath(expected_root, relative_name).parent
        while parent.as_posix() != ".":
            expected_directories.add(parent.as_posix())
            if parent.as_posix() == expected_root:
                break
            parent = parent.parent
    if directories != expected_directories:
        raise DistributionVerificationError("sdist directory map is not exact")
    for name, expected_payload in {**public_files, **source_payloads}.items():
        archive_name = f"{expected_root}/{name}"
        if files[archive_name] != expected_payload:
            raise DistributionVerificationError(
                f"sdist payload differs from source: {name}"
            )

    package_metadata = BytesParser(policy=email_policy).parsebytes(
        files[f"{expected_root}/PKG-INFO"]
    )
    _verify_core_metadata(package_metadata)
    if files[f"{expected_root}/pycforge.egg-info/PKG-INFO"] != files[
        f"{expected_root}/PKG-INFO"
    ]:
        raise DistributionVerificationError("sdist PKG-INFO copies differ")
    _verify_entry_points(
        files[f"{expected_root}/pycforge.egg-info/entry_points.txt"]
    )
    if files[f"{expected_root}/pycforge.egg-info/requires.txt"] != (
        EXPECTED_DEPENDENCY + "\n"
    ).encode("utf-8"):
        raise DistributionVerificationError("sdist dependency inventory is not exact")
    if files[f"{expected_root}/pycforge.egg-info/top_level.txt"] != b"pycforge\n":
        raise DistributionVerificationError("sdist top-level declaration is not exact")
    source_inventory = files[
        f"{expected_root}/pycforge.egg-info/SOURCES.txt"
    ].decode("utf-8").splitlines()
    expected_inventory = (
        set(public_files)
        | set(source_payloads)
        | {
            "pycforge.egg-info/PKG-INFO",
            "pycforge.egg-info/SOURCES.txt",
            "pycforge.egg-info/dependency_links.txt",
            "pycforge.egg-info/entry_points.txt",
            "pycforge.egg-info/requires.txt",
            "pycforge.egg-info/top_level.txt",
        }
    )
    if len(source_inventory) != len(set(source_inventory)) or set(
        source_inventory
    ) != expected_inventory:
        raise DistributionVerificationError("sdist SOURCES.txt is not exact")
    return {
        "path": str(path),
        "members": len(names),
        "root": expected_root,
        "repository_only_members": 0,
    }


def verify_directory(directory: Path) -> dict[str, object]:
    expected_wheel = f"pycforge-{VERSION}-py3-none-any.whl"
    expected_sdist = f"pycforge-{VERSION}.tar.gz"
    expected_names = {expected_wheel, expected_sdist}
    actual_names = {path.name for path in directory.iterdir()}
    if actual_names != expected_names or not all(
        (directory / name).is_file() for name in expected_names
    ):
        raise DistributionVerificationError(
            "dist must contain exactly the release wheel and source distribution"
        )
    wheel = directory / expected_wheel
    sdist = directory / expected_sdist
    return {
        "schema": "pycforge.public-distribution-verification/1",
        "passed": True,
        "wheel": verify_wheel(wheel),
        "sdist": verify_sdist(sdist),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify_directory(args.directory.resolve())
    except (DistributionVerificationError, OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
