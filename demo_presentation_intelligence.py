"""Small no-network checks for context, critique, refinement, and state safety."""

from copy import deepcopy

from critic import CriticDecision
from memory import MemoryManager
from memory.repository import UnavailableMemoryRepository
from orchestrator import PresentationOrchestrator
from semantic_detector import UpdateDecision
from state import new_presentation_state


def scene(action, kind, title, *, cards=None, stage="other", primary_idea=None):
    """Keep demo decisions shaped exactly like planner tool output."""
    return {
        "action": action,
        "kind": kind,
        "title": title,
        "subtitle": "",
        "cards": cards or [],
        "metrics": [],
        "primary_idea": primary_idea or title,
        "presentation_stage": stage,
    }


class AlwaysMeaningfulDetector:
    """Avoid an LLM so this file checks orchestration deterministically."""

    def detect(self, _previous, latest):
        return UpdateDecision(
            should_plan=True,
            reason="Demo content is ready.",
            approved_content=latest,
            update_type="completed_idea",
        )


class DemoCritic:
    def review(self, decision, _context):
        if decision["title"] == "Crowded architecture":
            return CriticDecision(
                approved=False,
                reason="Six unrelated items crowd one architecture scene.",
                suggestions=["Start a focused new scene for the new idea."],
                issue="density",
            )
        return CriticDecision(approved=True, reason="Focused and concise.", suggestions=[])


def demo_planner(transcript, state, refinement_feedback=None):
    """A stand-in planner whose choices make the intended agent routing visible."""
    if transcript == "Welcome":
        return scene("replace", "hero", "Stick", stage="introduction", primary_idea="Product introduction")
    if transcript == "It turns speech into clear presentation scenes":
        assert state["current_scene"]["content"]["title"] == "Stick"
        return scene("merge", "hero", "Stick", stage="introduction", primary_idea="Product introduction")
    if transcript == "The architecture has capture, reasoning, and rendering":
        return scene(
            "start_new_scene", "cards", "Architecture", cards=["Capture", "Reasoning", "Rendering"],
            stage="architecture", primary_idea="Three architecture layers",
        )
    if transcript == "A crowded follow-up":
        if refinement_feedback:
            return scene("start_new_scene", "hero", "Why it matters", stage="solution", primary_idea="Presentation benefit")
        return scene(
            "merge", "cards", "Crowded architecture", cards=["One", "Two", "Three", "Four", "Five", "Six"],
            stage="architecture", primary_idea="Too many unrelated ideas",
        )
    raise AssertionError(f"Unexpected transcript: {transcript}")


def main():
    orchestrator = PresentationOrchestrator(
        planner=demo_planner,
        semantic_detector=AlwaysMeaningfulDetector(),
        critic=DemoCritic(),
        memory_manager=MemoryManager(repository=UnavailableMemoryRepository()),
        session_id="demo-intelligence",
    )
    state = orchestrator.presentation_state

    first = orchestrator.receive_transcript("Welcome")
    assert first["scene"]["kind"] == "hero"
    assert first["critic"]["approved"] is True
    scene_id = first["scene"]["id"]

    merged = orchestrator.receive_transcript("It turns speech into clear presentation scenes")
    assert merged["scene"]["id"] == scene_id
    assert state["metadata"]["presentation_stage"] == "introduction"

    architecture = orchestrator.receive_transcript("The architecture has capture, reasoning, and rendering")
    completed_before_crowd = deepcopy(state["completed_scenes"][0])
    assert architecture["scene"]["kind"] == "cards"
    assert len(state["completed_scenes"]) == 1

    crowded = orchestrator.receive_transcript("A crowded follow-up")
    assert crowded["critic"]["approved"] is False
    assert crowded["refined"] is True
    assert crowded["critic_after_refinement"]["approved"] is True
    assert state["current_scene"]["content"]["title"] == "Why it matters"
    assert state["completed_scenes"][0] == completed_before_crowd
    print("Presentation intelligence demo passed.")


if __name__ == "__main__":
    main()
