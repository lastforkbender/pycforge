from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConversionProgress:
    """Observer-only progress at deterministic pipeline boundaries."""

    state: str
    stage_id: str | None
    completed_stages: int
    total_stages: int

    def __post_init__(self) -> None:
        if self.state not in {"pipeline-ready", "stage-entered", "stage-completed"}:
            raise ValueError("unknown conversion-progress state")
        if self.completed_stages < 0 or self.total_stages < 0:
            raise ValueError("conversion-progress counts must be non-negative")
        if self.completed_stages > self.total_stages:
            raise ValueError("completed conversion stages exceed the pipeline size")
        if self.state == "pipeline-ready" and self.stage_id is not None:
            raise ValueError("pipeline-ready progress cannot identify an active stage")
        if self.state != "pipeline-ready" and not self.stage_id:
            raise ValueError("stage progress requires a stage identity")
