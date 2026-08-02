from __future__ import annotations
from dataclasses import dataclass

MAX_SAFE_NESTING_DEPTH = 128

@dataclass(frozen=True, slots=True)
class ResourcePolicy:
    max_source_bytes: int = 1_000_000
    max_source_lines: int = 100_000
    max_diagnostics: int = 1_000
    max_trace_events: int = 10_000
    max_telemetry_events: int = 10_000
    max_tokens: int = 250_000
    max_ast_nodes: int = 100_000
    max_nesting_depth: int = MAX_SAFE_NESTING_DEPTH
    max_source_documents: int = 64
    max_import_edges: int = 4_096

    def validate(self) -> tuple[str, ...]:
        errors=[]
        for name in self.__slots__:
            value=getattr(self,name)
            if not isinstance(value,int) or isinstance(value,bool) or value < 0: errors.append(f"{name} must be a non-negative integer")
        for name in ("max_source_lines", "max_diagnostics", "max_tokens", "max_ast_nodes", "max_nesting_depth", "max_source_documents"):
            value=getattr(self,name)
            if isinstance(value,int) and not isinstance(value,bool) and value == 0:
                errors.append(f"{name} must be greater than zero")
        if isinstance(self.max_nesting_depth,int) and not isinstance(self.max_nesting_depth,bool) and self.max_nesting_depth > MAX_SAFE_NESTING_DEPTH:
            errors.append(f"max_nesting_depth must not exceed the safe pipeline ceiling of {MAX_SAFE_NESTING_DEPTH}")
        return tuple(errors)
    def to_dict(self)->dict[str,int]: return {k:getattr(self,k) for k in self.__slots__}
