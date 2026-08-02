from __future__ import annotations

import os
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from queue import Empty, Full, Queue
from tempfile import NamedTemporaryFile
from threading import RLock, Thread, current_thread
from typing import Callable


class WorkspaceIOError(OSError):
    """A bounded workspace file operation failed."""


class StaleWorkspaceWrite(WorkspaceIOError):
    """Freshness changed before an atomic destination replacement."""


@dataclass(frozen=True, slots=True)
class FileRead:
    path: str
    text: str
    utf8_sha256: str


@dataclass(slots=True)
class _IOJob:
    operation: Callable[[], object]
    future: Future


class WorkspaceIOService:
    """Small daemon-backed file service that never blocks application exit."""

    def __init__(self, *, workers: int = 2, capacity: int = 8) -> None:
        if not 1 <= workers <= 4:
            raise ValueError("workspace I/O worker count must be between 1 and 4")
        if capacity < workers:
            raise ValueError("workspace I/O capacity must cover every worker")
        self._queue: Queue[_IOJob | None] = Queue(maxsize=capacity)
        self._lock = RLock()
        self._closed = False
        self._threads = tuple(
            Thread(
                target=self._run,
                name=f"pycforge-file-io-{index + 1}",
                daemon=True,
            )
            for index in range(workers)
        )
        for thread in self._threads:
            thread.start()

    def read_text(self, path: Path | str) -> Future[FileRead]:
        source = Path(path)

        def operation() -> FileRead:
            try:
                text = source.read_text(encoding="utf-8")
                encoded = text.encode("utf-8")
            except (OSError, UnicodeError) as exc:
                raise WorkspaceIOError(
                    f"could not read UTF-8 workspace file: {source}"
                ) from exc
            return FileRead(str(source), text, sha256(encoded).hexdigest())

        return self._submit(operation)

    def write_text(
        self,
        path: Path | str,
        text: str,
        *,
        before_replace: Callable[[], bool] | None = None,
    ) -> Future[str]:
        destination = Path(path)
        if not isinstance(text, str):
            raise TypeError("workspace file text must be a string")

        def operation() -> str:
            self._atomic_write(
                destination,
                text,
                before_replace=before_replace,
            )
            return str(destination)

        return self._submit(operation)

    def observe_text(self, path: Path | str) -> Future[FileRead]:
        return self.read_text(path)

    def close(self, *, wait: bool = False, timeout: float | None = None) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                while True:
                    try:
                        job = self._queue.get_nowait()
                    except Empty:
                        break
                    if job is not None and not job.future.done():
                        job.future.cancel()
                    self._queue.task_done()
                for _ in self._threads:
                    try:
                        self._queue.put_nowait(None)
                    except Full:
                        break
        if wait:
            for thread in self._threads:
                if thread is not current_thread():
                    thread.join(timeout)

    def _submit(self, operation: Callable[[], object]):
        future = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("workspace I/O service is closed")
            try:
                self._queue.put_nowait(_IOJob(operation, future))
            except Full as exc:
                raise WorkspaceIOError(
                    "workspace I/O capacity is temporarily full"
                ) from exc
        return future

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                if not job.future.set_running_or_notify_cancel():
                    continue
                try:
                    result = job.operation()
                except BaseException as exc:
                    job.future.set_exception(exc)
                else:
                    job.future.set_result(result)
            finally:
                self._queue.task_done()

    @staticmethod
    def _atomic_write(
        destination: Path,
        text: str,
        *,
        before_replace: Callable[[], bool] | None,
    ) -> None:
        temporary: Path | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            if before_replace is not None and not before_replace():
                raise StaleWorkspaceWrite(
                    "workspace freshness changed before file publication"
                )
            os.replace(temporary, destination)
            temporary = None
        except StaleWorkspaceWrite:
            raise
        except Exception as exc:
            raise WorkspaceIOError(
                f"atomic workspace write failed: {destination}"
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass


__all__ = [
    "FileRead",
    "StaleWorkspaceWrite",
    "WorkspaceIOError",
    "WorkspaceIOService",
]
