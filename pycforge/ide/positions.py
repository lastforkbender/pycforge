"""Immutable text-position indexes for bounded workspace projection."""

from __future__ import annotations

from bisect import bisect_right
from concurrent.futures import CancelledError, Future
from dataclasses import dataclass
from threading import Condition, Thread, current_thread
from typing import Callable


@dataclass(frozen=True, slots=True)
class TextPositionIndex:
    """Line and UTF-16 facts built once for one exact immutable string."""

    text_length: int
    line_starts: tuple[int, ...]
    utf16_line_starts: tuple[int, ...]
    utf16_compatible: bool

    @property
    def line_count(self) -> int:
        return len(self.line_starts)

    def character_offset(self, line: int, column: int) -> int:
        """Translate a one-based line and zero-based column without rescanning."""

        if not isinstance(line, int) or not isinstance(column, int):
            return 0
        if line < 1:
            return 0
        if line > len(self.line_starts):
            return self.text_length
        start = self.line_starts[line - 1]
        end = (
            self.line_starts[line]
            if line < len(self.line_starts)
            else self.text_length
        )
        return min(self.text_length, start + min(max(0, column), end - start))

    def qt_position(self, text: str, offset: int) -> int:
        """Translate a Python code-point offset to a Qt UTF-16 position."""

        clipped = min(self.text_length, max(0, offset))
        if self.utf16_compatible:
            return clipped
        line_index = max(0, bisect_right(self.line_starts, clipped) - 1)
        line_start = self.line_starts[line_index]
        qt_start = self.utf16_line_starts[line_index]
        return qt_start + len(
            text[line_start:clipped].encode("utf-16-le")
        ) // 2

    def qt_range(
        self,
        text: str,
        start: int,
        end: int,
    ) -> tuple[int, int]:
        return self.qt_position(text, start), self.qt_position(text, end)


def build_text_position_index(
    text: str,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> TextPositionIndex:
    """Build source-proportional position facts outside the GUI thread."""

    if not isinstance(text, str):
        raise TypeError("position-index text must be a string")
    line_starts = [0]
    utf16_line_starts = [0]
    utf16_offset = 0
    utf16_compatible = True
    for offset, character in enumerate(text):
        if (
            cancelled is not None
            and offset % 65_536 == 0
            and cancelled()
        ):
            raise CancelledError("position index was superseded")
        astral = ord(character) > 0xFFFF
        if astral:
            utf16_compatible = False
        utf16_offset += 2 if astral else 1
        if character == "\n":
            line_starts.append(offset + 1)
            utf16_line_starts.append(utf16_offset)
    return TextPositionIndex(
        text_length=len(text),
        line_starts=tuple(line_starts),
        utf16_line_starts=tuple(utf16_line_starts),
        utf16_compatible=utf16_compatible,
    )


PositionIndexListener = Callable[[int, str, TextPositionIndex], None]


@dataclass(slots=True)
class _IndexJob:
    submission: int
    generation: int
    text: str
    future: Future[TextPositionIndex]


class TextPositionIndexService:
    """One-active/one-latest-pending text index builder."""

    def __init__(
        self,
        listener: PositionIndexListener | None = None,
    ) -> None:
        self._listener = listener
        self._condition = Condition()
        self._submission = 0
        self._active: _IndexJob | None = None
        self._pending: _IndexJob | None = None
        self._closed = False
        self._thread = Thread(
            target=self._run,
            name="pycforge-output-position-index",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        generation: int,
        text: str,
    ) -> Future[TextPositionIndex]:
        future: Future[TextPositionIndex] = Future()
        with self._condition:
            if self._closed:
                raise RuntimeError("position index service is closed")
            self._submission += 1
            job = _IndexJob(self._submission, generation, text, future)
            replaced = self._pending
            self._pending = job
            if replaced is not None:
                replaced.future.cancel()
            self._condition.notify()
        return future

    def close(
        self,
        *,
        wait: bool = False,
        timeout: float | None = None,
    ) -> None:
        with self._condition:
            if not self._closed:
                self._closed = True
                pending = self._pending
                self._pending = None
                if pending is not None:
                    pending.future.cancel()
                self._condition.notify_all()
        if wait and current_thread() is not self._thread:
            self._thread.join(timeout)

    def _superseded(self, submission: int) -> bool:
        with self._condition:
            return self._closed or submission != self._submission

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._closed:
                    self._condition.wait()
                if self._pending is None and self._closed:
                    return
                job = self._pending
                self._pending = None
                self._active = job
            assert job is not None
            if not job.future.set_running_or_notify_cancel():
                with self._condition:
                    if self._active is job:
                        self._active = None
                    self._condition.notify_all()
                continue
            try:
                index = build_text_position_index(
                    job.text,
                    cancelled=lambda: self._superseded(job.submission),
                )
            except BaseException as exc:
                if not job.future.done():
                    job.future.set_exception(exc)
                index = None
            with self._condition:
                if self._active is job:
                    self._active = None
                publishable = (
                    index is not None
                    and not self._closed
                    and job.submission == self._submission
                    and self._pending is None
                )
                self._condition.notify_all()
            if index is None:
                continue
            if not job.future.done():
                job.future.set_result(index)
            if publishable and self._listener is not None:
                try:
                    self._listener(job.generation, job.text, index)
                except Exception:
                    pass


__all__ = [
    "TextPositionIndex",
    "TextPositionIndexService",
    "build_text_position_index",
]
