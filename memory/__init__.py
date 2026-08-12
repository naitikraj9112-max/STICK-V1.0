"""Memory subsystem public API.

Only ``MemoryManager`` is used by the presentation orchestrator. Storage and
retrieval choices stay internal so Neon can later be replaced safely.
"""

from memory.manager import MemoryManager
from memory.models import MemoryRecord, MemoryScope
from memory.repository import MemoryRepository, PostgresMemoryRepository

__all__ = ["MemoryManager", "MemoryRecord", "MemoryRepository", "MemoryScope", "PostgresMemoryRepository"]
