"""Deterministic visual composition strategy for live UI and PPT Master SVG export."""

from dataclasses import dataclass
from typing import Literal

ImageFit = Literal["contain", "cover", "none"]
ImageImportance = Literal["required", "recommended", "optional", "unnecessary"]


@dataclass(frozen=True)
class VisualBounds:
    x: int
    y: int
    width: int
    height: int
    fit: ImageFit = "cover"


@dataclass(frozen=True)
class VisualPlan:
    strategy: str
    needs_gemini_image: bool
    visual_bounds: VisualBounds | None
    image_importance: ImageImportance
    prompt_aspect: Literal["square", "landscape", "wide"] = "square"


def _card_count(scene: dict) -> int:
    content = scene.get("content") or {}
    items = content.get("card_items") or []
    if items:
        return len(items)
    return len(content.get("cards") or [])


def _metric_count(scene: dict) -> int:
    return len((scene.get("content") or {}).get("metrics") or [])


def _stage(scene: dict) -> str:
    content = scene.get("content") or {}
    return scene.get("presentation_stage") or content.get("presentation_stage") or "other"


def _subtitle_words(scene: dict) -> int:
    subtitle = (scene.get("content") or {}).get("subtitle") or ""
    return len(str(subtitle).split())


def resolve_visual_plan(scene: dict) -> VisualPlan:
    """Choose layout strategy from slide purpose, structure, and narrative stage."""
    kind = scene.get("kind", "hero")
    stage = _stage(scene)
    cards = _card_count(scene)
    metrics = _metric_count(scene)

    if kind == "quote" or (stage == "conclusion" and kind != "hero"):
        return VisualPlan("quote_typography", False, None, "unnecessary")

    if stage == "architecture":
        return VisualPlan("architecture_diagram", False, None, "unnecessary")

    if kind == "pipeline" or stage == "workflow":
        return VisualPlan("pipeline_horizontal", False, None, "unnecessary")

    if kind == "metric" or (stage == "results" and metrics):
        return VisualPlan("metrics_dashboard", False, None, "unnecessary")

    if kind == "cards":
        if cards >= 4:
            return VisualPlan("cards_full_width", False, None, "unnecessary")
        if cards >= 2:
            return VisualPlan(
                "cards_with_small_visual",
                True,
                VisualBounds(920, 96, 264, 198, "cover"),
                "optional",
                "landscape",
            )
        return VisualPlan("cards_full_width", False, None, "unnecessary")

    if kind == "hero":
        if stage == "conclusion":
            return VisualPlan(
                "hero_visual_focus",
                True,
                VisualBounds(160, 168, 960, 340, "cover"),
                "recommended",
                "wide",
            )
        if stage == "introduction" or _subtitle_words(scene) <= 18:
            return VisualPlan(
                "hero_split_visual",
                True,
                VisualBounds(720, 132, 464, 464, "cover"),
                "recommended",
                "square",
            )
        return VisualPlan(
            "hero_split_visual",
            True,
            VisualBounds(720, 132, 400, 400, "contain"),
            "optional",
            "square",
        )

    return VisualPlan("hero_split_visual", True, VisualBounds(720, 132, 464, 464, "cover"), "optional", "square")


def visual_strategy_label(scene: dict) -> str:
    """Human-readable label for generation status messages."""
    plan = resolve_visual_plan(scene)
    labels = {
        "hero_split_visual": "hero split layout",
        "hero_visual_focus": "hero visual-focus layout",
        "cards_full_width": "full-width card layout",
        "cards_with_small_visual": "cards with accent visual",
        "architecture_diagram": "architecture diagram layout",
        "pipeline_horizontal": "horizontal pipeline layout",
        "metrics_dashboard": "metrics dashboard layout",
        "quote_typography": "quote typography layout",
    }
    return labels.get(plan.strategy, "structured content layout")
