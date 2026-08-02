"""Normalize a built source distribution for byte-reproducible publication."""

from __future__ import annotations

import argparse
from copy import copy
import gzip
import io
import os
from pathlib import Path
import tarfile
import tempfile


class SdistNormalizationError(RuntimeError):
    """The input is not a normalizable regular-file source distribution."""


def normalize_sdist(path: Path, epoch: int) -> None:
    if epoch < 0:
        raise SdistNormalizationError("SOURCE_DATE_EPOCH must be non-negative")

    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, mode="r:gz") as source:
        for member in source.getmembers():
            if not (member.isfile() or member.isdir()):
                raise SdistNormalizationError(
                    f"sdist contains a link or special member: {member.name}"
                )
            payload: bytes | None = None
            if member.isfile():
                extracted = source.extractfile(member)
                if extracted is None:
                    raise SdistNormalizationError(
                        f"sdist member is unreadable: {member.name}"
                    )
                payload = extracted.read()
            entries.append((member, payload))

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=temporary,
                mtime=epoch,
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
                ) as target:
                    for original, payload in entries:
                        normalized = copy(original)
                        normalized.uid = 0
                        normalized.gid = 0
                        normalized.uname = ""
                        normalized.gname = ""
                        normalized.mtime = epoch
                        normalized.pax_headers = {}
                        target.addfile(
                            normalized,
                            None if payload is None else io.BytesIO(payload),
                        )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "-1")),
    )
    args = parser.parse_args(argv)
    normalize_sdist(args.path.resolve(), args.epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
