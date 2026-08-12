"""Welcome cover scene — mirrors ZeroPrep's initial stage before the first replace."""

from datetime import datetime, timezone

COVER_SCENE_ID = "stick-cover"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_cover_scene() -> dict:
    now = _timestamp()
    return {
        "id": COVER_SCENE_ID,
        "kind": "hero",
        "status": "editing",
        "created_at": now,
        "updated_at": now,
        "content": {
            "title": "ON-THE-FLY PRESENTATIONS",
            "subtitle": "Instant visuals + data cards",
            "tagline": "Speak. I'll build.",
            "cards": [],
            "card_items": [],
            "metrics": [],
            "primary_idea": "Live presentation",
            "icon": "sparkles",
            "eyebrow": "Stick",
            "accent": "lime",
            "presentation_stage": "introduction",
            "is_cover": True,
        },
    }


def is_cover_scene(scene: dict | None) -> bool:
    if not scene:
        return False
    if scene.get("id") == COVER_SCENE_ID:
        return True
    return bool((scene.get("content") or {}).get("is_cover"))


def deck_is_empty(state: dict | None) -> bool:
    if not state:
        return True
    if state.get("completed_scenes"):
        return False
    current = state.get("current_scene") or {}
    return not current or is_cover_scene(current)


def has_substantive_current(state: dict | None) -> bool:
    current = (state or {}).get("current_scene") or {}
    return bool(current) and not is_cover_scene(current)
