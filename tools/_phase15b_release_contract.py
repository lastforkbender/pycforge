"""Shared Phase 15B release-custody checks.

The helpers in this module are deliberately source-only.  They inspect paths,
regular-file bytes, normalized source archives, and wheels without importing
or executing user code and without invoking any native toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
import tarfile
from typing import Iterable, Mapping
from zipfile import ZipFile


# Encoded so the vocabulary audit does not reproduce the retired label in its
# own source, diagnostics, reports, or package members.
_RETIRED_THEME_BYTES = bytes.fromhex("7370616365706f7274")
_IGNORED_DIRECTORY_NAMES = frozenset({".git"})


@dataclass(frozen=True, slots=True)
class VocabularyScan:
    """Bounded, sanitized result for one path/content vocabulary scan."""

    path_matches: tuple[str, ...]
    content_matches: tuple[str, ...]
    regular_files_scanned: int

    @property
    def passed(self) -> bool:
        return not self.path_matches and not self.content_matches

    def to_report(self) -> dict[str, object]:
        """Return aggregate evidence without reproducing matched vocabulary."""

        return {
            "passed": self.passed,
            "path_match_count": len(self.path_matches),
            "content_match_count": len(self.content_matches),
            "regular_files_scanned": self.regular_files_scanned,
        }


def _contains_retired_theme_label(value: bytes) -> bool:
    return _RETIRED_THEME_BYTES in value.lower()


def _safe_member_name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("archive contains an unsafe member path")
    return value


def scan_named_bytes(items: Iterable[tuple[str, bytes]]) -> VocabularyScan:
    """Scan already-resolved named byte payloads without exposing the label."""

    path_matches: list[str] = []
    content_matches: list[str] = []
    count = 0
    for name, payload in items:
        safe_name = _safe_member_name(name)
        count += 1
        if _contains_retired_theme_label(safe_name.encode("utf-8")):
            path_matches.append(safe_name)
        if _contains_retired_theme_label(payload):
            content_matches.append(safe_name)
    return VocabularyScan(
        tuple(sorted(path_matches)),
        tuple(sorted(content_matches)),
        count,
    )


def scan_release_tree(root: Path) -> VocabularyScan:
    """Scan every regular file and relative path beneath ``root``."""

    resolved = root.resolve()
    items: list[tuple[str, bytes]] = []
    for candidate in sorted(
        resolved.rglob("*"),
        key=lambda path: path.relative_to(resolved).as_posix(),
    ):
        relative = candidate.relative_to(resolved)
        if any(part in _IGNORED_DIRECTORY_NAMES for part in relative.parts):
            continue
        if candidate.is_symlink():
            raise ValueError(
                f"release tree contains a symbolic link: {relative.as_posix()}"
            )
        if not candidate.is_file():
            continue
        items.append((relative.as_posix(), candidate.read_bytes()))
    return scan_named_bytes(items)


def scan_source_archive_bytes(payload: bytes) -> VocabularyScan:
    """Scan regular-file member paths and contents in a gzip tar archive."""

    items: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                raise ValueError("source archive contains a non-regular member")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("source archive contains an unreadable member")
            items.append((_safe_member_name(member.name), stream.read()))
    return scan_named_bytes(items)


def scan_wheel(path: Path) -> VocabularyScan:
    """Scan regular member paths and contents in one wheel."""

    items: list[tuple[str, bytes]] = []
    with ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            items.append((_safe_member_name(info.filename), archive.read(info)))
    return scan_named_bytes(items)


def assert_clean_scan(scan: VocabularyScan, *, label: str) -> None:
    """Raise a sanitized error when a vocabulary scan is not clean."""

    if not scan.passed:
        raise ValueError(
            f"{label} contains retired-theme vocabulary "
            f"(paths={len(scan.path_matches)}, "
            f"contents={len(scan.content_matches)})"
        )


def scan_file_map(files: Mapping[str, bytes]) -> VocabularyScan:
    """Scan the deterministic release map used by source packaging."""

    return scan_named_bytes(sorted(files.items()))


__all__ = [
    "VocabularyScan",
    "assert_clean_scan",
    "scan_file_map",
    "scan_named_bytes",
    "scan_release_tree",
    "scan_source_archive_bytes",
    "scan_wheel",
]
