from __future__ import annotations
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

class AtomicWriteError(OSError):
    pass

class AtomicWriter:
    def __init__(self, *, before_replace: Callable[[Path], None] | None = None) -> None:
        self._before_replace = before_replace

    def write_text(self, destination: Path, text: str) -> None:
        destination = Path(destination)
        temporary: Path | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if self._before_replace:
                self._before_replace(temporary)
            os.replace(temporary, destination)
            temporary = None
        except Exception as exc:
            raise AtomicWriteError(f"atomic write failed for {destination}") from exc
        finally:
            if temporary is not None:
                try: temporary.unlink()
                except FileNotFoundError: pass
