"""Speech vs typed transcript should reach the same planner path."""

from critic import CriticDecision
from demo_memory import InMemoryRepository
from memory import MemoryManager
from orchestrator import PresentationOrchestrator
from presentation_cover import is_cover_scene
from presentation_generator import PresentationGenerator
from semantic_detector import UpdateDecision


class LocalDetector:
    def detect(self, _previous, latest):
        words = latest.split()
        complete = len(words) >= 6
        return UpdateDecision(
            should_plan=complete,
            reason="local",
            approved_content=latest,
            update_type="completed_idea" if complete else "incomplete",
        )


class LocalCritic:
    def review(self, _decision, _context):
        return CriticDecision(approved=True, reason="ok")


def local_planner(transcript, state, **_kwargs):
    current = state.get("current_scene")
    if not current or is_cover_scene(current):
        return {
            "action": "replace",
            "kind": "hero",
            "title": " ".join(transcript.split()[:6]) or "Idea",
            "subtitle": transcript[:80],
            "cards": [],
            "metrics": [],
            "primary_idea": transcript[:120],
            "presentation_stage": "introduction",
        }
    return {
        "action": "start_new_scene",
        "kind": "cards",
        "title": "Next idea",
        "subtitle": transcript[:80],
        "cards": [transcript[:40]],
        "metrics": [],
        "primary_idea": transcript[:120],
        "presentation_stage": "solution",
    }


def make_orchestrator():
    return PresentationOrchestrator(
        planner=local_planner,
        semantic_detector=LocalDetector(),
        critic=LocalCritic(),
        memory_manager=MemoryManager(repository=InMemoryRepository(), session_id="speech-test"),
        presentation_generator=PresentationGenerator(session_id="speech-test", adapter=None),
        session_id="speech-test",
    )


def test_combine_transcript_grows_snapshot_and_joins_fragments():
    assert PresentationOrchestrator.combine_transcript("", "Hello") == "Hello"
    assert PresentationOrchestrator.combine_transcript("Hello", "Hello everyone") == "Hello everyone"
    assert PresentationOrchestrator.combine_transcript("Hello everyone", "today") == "Hello everyone today"
    assert PresentationOrchestrator.combine_transcript("Hello everyone today", "Hello") == "Hello everyone today"


def test_typed_sentence_updates_scene():
    orchestrator = make_orchestrator()
    result = orchestrator.receive_transcript(
        "Welcome to Stick, a live presentation engine built from speech.",
        "typed-1",
        True,
    )
    assert result["scene_updated"] is True
    assert not is_cover_scene(orchestrator.presentation_state["current_scene"])


def test_speech_fragments_reach_the_same_planner():
    orchestrator = make_orchestrator()
    first = orchestrator.receive_transcript("Welcome to", "speech-1", True)
    assert first["planned"] is False
    assert first["success"] is True
    second = orchestrator.receive_transcript("Stick a live presentation engine", "speech-2", True)
    assert second["scene_updated"] is True
    scene = orchestrator.presentation_state["current_scene"]
    assert not is_cover_scene(scene)
    assert "Stick" in scene["content"]["subtitle"] or "Stick" in scene["content"]["title"]


def test_short_spoken_slide_direction_builds_next_scene():
    class RejectingDetector:
        def detect(self, _previous, latest):
            return UpdateDecision(
                should_plan=False,
                reason="Treat as a meta-instruction.",
                approved_content=latest,
                update_type="incomplete",
            )

    orchestrator = PresentationOrchestrator(
        planner=local_planner,
        semantic_detector=RejectingDetector(),
        critic=LocalCritic(),
        memory_manager=MemoryManager(repository=InMemoryRepository(), session_id="spoken-direction-test"),
        presentation_generator=PresentationGenerator(session_id="spoken-direction-test", adapter=None),
        session_id="spoken-direction-test",
    )
    orchestrator.receive_transcript("Welcome to Stick, a live presentation engine.", "seed-1", True)
    result = orchestrator.receive_transcript(
        "Introduce the topic and why it matters.", "direction-1", True
    )
    assert result["scene_updated"] is True
    assert result["execution"]["planner_called"] is True


def test_growing_speech_snapshot_is_not_treated_as_duplicate():
    orchestrator = make_orchestrator()
    orchestrator.receive_transcript("Welcome to Stick", "snap-1", True)
    result = orchestrator.receive_transcript(
        "Welcome to Stick a live presentation engine for founders",
        "snap-2",
        True,
    )
    assert result["scene_updated"] is True


def test_interim_flag_still_ignored_until_final():
    orchestrator = make_orchestrator()
    result = orchestrator.receive_transcript("Welcome to Stick a live presentation engine", "tmp-1", False)
    assert result["planned"] is False
    assert is_cover_scene(orchestrator.presentation_state["current_scene"])


def test_failed_planner_allows_retry_of_same_words():
    calls = {"n": 0}

    def flaky_planner(transcript, state, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("planner outage")
        return local_planner(transcript, state)

    orchestrator = PresentationOrchestrator(
        planner=flaky_planner,
        semantic_detector=LocalDetector(),
        critic=LocalCritic(),
        memory_manager=MemoryManager(repository=InMemoryRepository(), session_id="retry-test"),
        presentation_generator=PresentationGenerator(session_id="retry-test", adapter=None),
        session_id="retry-test",
    )
    text = "Welcome to Stick a live presentation engine"
    first = orchestrator.receive_transcript(text, "retry-1", True)
    assert first["success"] is False
    second = orchestrator.receive_transcript(text, "retry-2", True)
    assert second["scene_updated"] is True
