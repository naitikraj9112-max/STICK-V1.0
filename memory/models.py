"""Small, consistent schemas for the four kinds of agent memory."""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


MemoryType = Literal["working_memory", "episodic_memory", "user_preference", "presentation_memory"]


def now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryScope(BaseModel):
    """Identity fields make presentation memory isolated without requiring auth yet."""

    user_id: str = "local-user"
    presentation_id: str = "local-presentation"
    session_id: str = "local-session"


class MemoryRecord(BaseModel):
    """One portable memory record, regardless of its persistence implementation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: MemoryType
    content: dict[str, Any]
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    user_id: str = "local-user"
    presentation_id: str | None = None
    session_id: str | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryCandidate(BaseModel):
    """A proposed meaningful memory. Python decides whether it is persisted."""

    type: Literal["episodic_memory", "presentation_memory"]
    content: dict[str, Any]
    importance: float = Field(default=0.6, ge=0.0, le=1.0)
    should_store: bool = True
