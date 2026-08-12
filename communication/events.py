"""Events emitted by any transcript transport."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class TranscriptEvent:
    """A latest transcript snapshot, independent of its audio transport."""

    transcript: str
    is_final: bool = False
    source: str = "unknown"
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
