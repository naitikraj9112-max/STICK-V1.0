"""Map ZeroPrep-style director tool calls onto Stick scene state."""

from datetime import datetime, timezone

from iconography import DEFAULT_ACCENT, ICON_NAMES
from presentation_context import slide_language_instructions
from presentation_cover import deck_is_empty, has_substantive_current
from tools import SceneDecision

PRESENTATION_STAGES = [
    "introduction",
    "problem",
    "solution",
    "architecture",
    "workflow",
    "results",
    "conclusion",
    "other",
]

STAGE_LABELS = {
    "introduction": "Introduction",
    "problem": "The Problem",
    "solution": "The Solution",
    "architecture": "Architecture",
    "workflow": "How It Works",
    "results": "Results",
    "conclusion": "Conclusion",
    "other": "Key Point",
}

STAGE_DEFAULT_KIND = {
    "introduction": "hero",
    "problem": "hero",
    "solution": "cards",
    "architecture": "pipeline",
    "workflow": "pipeline",
    "results": "metric",
    "conclusion": "quote",
    "other": "hero",
}

DIRECTOR_INSTRUCTIONS = """You are Stick, a live presentation director that turns natural speech into a structured deck.

The presentation starts on the Stick welcome cover. The first substantive turn MUST use replace with a complete hero scene (title + subtitle). An introduction, product name, thesis, or agenda counts as substantive.

Decision policy (ZeroPrep-style):
- replace: new semantic beat — advances the deck with a new slide after the first hero exists.
- focus / merge_cards: UPDATE the current slide in place. Never create a new slide for these actions.
- merge_cards: when the speaker lists 2–4 related points on the SAME topic as the current slide. Keep the existing title unless the speaker names a new headline.
- hold: only for noise, filler, or exact repetition.

First slide rules (critical):
- First substantive speech → replace the welcome cover with kind=hero, presentation_stage=introduction.
- Put the product or topic name in title (3–8 words). Example: "Extract AI" not "New idea".
- Do NOT use merge_cards before a hero intro exists.
- Do NOT jump to problem/solution cards on the first turn.

Later turns:
- merge_cards ONLY when expanding the SAME slide topic — same headline, adding bullet points or cards.
- If the speaker names a NEW headline or NEW section → replace (creates a new slide). Never overwrite slide 1 with slide 2 content.
- Clear new section in speech → replace (new slide).
- Recompose after two or three substantive turns when the visual grammar should change.

Visual quality:
- Titles: crisp, 3–8 words. Subtitles: one clear supporting sentence.
- Cards: 2–4 items max, each with title + short body + semantic icon.

Never speak to the user. The function call is the response."""

def director_instructions(output_language: str | None = None) -> str:
    """Realtime session instructions with deck language policy appended."""
    return f"{DIRECTOR_INSTRUCTIONS}\n\n{slide_language_instructions(output_language)}"

CARD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "icon": {"type": "string", "enum": ICON_NAMES},
    },
    "required": ["title"],
}


def build_stage_scene_tool() -> dict:
    return {
        "type": "function",
        "name": "stage_scene",
        "description": "Hold, refine in place, or advance the structured live presentation.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["hold", "focus", "merge_cards", "replace"],
                    "description": "hold=no change; focus/merge_cards=refine current slide; replace=advance section or new visual beat.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["hero", "cards", "pipeline", "metric", "quote"],
                },
                "eyebrow": {"type": "string", "description": "Section label, max 6 words."},
                "title": {"type": "string", "description": "Headline, 3–8 words."},
                "subtitle": {"type": "string", "description": "Supporting sentence, max 22 words."},
                "icon": {"type": "string", "enum": ICON_NAMES},
                "accent": {"type": "string", "enum": list({"ember", "lime", "sky", "violet"})},
                "cards": {
                    "type": "array",
                    "items": CARD_ITEM_SCHEMA,
                    "description": "2–4 card objects for cards/pipeline kinds.",
                },
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                        "required": ["label", "value"],
                    },
                },
                "quote": {"type": "string", "description": "Memorable line for quote kind."},
                "attribution": {"type": "string"},
                "primary_idea": {"type": "string"},
                "presentation_stage": {
                    "type": "string",
                    "enum": PRESENTATION_STAGES,
                },
            },
            "required": ["action"],
        },
    }


def _fit_words(text: str, max_words: int) -> str:
    words = (text or "").split()
    if len(words) <= max_words:
        return (text or "").strip()
    return " ".join(words[:max_words]).strip()


def _normalize_cards(raw_cards: list) -> list[dict]:
    normalized = []
    for index, card in enumerate(raw_cards[:4]):
        if isinstance(card, str):
            normalized.append({"title": _fit_words(card, 5), "body": "", "icon": "sparkles"})
            continue
        if isinstance(card, dict):
            normalized.append({
                "title": _fit_words(str(card.get("title", f"Point {index + 1}")), 5),
                "body": _fit_words(str(card.get("body", "")), 20),
                "icon": card.get("icon") if card.get("icon") in ICON_NAMES else "sparkles",
            })
    return normalized


def _stage_index(stage: str) -> int:
    try:
        return PRESENTATION_STAGES.index(stage)
    except ValueError:
        return len(PRESENTATION_STAGES) - 1


def _scene_age_seconds(scene: dict) -> float | None:
    updated_at = scene.get("updated_at") or scene.get("created_at")
    if not updated_at:
        return None
    try:
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, TypeError):
        return None


