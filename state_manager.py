"""Apply planner decisions to presentation state."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from presentation_cover import is_cover_scene
from tools import SceneDecision


def apply_scene_action(scene_update: dict, state: dict) -> dict:
    """Validate, build a draft, then atomically commit a lifecycle change."""
    validated = SceneDecision.model_validate(scene_update).model_dump()
    draft = deepcopy(state)
    action = validated["action"]

    if action == "replace":
        existing = draft["current_scene"]
        if is_cover_scene(existing):
            draft["current_scene"] = create_scene(validated)
        else:
            draft["current_scene"] = create_scene(validated, existing)
    elif action == "merge":
        draft["current_scene"] = merge_scene(validated, draft["current_scene"])
    elif action == "start_new_scene":
        complete_current_scene(draft)
        draft["current_scene"] = create_scene(validated)
    elif action == "complete_scene":
        draft["current_scene"] = merge_scene(validated, draft["current_scene"])
        complete_current_scene(draft)
    else:
        raise ValueError(f"Unsupported scene action: {action}")

    # State manager is the only writer of presentation-level narrative memory.
    stage = validated.get("presentation_stage")
    if stage:
        draft.setdefault("metadata", {})["presentation_stage"] = stage
    draft.setdefault("metadata", {})["presentation_summary"] = summary_from_state(draft)

    state.clear()
    state.update(draft)
    return state["current_scene"]


def create_scene(scene_update: dict, existing_scene: dict | None = None) -> dict:
    """Create an editing scene, preserving identity when it is revised."""
    now = timestamp()
    return {
        "id": existing_scene.get("id") if existing_scene else str(uuid4()),
        "kind": scene_update["kind"],
        "status": "editing",
        "created_at": existing_scene.get("created_at", now) if existing_scene else now,
        "updated_at": now,
        "content": scene_content(scene_update),
    }


def merge_scene(scene_update: dict, current_scene: dict) -> dict:
    """Merge planner content into the active scene, or create it when empty."""
    if not current_scene:
        return create_scene(scene_update)
    return {
        **current_scene,
        "kind": scene_update["kind"],
        "updated_at": timestamp(),
        "content": {**current_scene["content"], **scene_content(scene_update)},
    }


def complete_current_scene(state: dict) -> None:
    """Finalize and archive the active scene without overwriting it later."""
    current = state.get("current_scene")
    if current and not is_cover_scene(current):
        current["status"] = "completed"
        current["updated_at"] = timestamp()
        state["completed_scenes"].append(deepcopy(current))
        state["current_scene"] = {}


def scene_content(scene_update: dict) -> dict:
    card_items = scene_update.get("card_items") or []
    if not card_items and scene_update.get("cards"):
        card_items = [{"title": card, "body": "", "icon": "sparkles"} for card in scene_update.get("cards", [])]
    return {
        "title": scene_update["title"],
        "subtitle": scene_update.get("subtitle", ""),
        "cards": scene_update.get("cards") or [],
        "card_items": card_items,
        "metrics": scene_update.get("metrics") or [],
        "primary_idea": scene_update.get("primary_idea", ""),
        "icon": scene_update.get("icon", "sparkles"),
        "eyebrow": scene_update.get("eyebrow", ""),
        "accent": scene_update.get("accent", "sky"),
        "presentation_stage": scene_update.get("presentation_stage", "other"),
    }


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def summary_from_state(state: dict) -> dict:
    """Persist a small deterministic summary alongside state, not in agent memory."""
    metadata = state.get("metadata", {})
    return {
        "title": metadata.get("presentation_title", ""),
        "goal": metadata.get("presentation_goal", metadata.get("goal", "")),
        "audience": metadata.get("audience", ""),
        "current_stage": metadata.get("presentation_stage", "other"),
        "current_section": state.get("current_scene", {}).get("content", {}).get("title", ""),
        "completed_sections": [scene.get("content", {}).get("title", "") for scene in state.get("completed_scenes", [])[-6:]],
    }
