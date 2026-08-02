from __future__ import annotations
from dataclasses import dataclass
from .enums import StageTerminal
from .stage_artifact import StageArtifact
from .diagnostics import Diagnostic

@dataclass(frozen=True, slots=True)
class StageOutcome:
    terminal: StageTerminal
    artifact: StageArtifact|None=None
    diagnostics: tuple[Diagnostic,...]=()
    @property
    def completed(self)->bool: return self.terminal is StageTerminal.COMPLETED
    def __post_init__(self)->None:
        if self.completed != (self.artifact is not None): raise ValueError("Completed outcomes require exactly one artifact; terminal outcomes require none")
