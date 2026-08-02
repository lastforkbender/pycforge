"""Persistent per-document Qt buffers for the closed SourceBundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from PyQt5.QtCore import QObject
from PyQt5.QtGui import QTextDocument
from PyQt5.QtWidgets import QPlainTextDocumentLayout


MAX_SOURCE_BUFFERS = 64


@dataclass(slots=True)
class _SourceBuffer:
    document: QTextDocument
    source_key: int


class SourceBufferStore(QObject):
    """Own one undo-capable ``QTextDocument`` per explicit source document."""

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._buffers: dict[str, _SourceBuffer] = {}

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(self._buffers)

    def document_for(self, document_id: str) -> QTextDocument:
        try:
            return self._buffers[document_id].document
        except KeyError as exc:
            raise KeyError(
                f"source buffer is unavailable: {document_id}"
            ) from exc

    def is_modified(self, document_id: str) -> bool:
        buffer = self._buffers.get(document_id)
        return buffer is not None and buffer.document.isModified()

    def reconcile(
        self,
        documents: Iterable[Any],
        *,
        skip_document_id: str | None = None,
    ) -> None:
        records = tuple(documents)
        if not 1 <= len(records) <= MAX_SOURCE_BUFFERS:
            raise ValueError("source buffers require between 1 and 64 documents")
        identifiers = tuple(item.document_id for item in records)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("source buffer document IDs must be unique")
        for document_id in tuple(self._buffers):
            if document_id in identifiers:
                continue
            buffer = self._buffers.pop(document_id)
            buffer.document.setParent(None)
            buffer.document.deleteLater()
        for item in records:
            key = id(item.text)
            buffer = self._buffers.get(item.document_id)
            if buffer is None:
                document = QTextDocument(self)
                document.setDocumentLayout(
                    QPlainTextDocumentLayout(document)
                )
                document.setPlainText(item.text)
                # Controller ``dirty`` is disk-save authority.  Qt's modified
                # bit is reserved for text not yet synchronized back into the
                # immutable workspace snapshot.
                document.setModified(False)
                self._buffers[item.document_id] = _SourceBuffer(
                    document,
                    key,
                )
                continue
            if (
                item.document_id != skip_document_id
                and buffer.source_key != key
            ):
                undo_enabled = buffer.document.isUndoRedoEnabled()
                buffer.document.setUndoRedoEnabled(False)
                buffer.document.setPlainText(item.text)
                buffer.document.setUndoRedoEnabled(undo_enabled)
                buffer.document.setModified(False)
                buffer.source_key = key

    def mark_synchronized(
        self,
        document_id: str,
        source_key: int,
        *,
        dirty: bool,
    ) -> None:
        buffer = self._buffers.get(document_id)
        if buffer is None:
            return
        del dirty
        buffer.source_key = int(source_key)
        buffer.document.setModified(False)

    def close(self) -> None:
        for buffer in self._buffers.values():
            buffer.document.setParent(None)
            buffer.document.deleteLater()
        self._buffers.clear()


__all__ = ["MAX_SOURCE_BUFFERS", "SourceBufferStore"]
