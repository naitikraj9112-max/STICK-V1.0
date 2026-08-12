"""High-level, failure-tolerant memory API used by the orchestrator."""

import logging
import re
from datetime import datetime, timezone

from memory.models import MemoryCandidate, MemoryRecord, MemoryScope
from memory.repository import MemoryRepository, PostgresMemoryRepository, UnavailableMemoryRepository
from memory.retrieval import LexicalMemoryRetrieval

LOGGER = logging.getLogger(__name__)


class MemoryManager:
    """Coordinates scoped storage and retrieval without exposing PostgreSQL to callers."""

    def __init__(
        self,
        repository: MemoryRepository | None = None,
        retrieval=None,
        user_id: str = "local-user",
        presentation_id: str = "local-presentation",
        session_id: str = "local-session",
    ):
        self.scope = MemoryScope(user_id=user_id, presentation_id=presentation_id, session_id=session_id)
        try:
            self.repository = repository or PostgresMemoryRepository()
        except Exception as error:
            LOGGER.warning("Memory is unavailable; continuing without it: %s", error)
            self.repository = UnavailableMemoryRepository()
        self.retrieval = retrieval or LexicalMemoryRetrieval()

    def remember(self, key: str, value, importance: float = 0.5) -> None:
        records = self._working_records()
        existing = records.get(key)
        fields = {
            "type": "working_memory", "content": {"key": key, "value": value}, "importance": importance,
            "user_id": self.scope.user_id, "presentation_id": self.scope.presentation_id, "session_id": self.scope.session_id,
            "created_at": existing.created_at if existing else datetime.now(timezone.utc),
        }
        if existing:
            fields["id"] = existing.id
        records[key] = MemoryRecord(**fields)
        self._safe_write(lambda: self.repository.save_working(self.scope, records))

    def retrieve(self, key: str, default=None):
        record = self._working_records().get(key)
        return record.content["value"] if record else default

    def record_event(self, event: str, topic: str = "", details: dict | None = None, importance: float = 0.6) -> dict:
        record = self._upsert_record(
            "episodic_memory", {"event": event, "topic": topic, "details": details or {}}, importance
        )
        return record.model_dump(mode="json")

    def store_presentation_memory(self, content: dict, importance: float = 0.6) -> dict:
        return self._upsert_record("presentation_memory", content, importance).model_dump(mode="json")

    def store_candidate(self, candidate: MemoryCandidate | None) -> dict | None:
        """Python applies this bounded persistence decision after a successful update."""
        if not candidate or not candidate.should_store:
            return None
        return self._upsert_record(candidate.type, candidate.content, candidate.importance).model_dump(mode="json")

    def get_preferences(self) -> dict:
        records = self._safe_records(self.scope.user_id, None)
        return {record.content["key"]: record.content["value"] for record in records if record.type == "user_preference"}

    def set_preference(self, key: str, value, importance: float = 0.8) -> None:
        self._upsert_record("user_preference", {"key": key, "value": value}, importance, presentation_id=None)

    def remember_explicit_preference(self, text: str) -> bool:
        match = re.search(r"\bi prefer\s+(.+?)[.!?]*$", text.strip(), re.IGNORECASE)
        if not match:
            return False
        value = match.group(1).strip()
        lowered = value.lower()
        key = "slide_style" if "slide" in lowered else "theme" if "theme" in lowered else "tone" if "tone" in lowered else "slide_density" if ("dense" in lowered or "concise" in lowered) else "presentation_preference"
        self.set_preference(key, value)
        return True

    def clear_session(self) -> None:
        self._safe_write(lambda: self.repository.clear_session(self.scope))

    def get_relevant_memory(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve only scoped working facts, presentation memories, then preferences."""
        working = list(self._working_records().values())
        records = working + self._safe_records(self.scope.user_id, self.scope.presentation_id)
        try:
            return self.retrieval.retrieve(query, records, self.scope.presentation_id, limit)
        except Exception as error:  # A future semantic retriever must not stop the presentation.
            LOGGER.warning("Memory retrieval failed; continuing without memory: %s", error)
            return []

    def health(self) -> str:
        """Optional memory health; callers must treat it as degraded, not fatal."""
        try:
            return "healthy" if self.repository.health() else "unavailable"
        except Exception:
            return "unavailable"

    def _working_records(self) -> dict[str, MemoryRecord]:
        try:
            return self.repository.get_working(self.scope)
        except Exception as error:
            LOGGER.warning("Memory read failed; continuing without memory: %s", error)
            return {}

    def _safe_records(self, user_id: str, presentation_id: str | None) -> list[MemoryRecord]:
        try:
            return self.repository.list_records(user_id, presentation_id)
        except Exception as error:
            LOGGER.warning("Memory read failed; continuing without memory: %s", error)
            return []

    def _safe_write(self, operation) -> None:
        try:
            operation()
        except Exception as error:
            LOGGER.warning("Memory write failed; presentation continues: %s", error)

    def _upsert_record(self, memory_type: str, content: dict, importance: float, presentation_id: str | None = "use_scope") -> MemoryRecord:
        target_presentation = self.scope.presentation_id if presentation_id == "use_scope" else presentation_id
        matches = [
            record for record in self._safe_records(self.scope.user_id, target_presentation)
            if record.type == memory_type and record.content == content
        ]
        existing = matches[0] if matches else None
        fields = {
            "type": memory_type, "content": content,
            "importance": max(importance, existing.importance) if existing else importance,
            "user_id": self.scope.user_id, "presentation_id": target_presentation,
            "session_id": self.scope.session_id if target_presentation else None,
            "created_at": existing.created_at if existing else datetime.now(timezone.utc),
            "metadata": existing.metadata if existing else {},
        }
        if existing:
            fields["id"] = existing.id
        record = MemoryRecord(**fields)
        self._safe_write(lambda: self.repository.save_record(record))
        return record
