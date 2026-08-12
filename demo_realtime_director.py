"""Guard tests for ZeroPrep-style realtime director behavior."""

from copy import deepcopy

from presentation_cover import create_cover_scene, deck_is_empty
from realtime_director import apply_structured_scene_guard, director_instructions, normalize_realtime_payload
from presentation_context import slide_language_instructions
from session import new_presentation_state


def _state_with_scene(stage="introduction", age_seconds_ago=None, title="Intro"):
    state = new_presentation_state()
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    ts = (now - timedelta(seconds=age_seconds_ago or 30)).isoformat()
    state["current_scene"] = {
        "id": "scene-1",
        "kind": "hero",
        "status": "editing",
        "created_at": ts,
        "updated_at": ts,
        "content": {"title": title, "subtitle": "Subtitle", "presentation_stage": stage, "eyebrow": "Intro"},
    }
    state["metadata"]["presentation_stage"] = stage
    return state


def test_starts_with_cover():
    state = new_presentation_state()
    assert deck_is_empty(state)
    assert state["current_scene"]["content"]["is_cover"] is True


def test_merge_cards_on_empty_deck_becomes_hero_replace():
    state = new_presentation_state()
    payload = {
        "action": "merge_cards",
        "kind": "cards",
        "title": "Extract AI",
        "cards": [{"title": "PDFs", "body": "Reports"}],
        "presentation_stage": "problem",
    }
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "replace"
    assert normalized["kind"] == "hero"
    assert normalized["title"] == "Extract AI"
    assert normalized["cards"] == []


def test_merge_cards_preserves_title():
    state = _state_with_scene(title="Extract AI")
    payload = {
        "action": "merge_cards",
        "cards": [{"title": "PDFs", "body": "Reports"}, {"title": "Invoices", "body": "Contracts"}],
        "presentation_stage": "problem",
    }
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "merge"
    assert normalized["kind"] == "cards"
    assert normalized["title"] == "Extract AI"


def test_replace_on_cover_is_replace_not_new_scene():
    state = new_presentation_state()
    payload = {"action": "replace", "kind": "hero", "title": "Extract AI", "subtitle": "Live extraction", "presentation_stage": "introduction"}
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "replace"


def test_rapid_replace_same_topic_becomes_merge():
    state = _state_with_scene(age_seconds_ago=2, title="Intro")
    payload = {"action": "replace", "kind": "hero", "title": "Intro", "presentation_stage": "introduction"}
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "merge"


def test_rapid_replace_new_title_starts_scene():
    state = _state_with_scene(age_seconds_ago=2, title="Intro")
    payload = {"action": "replace", "kind": "hero", "title": "Next", "presentation_stage": "problem"}
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "start_new_scene"


def test_stage_advance_allowed_after_dwell():
    state = _state_with_scene(age_seconds_ago=20)
    payload = {"action": "replace", "kind": "hero", "title": "Problem", "presentation_stage": "problem"}
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "start_new_scene"


def test_merge_cards_new_title_starts_scene():
    state = _state_with_scene(title="SpaceX Overview")
    payload = {
        "action": "merge_cards",
        "title": "Falcon Rockets",
        "cards": [{"title": "Reusable", "body": "First stage landing"}],
        "presentation_stage": "solution",
    }
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "start_new_scene"
    assert normalized["title"] == "Falcon Rockets"


def test_hold_returns_none():
    assert normalize_realtime_payload({"action": "hold"}, True, _state_with_scene()) is None


def test_focus_merges_in_place():
    state = _state_with_scene()
    payload = {"action": "focus", "kind": "hero", "title": "Stick", "presentation_stage": "introduction"}
    normalized = normalize_realtime_payload(payload, True, state)
    assert normalized["action"] == "merge"


def test_director_language_policy():
    instructions = director_instructions("en")
    assert "same language the speaker uses" in instructions
    assert "use English (en) as the deck default" in slide_language_instructions("en")


def main():
    test_starts_with_cover()
    test_merge_cards_on_empty_deck_becomes_hero_replace()
    test_merge_cards_preserves_title()
    test_replace_on_cover_is_replace_not_new_scene()
    test_rapid_replace_same_topic_becomes_merge()
    test_rapid_replace_new_title_starts_scene()
    test_stage_advance_allowed_after_dwell()
    test_merge_cards_new_title_starts_scene()
    test_hold_returns_none()
    test_focus_merges_in_place()
    test_director_language_policy()
    print("Realtime director guard demo passed.")


if __name__ == "__main__":
    main()