def apply_structured_scene_guard(scene_update: dict, state: dict, min_new_scene_seconds: float = 15.0) -> dict:
    """Prefer in-place refinement; allow new slides when section/title/kind clearly advances."""
    action = scene_update.get("action")
    if action != "start_new_scene":
        return scene_update

    current_scene = state.get("current_scene") or {}
    if not current_scene:
        return scene_update

    metadata = state.get("metadata") or {}
    current_content = current_scene.get("content") or {}
    current_stage = current_content.get("presentation_stage") or metadata.get("presentation_stage", "other")
    new_stage = scene_update.get("presentation_stage", "other")
    new_kind = scene_update.get("kind", "hero")
    current_kind = current_scene.get("kind", "hero")
    current_title = _fit_words(current_content.get("title") or "", 8).strip().lower()
    new_title = _fit_words(scene_update.get("title") or "", 8).strip().lower()

    stage_advanced = (
        new_stage in STAGE_LABELS
        and new_stage != "other"
        and _stage_index(new_stage) > _stage_index(current_stage)
    )
    kind_shift = new_kind != current_kind
    title_changed = bool(new_title and current_title and new_title != current_title)

    if stage_advanced or kind_shift or title_changed:
        return scene_update

    cards = scene_update.get("cards") or []
    min_dwell = min(min_new_scene_seconds, 4.0) if len(cards) >= 2 else min_new_scene_seconds
    age = _scene_age_seconds(current_scene)
    if age is not None and age < min_dwell:
        return {**scene_update, "action": "merge"}

    # Dwell time passed — allow the new slide to be created
    return scene_update


def normalize_realtime_payload(payload: dict, has_current_scene: bool, state: dict | None = None) -> dict | None:
    """Convert a director tool payload into a SceneDecision dict, or None for hold."""
    director_action = payload.get("action", "focus")
    if director_action == "hold":
        return None

    current_content = ((state or {}).get("current_scene") or {}).get("content") or {}
    substantive = has_substantive_current(state) if state else has_current_scene
    empty_deck = deck_is_empty(state) if state else not has_current_scene

    raw_title = payload.get("title") or payload.get("quote") or ""
    current_title = _fit_words(current_content.get("title") or "", 8)
    new_title = _fit_words(raw_title or "", 8)
    title_advances = (
        substantive
        and new_title
        and current_title
        and new_title.strip().lower() != current_title.strip().lower()
    )
    if title_advances and director_action == "merge_cards":
        director_action = "replace"

    if empty_deck and director_action in {"focus", "merge_cards"}:
        director_action = "replace"

    stage = payload.get("presentation_stage") or ("introduction" if empty_deck else "other")
    if stage not in PRESENTATION_STAGES:
        stage = "other"

    if director_action == "focus":
        stick_action = "merge"
    elif director_action == "merge_cards":
        stick_action = "merge"
    elif director_action == "replace":
        stick_action = "start_new_scene" if substantive else "replace"
    else:
        stick_action = director_action if director_action in {"merge", "start_new_scene", "complete_scene", "replace"} else "merge"

    kind = payload.get("kind") or STAGE_DEFAULT_KIND.get(stage, "hero")
    if empty_deck:
        kind = "hero"
        stage = "introduction"
        stick_action = "replace"
    elif director_action == "merge_cards" and not payload.get("kind"):
        kind = "cards"

    current_content = ((state or {}).get("current_scene") or {}).get("content") or {}
    is_in_place_update = director_action in {"focus", "merge_cards"} and substantive

    raw_title = payload.get("title") or payload.get("quote") or ""
    if is_in_place_update and not raw_title:
        title = _fit_words(current_content.get("title") or "New idea", 8)
    else:
        title = _fit_words(raw_title or current_content.get("title") or "New idea", 8)

    raw_subtitle = payload.get("subtitle") or payload.get("caption") or ""
    if is_in_place_update and not raw_subtitle:
        subtitle = _fit_words(current_content.get("subtitle") or "", 22)
    else:
        subtitle = _fit_words(raw_subtitle or current_content.get("subtitle") or "", 22)

    cards_raw = [] if empty_deck else (payload.get("cards") or [])
    cards = _normalize_cards(cards_raw)

    if kind == "quote" and payload.get("quote"):
        title = _fit_words(payload["quote"], 12)
        subtitle = _fit_words(payload.get("attribution") or subtitle, 22)

    if kind == "pipeline" and cards:
        cards = [{"title": c["title"], "body": c.get("body", ""), "icon": c.get("icon", "arrow-right")} for c in cards]

    card_strings = [f"{c['title']}: {c['body']}".strip(": ") if c.get("body") else c["title"] for c in cards]
    raw_eyebrow = payload.get("eyebrow") or ""
    if is_in_place_update and not raw_eyebrow:
        eyebrow = _fit_words(current_content.get("eyebrow") or STAGE_LABELS.get(stage, ""), 6)
    else:
        eyebrow = _fit_words(raw_eyebrow or STAGE_LABELS.get(stage, ""), 6)

    scene_update = {
        "action": stick_action,
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "cards": card_strings,
        "card_items": cards,
        "metrics": payload.get("metrics") or [],
        "primary_idea": _fit_words(payload.get("primary_idea") or title, 24),
        "presentation_stage": stage,
        "icon": payload.get("icon") if payload.get("icon") in ICON_NAMES else "sparkles",
        "eyebrow": eyebrow,
        "accent": payload.get("accent") if payload.get("accent") in {"ember", "lime", "sky", "violet"} else DEFAULT_ACCENT,
    }
    SceneDecision.model_validate(scene_update)

    if state is not None:
        from config import MIN_NEW_SCENE_SECONDS

        scene_update = apply_structured_scene_guard(scene_update, state, MIN_NEW_SCENE_SECONDS)

    return scene_update
