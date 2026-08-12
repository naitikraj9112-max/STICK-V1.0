"""Temporary Neon CRUD verification. It deletes its clearly labelled test record."""

from critic import CriticDecision
from memory import MemoryManager
from memory.models import MemoryRecord
from memory.repository import PostgresMemoryRepository
from orchestrator import PresentationOrchestrator
from semantic_detector import UpdateDecision


TEST_USER = "__neon_connection_test__"
TEST_PRESENTATION = "__temporary_memory_test__"


class Detector:
    def detect(self, _previous, transcript):
        return UpdateDecision(should_plan=True, reason="test", approved_content=transcript, update_type="topic_change")


class Critic:
    def review(self, _decision, _context):
        return CriticDecision(approved=True, reason="test")


def planner(_transcript, _state, relevant_memory=None, **_kwargs):
    assert any(item["content"].get("topic") == "architecture" for item in relevant_memory)
    return {"action": "start_new_scene", "kind": "cards", "title": "Architecture", "subtitle": "", "cards": ["One", "Two", "Three"], "metrics": [], "primary_idea": "Three layers", "presentation_stage": "architecture"}


def main():
    repository = PostgresMemoryRepository()
    record = MemoryRecord(
        type="presentation_memory",
        user_id=TEST_USER,
        presentation_id=TEST_PRESENTATION,
        session_id="test-session",
        content={"topic": "temporary Neon connection test", "important_detail": "delete after verification"},
        importance=0.1,
        metadata={"temporary": True},
    )
    try:
        repository.save_record(record)  # Insert.
        found = [item for item in repository.list_records(TEST_USER, TEST_PRESENTATION) if item.id == record.id]
        assert len(found) == 1 and found[0].content["topic"] == "temporary Neon connection test"

        record.importance = 0.2
        record.metadata["updated"] = True
        repository.save_record(record)  # Update.
        updated = [item for item in repository.list_records(TEST_USER, TEST_PRESENTATION) if item.id == record.id][0]
        assert updated.importance == 0.2 and updated.metadata["updated"] is True

        PostgresMemoryRepository()  # Reconnect and re-run idempotent setup.
        print("Neon connection, schema, insert, retrieval, update, and reconnect passed.")

        # Real repository integration with the existing orchestration flow.
        manager = MemoryManager(repository=repository, user_id=TEST_USER, presentation_id=TEST_PRESENTATION, session_id="test-session")
        manager.store_presentation_memory({"topic": "architecture", "important_detail": "three layers"})
        orchestrator = PresentationOrchestrator(
            planner=planner, semantic_detector=Detector(), critic=Critic(), memory_manager=manager, session_id="test-session"
        )
        assert orchestrator.receive_transcript("Explain the architecture")["scene"]["kind"] == "cards"
        print("Neon-backed detector, retrieval, planner, critic, state, and recording flow passed.")
    finally:
        for item in repository.list_records(TEST_USER, TEST_PRESENTATION):
            repository.delete_record(item.id)  # Cleanup every temporary test record.
    assert not repository.list_records(TEST_USER, TEST_PRESENTATION)
    print("Temporary Neon record cleanup passed.")


if __name__ == "__main__":
    main()
