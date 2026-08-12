"""The structured scene-decision tool available to the presentation planner."""

from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class SceneDecision(BaseModel):
    """A planner decision, validated before Python changes presentation state."""

    action: Literal["replace", "merge", "start_new_scene", "complete_scene"]
    kind: Literal["hero", "cards", "pipeline", "metric", "quote"]
    title: str = Field(description="Short slide title.")
    subtitle: str = Field(default="", description="One concise supporting sentence.")
    cards: list[str] = Field(default_factory=list, description="Short supporting points or steps.")
    metrics: list[dict[str, str]] = Field(
        default_factory=list, description="Optional statistic items with label and value keys."
    )
    primary_idea: str = Field(description="The single message this scene communicates.")
    presentation_stage: Literal[
        "introduction", "problem", "solution", "architecture", "workflow", "results", "conclusion", "other"
    ] = "other"
    icon: str = Field(default="sparkles", description="Semantic Lucide-style icon name.")
    eyebrow: str = Field(default="", description="Short section label.")
    accent: Literal["ember", "lime", "sky", "violet"] = Field(default="sky", description="Accent color token.")
    card_items: list[dict] = Field(default_factory=list, description="Structured cards with title, body, icon.")


@tool(args_schema=SceneDecision)
def stage_scene(**scene_update) -> dict:
    """Decide how to evolve a scene; this tool does not modify presentation state.

    replace edits the active scene, merge adds detail to it, start_new_scene
    finalizes the active scene and starts another, and complete_scene finalizes it.
    """
    return scene_update


tools = [stage_scene]
