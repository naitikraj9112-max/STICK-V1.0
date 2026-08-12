"""No-network reliability checks for the existing production pipeline."""

from copy import deepcopy

from critic import CriticDecision
from demo_memory import InMemoryRepository
from memory import MemoryManager
from orchestrator import PresentationOrchestrator
from presentation_context import build_presentation_context
from reliability import retry_call
from rendering import render_presentation
from semantic_detector import UpdateDecision
from state import new_presentation_state
from state_manager import apply_scene_action


def scene():
    return {"action": "replace", "kind": "hero", "title": "Reliable", "subtitle": "", "cards": [], "metrics": [], "primary_idea": "Reliability", "presentation_stage": "introduction"}


class Detector:
    def __init__(self, fail=False): self.fail, self.calls = fail, 0
    def detect(self, _previous, latest):
        self.calls += 1
        if self.fail: raise TimeoutError("temporary detector outage")
        return UpdateDecision(should_plan=latest != "partial", reason="ready", approved_content=latest, update_type="completed_idea" if latest != "partial" else "incomplete")


class ApprovingCritic:
    def review(self, _scene, _context): return CriticDecision(approved=True, reason="ok")


class BrokenCritic:
    def review(self, _scene, _context): raise TimeoutError("critic outage")


def planner(_content, _state, **_kwargs): return scene()
def complex_planner(_content, _state, **_kwargs):
    return {**scene(), "action": "start_new_scene", "kind": "cards", "cards": ["One", "Two", "Three", "Four"], "presentation_stage": "architecture"}
def bad_planner(_content, _state, **_kwargs): return {"action": "replace"}
def broken_planner(_content, _state, **_kwargs): raise TimeoutError("planner outage")


def make_orchestrator(detector, planner_fn=planner, critic=None, session_id="demo-reliability"):
    return PresentationOrchestrator(
        planner=planner_fn,
        semantic_detector=detector,
        critic=critic or ApprovingCritic(),
        memory_manager=MemoryManager(repository=InMemoryRepository()),
        session_id=session_id,
    )


def main():
    attempts = {"count": 0}
    def transient():
        attempts["count"] += 1
        if attempts["count"] == 1: raise TimeoutError("temporary")
        return "recovered"
    assert retry_call(transient, "test") == "recovered" and attempts["count"] == 2

    detector = Detector()
    orchestrator = make_orchestrator(detector, session_id="reliability-1")
    first = orchestrator.receive_transcript("A complete idea", "event-1")
    duplicate = orchestrator.receive_transcript("A complete idea", "event-1")
    incomplete = orchestrator.receive_transcript("partial", "event-2")
    assert first["planned"] and first["planner_called"] and first["memory_retrieved"] and not first["critic_called"]
    assert not duplicate["planned"] and not incomplete["planned"] and not incomplete["memory_retrieved"] and detector.calls == 2

    failure_orchestrator = make_orchestrator(Detector(), broken_planner, session_id="reliability-2")
    before = deepcopy(failure_orchestrator.presentation_state)
    failure = failure_orchestrator.receive_transcript("Plan this", "event-3")
    assert not failure["planned"] and failure_orchestrator.presentation_state == before

    fallback = make_orchestrator(Detector(), complex_planner, BrokenCritic(), session_id="reliability-3")
    assert fallback.receive_transcript("Critic down", "event-4")["planned"]

    invalid_orchestrator = make_orchestrator(Detector(), bad_planner, session_id="reliability-4")
    before = deepcopy(invalid_orchestrator.presentation_state)
    invalid = invalid_orchestrator.receive_transcript("Bad scene", "event-5")
    assert not invalid["planned"] and invalid_orchestrator.presentation_state == before
    isolated = new_presentation_state()
    try:
        apply_scene_action({"action": "replace"}, isolated)
    except Exception:
        pass
    assert isolated["completed_scenes"] == []
    assert isolated["current_scene"]["content"]["is_cover"] is True
    assert render_presentation({"bad": "state"})["success"] is False

    compact_state = {"current_scene": {}, "completed_scenes": [{"id": str(number), "kind": "hero", "status": "completed", "content": {"title": f"Section {number}", "cards": list(range(10))}} for number in range(8)], "theme": {}, "metadata": {"presentation_goal": "Explain reliability"}}
    compact = build_presentation_context("Current approved update", compact_state, [{"type": "user_preference"}])
    assert len(compact["completed_scenes"]) == 3 and len(compact["presentation_summary"]["completed_sections"]) == 6
    print("Production reliability demo passed.")


if __name__ == "__main__":
    main()
