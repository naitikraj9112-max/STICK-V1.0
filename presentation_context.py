"""Build a small read-only view of presentation state for the planner."""

from copy import deepcopy

from config import PRESENTATION_LANGUAGE

LANGUAGE_LABELS = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "hi": "Hindi",
    "ja": "Japanese",
    "zh": "Chinese",
}


def normalize_output_language(value: str | None) -> str:
    raw = (value or PRESENTATION_LANGUAGE or "en").strip().lower()
    return raw.split("-")[0] or "en"


def slide_language_instructions(default_language: str | None = None) -> str:
    """Shared language policy for realtime director, planner, and critic prompts."""
    code = normalize_output_language(default_language)
    label = LANGUAGE_LABELS.get(code, code)
    return f"""Language (critical):
- Write ALL slide copy (title, subtitle, eyebrow, cards, metrics, quotes) in the same language the speaker uses.
- Never translate slide copy into a different language unless the speaker clearly switched languages.
- If the speaker's language is ambiguous, use {label} ({code}) as the deck default.
- Do not mix languages on one slide unless the speaker explicitly did so in speech."""


def preferred_output_language(metadata: dict | None) -> str:
    return normalize_output_language((metadata or {}).get("output_language"))


def _compact_scene(scene: dict) -> dict:
    """Keep scene context useful without forwarding render-sized history to the LLM."""
    content = scene.get("content", {})
    return {
        "id": scene.get("id"), "kind": scene.get("kind"), "status": scene.get("status"),
        "title": content.get("title", ""), "subtitle": content.get("subtitle", "")[:180],
        "primary_idea": content.get("primary_idea", ""), "cards": (content.get("cards") or [])[:5],
        "metrics": (content.get("metrics") or [])[:3],
    }


def build_presentation_summary(state: dict) -> dict:
    """Deterministic state summary; no additional LLM call is needed."""
    metadata = state.get("metadata", {})
    completed = state.get("completed_scenes", [])
    return {
        "title": metadata.get("presentation_title", ""),
        "goal": metadata.get("presentation_goal", metadata.get("goal", "")),
        "audience": metadata.get("audience", ""),
        "current_stage": metadata.get("presentation_stage", "other"),
        "current_section": _compact_scene(state.get("current_scene", {})).get("title", ""),
        "completed_sections": [scene.get("content", {}).get("title", "") for scene in completed[-6:]],
        "completed_count": len(completed),
    }


def build_presentation_context(
    transcript_chunk: str, state: dict, relevant_memory: dict | None = None
) -> dict:
    """Combine read-only state and a small retrieved memory subset for planning."""
    metadata = deepcopy(state.get("metadata", {}))
    summary = build_presentation_summary(state)
    return {
        "transcript_chunk": transcript_chunk,
        "current_scene": _compact_scene(state.get("current_scene", {})),
        "completed_scenes": [_compact_scene(scene) for scene in state.get("completed_scenes", [])[-3:]],
        "metadata": metadata,
        "presentation_metadata": metadata,
        "presentation_goal": metadata.get("presentation_goal", metadata.get("goal", "")),
        "current_stage": metadata.get("presentation_stage", "other"),
        "narrative_stage": metadata.get("presentation_stage", "other"),
        "presentation_summary": summary,
        "output_language": preferred_output_language(metadata),
        # Memory is deliberately separate from state and is supplied by Python.
        "relevant_memory": deepcopy(relevant_memory or {}),
    }
