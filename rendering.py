"""Read presentation state and return frontend-ready scene components."""

from copy import deepcopy

from presentation_cover import is_cover_scene
from presentation_generator.visual_strategy import resolve_visual_plan
from reliability import failure


def render_presentation(
    state: dict,
    session_id: str | None = None,
    scene_images: dict[str, str] | None = None,
    scene_image_status: dict[str, str] | None = None,
) -> dict:
    """Build a render model without modifying presentation state."""
    try:
        return {
            "current_scene": render_scene(state.get("current_scene"), session_id, scene_images, scene_image_status),
            "completed_scenes": [
                render_scene(scene, session_id, scene_images, scene_image_status)
                for scene in state.get("completed_scenes") or []
                if not is_cover_scene(scene)
            ],
            "theme": deepcopy(state["theme"]),
            "metadata": deepcopy(state["metadata"]),
        }
    except (KeyError, TypeError):
        return {"current_scene": None, "completed_scenes": [], "theme": {}, "metadata": {}, **failure("rendering", "Presentation rendering is temporarily unavailable")}


def render_scene(
    scene: dict | None,
    session_id: str | None = None,
    scene_images: dict[str, str] | None = None,
    scene_image_status: dict[str, str] | None = None,
) -> dict | None:
    """Select the frontend component for one structured scene."""
    if not scene:
        return None
    if is_cover_scene(scene):
        return {
            "id": scene["id"],
            "status": scene["status"],
            "component": "CoverScene",
            "props": deepcopy(scene["content"]),
        }
    component = {
        "hero": "HeroScene",
        "cards": "CardsScene",
        "pipeline": "PipelineScene",
        "quote": "QuoteScene",
        "metric": "MetricScene",
    }.get(scene.get("kind"), "HeroScene")
    props = deepcopy(scene["content"])
    scene_id = scene.get("id")
    plan = resolve_visual_plan(scene)
    props["visual_strategy"] = plan.strategy
    props["needs_gemini_image"] = plan.needs_gemini_image
    props["image_importance"] = plan.image_importance
    status = (scene_image_status or {}).get(scene_id, "idle")
    if plan.needs_gemini_image:
        if status == "generating":
            props["hero_image_status"] = "generating"
        elif session_id and scene_images and scene_id in scene_images:
            version = scene.get("updated_at") or scene.get("created_at") or ""
            props["hero_image_url"] = f"/presentation/media?session_id={session_id}&scene_id={scene_id}&v={version}"
            props["hero_image_status"] = "ready"
    return {
        "id": scene_id,
        "status": scene["status"],
        "component": component,
        "props": props,
    }
