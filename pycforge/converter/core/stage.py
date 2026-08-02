from __future__ import annotations
from typing import Protocol
from .stage_artifact import StageArtifact
from .stage_outcome import StageOutcome
class ConversionStage(Protocol):
    stage_id:str
    input_schema:str
    output_schema:str
    def run(self, artifact:StageArtifact, services:object)->StageOutcome: ...
    def validate(self, artifact:StageArtifact, services:object)->tuple[bool,str]: ...
