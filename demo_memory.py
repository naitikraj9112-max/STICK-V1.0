"""No-network checks for the memory manager and existing presentation pipeline."""

import inspect

from critic import CriticDecision
from memory import MemoryManager
from memory.models import MemoryRecord
from memory.repository import MemoryRepository, MemoryRepositoryError
from orchestrator import PresentationOrchestrator
from presentation_context import build_presentation_context
from planner import presenter_planner
from rendering import render_presentation
from semantic_detector import UpdateDecision
from state import new_presentation_state
from state_manager import apply_scene_action


class InMemoryRepository(MemoryRepository):
    """Small test double; production persistence is PostgreSQL, not this class."""

    def __init__(self):
        self.working = {}
        self.records = {}

    def get_working(self, scope): return dict(self.working.get((scope.user_id, scope.presentation_id, scope.session_id), {}))
    def save_working(self, scope, records): self.working[(scope.user_id, scope.presentation_id, scope.session_id)] = dict(records)
    def clear_session(self, scope): self.working.pop((scope.user_id, scope.presentation_id, scope.session_id), None)
    def list_records(self, user_id, presentation_id=None):
        return [record for record in self.records.values() if record.user_id == user_id and (presentation_id is None and record.presentation_id is None or presentation_id is not None and record.presentation_id in (None, presentation_id))]
    def save_record(self, record): self.records[record.id] = record
    def delete_record(self, record_id): self.records.pop(record_id, None)
    def health(self): return True


class FailingRepository(InMemoryRepository):
    def get_working(self, _scope): raise MemoryRepositoryError("unavailable")
    def save_working(self, _scope, _records): raise MemoryRepositoryError("unavailable")
    def clear_session(self, _scope): raise MemoryRepositoryError("unavailable")
    def list_records(self, _user_id, _presentation_id=None): raise MemoryRepositoryError("unavailable")
    def save_record(self, _record): raise MemoryRepositoryError("unavailable")


class MeaningfulDetector:
    def detect(self, _previous, latest):
        return UpdateDecision(should_plan=True, reason="ready", approved_content=latest, update_type="topic_change")


class ApprovingCritic:
    def review(self, _decision, _context): return CriticDecision(approved=True, reason="focused")


def integration_planner(_transcript, _state, relevant_memory=None, **_kwargs):
    assert isinstance(relevant_memory, list)
    return {"action": "start_new_scene", "kind": "cards", "title": "Architecture", "subtitle": "", "cards": ["Capture", "Reasoning", "Rendering"], "metrics": [], "primary_idea": "Three architecture layers", "presentation_stage": "architecture"}


def reset_state():
    return new_presentation_state()


def main():
    repository = InMemoryRepository()
    memory_a = MemoryManager(repository=repository, user_id="ada", presentation_id="deck-a", session_id="run-1")

    memory_a.remember("current_topic", "ExtractAI")
    assert memory_a.retrieve("current_topic") == "ExtractAI"
    memory_a.clear_session()
    assert memory_a.retrieve("current_topic") is None

    memory_a.record_event("product_introduced", "ExtractAI")
    first = memory_a.store_presentation_memory({"topic": "architecture", "important_detail": "three layers"}, 0.6)
    second = memory_a.store_presentation_memory({"topic": "architecture", "important_detail": "three layers"}, 0.9)
    architecture = [record for record in repository.list_records("ada", "deck-a") if record.type == "presentation_memory"]
    assert len(architecture) == 1 and first["id"] == second["id"] and architecture[0].importance == 0.9

    assert memory_a.remember_explicit_preference("I prefer minimal slides.")
    memory_b = MemoryManager(repository=repository, user_id="ada", presentation_id="deck-b", session_id="run-2")
    assert memory_b.get_preferences()["slide_style"] == "minimal slides"
    assert not [item for item in memory_b.get_relevant_memory("architecture") if item["type"] == "presentation_memory"]

    memory_a.set_preference("tone", "playful")
    relevant = memory_a.get_relevant_memory("Explain the architecture layers", limit=3)
    assert len(relevant) <= 3 and any(item["type"] == "presentation_memory" for item in relevant)
    assert not any(item["content"].get("value") == "playful" for item in relevant)

    restarted = MemoryManager(repository=repository, user_id="ada", presentation_id="deck-a", session_id="run-1")
    assert restarted.get_preferences()["slide_style"] == "minimal slides"
    context = build_presentation_context("Explain the architecture layers", {"current_scene": {}, "completed_scenes": [], "theme": {}, "metadata": {}}, relevant)
    assert context["relevant_memory"] == relevant and "MemoryManager" not in inspect.getsource(presenter_planner)

    state = {"current_scene": {}, "completed_scenes": [], "theme": {}, "metadata": {}}
    apply_scene_action({"action": "replace", "kind": "hero", "title": "ExtractAI", "primary_idea": "Introduction"}, state)
    apply_scene_action({"action": "start_new_scene", "kind": "cards", "title": "Architecture", "primary_idea": "Layers"}, state)
    assert render_presentation(state)["current_scene"]["component"] == "CardsScene"
    apply_scene_action({"action": "complete_scene", "kind": "cards", "title": "Architecture", "primary_idea": "Layers"}, state)
    assert state["current_scene"] == {} and len(state["completed_scenes"]) == 2

    reset_state()
    orchestrator = PresentationOrchestrator(
        planner=integration_planner,
        semantic_detector=MeaningfulDetector(),
        critic=ApprovingCritic(),
        memory_manager=MemoryManager(repository=repository, user_id="ada", presentation_id="deck-c", session_id="run-3"),
        session_id="run-3",
    )
    assert orchestrator.receive_transcript("The architecture has three layers")["scene"]["kind"] == "cards"
    assert any(record.type == "presentation_memory" for record in repository.list_records("ada", "deck-c"))

    fallback = PresentationOrchestrator(
        planner=integration_planner,
        semantic_detector=MeaningfulDetector(),
        critic=ApprovingCritic(),
        memory_manager=MemoryManager(repository=FailingRepository()),
        session_id="run-fallback",
    )
    assert fallback.receive_transcript("The architecture has three layers")["scene"]["kind"] == "cards"
    print("Agent memory demo passed.")


if __name__ == "__main__":
    main()
