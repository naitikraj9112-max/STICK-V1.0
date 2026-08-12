"""Deterministic policies that avoid unnecessary agent work."""

from presentation_generator.visual_strategy import resolve_visual_plan


def should_run_critic(scene_update: dict, presentation_state: dict | None = None) -> bool:
    """Reserve reflection for transitions or dense/structurally complex scenes."""
    if presentation_state is not None:
        if not presentation_state.get("current_scene") and not presentation_state.get("completed_scenes"):
            return False
    return (
        scene_update.get("action") == "start_new_scene"
        or scene_update.get("kind") in {"pipeline", "metric"}
        or len(scene_update.get("cards") or []) > 3
        or scene_update.get("presentation_stage") == "architecture"
    )


def should_generate_scene_image(scene: dict) -> bool:
    """Generate Gemini visuals only when the composition strategy calls for one."""
    return resolve_visual_plan(scene).needs_gemini_image


def should_plan_multimedia(state: dict) -> bool:
    """Avoid multimedia work when there are no exportable scenes."""
    scenes = list(state.get("completed_scenes") or [])
    if state.get("current_scene"):
        scenes.append(state["current_scene"])
    return bool(scenes)
