"""Registry for presentation sessions and their orchestrators."""

import logging
from threading import RLock

from config import DATABASE_URL
from multimedia import MultimediaManager
from multimedia.live_imagery import LiveImageryManager
from orchestrator import PresentationOrchestrator
from presentation_generator import PresentationGenerator
from session import (
    PresentationSession,
    complete_session,
    fail_session,
    mark_active,
    mark_connected,
    mark_disconnected,
    session_summary,
)

LOGGER = logging.getLogger(__name__)


class SessionManager:
    """Create and manage one orchestrator + state per presentation session."""

    def __init__(self, user_id: str = "local-user", presentation_id: str = "local-presentation"):
        self.user_id = user_id
        self.presentation_id = presentation_id
        self._sessions: dict[str, PresentationSession] = {}
        self._orchestrators: dict[str, PresentationOrchestrator] = {}
        self._lock = RLock()

    def create(self) -> PresentationSession:
        with self._lock:
            session = PresentationSession()
            self._sessions[session.session_id] = session
            self._orchestrators[session.session_id] = self._build_orchestrator(session)
            LOGGER.info("[%s] session created", session.session_id)
            return session

    def get(self, session_id: str) -> PresentationSession | None:
        return self._sessions.get(session_id)

    def get_orchestrator(self, session_id: str) -> PresentationOrchestrator | None:
        return self._orchestrators.get(session_id)

    def connect(self, session_id: str) -> PresentationSession | None:
        session = self.get(session_id)
        if not session:
            return None
        mark_connected(session)
        LOGGER.info("[%s] WebRTC connected", session_id)
        return session

    def note_transcript(self, session_id: str) -> None:
        session = self.get(session_id)
        if session and session.status in {"created", "connected"}:
            mark_active(session)

    def disconnect(self, session_id: str) -> None:
        with self._lock:
            session = self.get(session_id)
            if not session:
                return
            mark_disconnected(session)
            orchestrator = self._orchestrators.get(session_id)
            if orchestrator:
                orchestrator.finalize_session()
            LOGGER.info("[%s] session disconnected", session_id)

    def complete(self, session_id: str) -> None:
        with self._lock:
            session = self.get(session_id)
            if not session:
                return
            complete_session(session)
            orchestrator = self._orchestrators.get(session_id)
            if orchestrator:
                orchestrator.finalize_session()
            LOGGER.info("[%s] session completed", session_id)

    def shutdown_all(self) -> None:
        with self._lock:
            for session_id in list(self._sessions):
                session = self._sessions[session_id]
                if session.status not in {"completed", "failed"}:
                    complete_session(session)
                orchestrator = self._orchestrators.get(session_id)
                if orchestrator:
                    orchestrator.finalize_session()
            LOGGER.info("All sessions shut down (%s total)", len(self._sessions))

    def health_summary(self) -> dict:
        sessions = [session_summary(session) for session in self._sessions.values()]
        active = sum(1 for session in self._sessions.values() if session.status == "active")
        connected = sum(1 for session in self._sessions.values() if session.connection_status == "connected")
        return {"session_count": len(sessions), "active_sessions": active, "connected_sessions": connected, "sessions": sessions[-5:]}

    def sample_memory_health(self) -> str:
        orchestrator = next(iter(self._orchestrators.values()), None)
        if orchestrator:
            return orchestrator.memory_manager.health()
        if not DATABASE_URL:
            return "not_configured"
        try:
            from memory.repository import PostgresMemoryRepository

            repository = PostgresMemoryRepository()
            return "healthy" if repository.health() else "unavailable"
        except Exception:
            return "unavailable"

    def _build_orchestrator(self, session: PresentationSession) -> PresentationOrchestrator:
        generator = PresentationGenerator(session_id=session.session_id)
        multimedia = MultimediaManager(session_id=session.session_id)
        live_imagery = LiveImageryManager(session_id=session.session_id)
        return PresentationOrchestrator(
            session_id=session.session_id,
            user_id=self.user_id,
            presentation_id=self.presentation_id,
            presentation_generator=generator,
            multimedia_manager=multimedia,
            live_imagery_manager=live_imagery,
        )
