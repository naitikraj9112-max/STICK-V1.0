"""Small models at the boundary between scene state and PPT Master artifacts."""

from typing import Literal

from pydantic import BaseModel, Field


GenerationState = Literal["idle", "generating", "validating", "ready", "error", "unavailable"]


class GenerationResult(BaseModel):
    status: GenerationState
    scene_id: str | None = None
    artifact_path: str | None = None
    message: str = ""
    corrected: bool = False
    quality_issues: list[str] = Field(default_factory=list)


from presentation_generator.visual_strategy import visual_strategy_label


def visual_strategy(scene: dict) -> str:
    return visual_strategy_label(scene)
