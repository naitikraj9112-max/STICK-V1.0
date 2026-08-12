"""Presentation session lifecycle — separate from presentation content state."""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from presentation_cover import create_cover_scene
from presentation_context import normalize_output_language
from config import PRESENTATION_LANGUAGE

SessionStatus = Literal["created", "connected", "active", "disconnected", "completed", "failed"]
ConnectionStatus = Literal["disconnected", "connected"]


def new_presentation_state() -> dict:
    """Return a fresh presentation state dict for one session."""
    return {
        "current_scene": create_cover_scene(),
        "completed_scenes": [],
        "theme": {},
        "metadata": {
            "presentation_stage": "introduction",
            "output_language": normalize_output_language(PRESENTATION_LANGUAGE),
        },
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PresentationSession(BaseModel):
    """Lifecycle of one running presentation interaction."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: SessionStatus = "created"
    connection_status: ConnectionStatus = "disconnected"
    execution_metadata: dict = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def touch(self) -> None:
        self.updated_at = utc_now()


def mark_connected(session: PresentationSession) -> None:
    session.connection_status = "connected"
    if session.status == "created":
        session.status = "connected"
    session.touch()


def mark_active(session: PresentationSession) -> None:
    session.status = "active"
    session.touch()


def mark_disconnected(session: PresentationSession) -> None:
    session.connection_status = "disconnected"
    if session.status not in {"completed", "failed"}:
        session.status = "disconnected"
    session.touch()


def complete_session(session: PresentationSession) -> None:
    session.connection_status = "disconnected"
    session.status = "completed"
    session.touch()


def fail_session(session: PresentationSession, reason: str = "") -> None:
    session.status = "failed"
    if reason:
        session.execution_metadata["failure_reason"] = reason
    session.touch()


def session_summary(session: PresentationSession) -> dict:
    """Public session metadata for health and frontend responses."""
    return {
        "session_id": session.session_id,
        "status": session.status,
        "connection_status": session.connection_status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "execution_metadata": deepcopy(session.execution_metadata),
    }
