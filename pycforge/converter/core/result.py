from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .enums import ResultStatus
from .diagnostics import Diagnostic
from .fingerprint import Fingerprint
from .stage_artifact import StageArtifact
@dataclass(frozen=True, slots=True)
class ConversionResult:
    status: ResultStatus
    generated_c: str|None
    diagnostics: tuple[Diagnostic,...]
    request_fingerprint: Fingerprint|None
    resource_fingerprint: Fingerprint|None
    output_fingerprint: Fingerprint|None
    last_completed_stage: str|None
    stage_order: tuple[str,...]
    decision_trace: dict[str,Any]|None=None
    telemetry: dict[str,Any]|None=None
    stage_artifact: StageArtifact|None=None
    conversion_summary: dict[str,Any]|None=None
    def semantic_dict(self)->dict[str,object]:
        return {"status":self.status.value,"generated_c":self.generated_c,"diagnostics":[d.to_dict() for d in self.diagnostics],"request_fingerprint":None if self.request_fingerprint is None else self.request_fingerprint.to_dict(),"resource_fingerprint":None if self.resource_fingerprint is None else self.resource_fingerprint.to_dict(),"output_fingerprint":None if self.output_fingerprint is None else self.output_fingerprint.to_dict(),"last_completed_stage":self.last_completed_stage,"stage_order":list(self.stage_order),"conversion_summary":self.conversion_summary}
