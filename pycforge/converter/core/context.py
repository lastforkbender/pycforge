from __future__ import annotations
from dataclasses import dataclass
from .canonicalization import CanonicalRequest
from .diagnostics import DiagnosticCollector
from .cancellation import CancellationToken
@dataclass(slots=True)
class ConversionContext:
    canonical: CanonicalRequest
    diagnostics: DiagnosticCollector
    cancellation: CancellationToken
    frontend_tree: object|None = None
    frontend_documents: tuple[object, ...] = ()
    frontend_trees: tuple[object, ...] = ()
