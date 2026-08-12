"""PostgreSQL persistence boundary for memory.

The rest of the application uses ``MemoryRepository`` and is intentionally
unaware that the current implementation is Neon PostgreSQL.
"""

from abc import ABC, abstractmethod

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # Allows the presentation to start in fallback mode before dependency installation.
    psycopg = None
    Jsonb = None

from config import DATABASE_TIMEOUT_SECONDS, DATABASE_URL
from memory.models import MemoryRecord, MemoryScope


class MemoryRepositoryError(RuntimeError):
    """A storage failure that callers handle without interrupting presentation."""


class MemoryRepository(ABC):
    """Small persistence interface; a future backend can implement the same methods."""

    @abstractmethod
    def get_working(self, scope: MemoryScope) -> dict[str, MemoryRecord]: ...

    @abstractmethod
    def save_working(self, scope: MemoryScope, records: dict[str, MemoryRecord]) -> None: ...

    @abstractmethod
    def clear_session(self, scope: MemoryScope) -> None: ...

    @abstractmethod
    def list_records(self, user_id: str, presentation_id: str | None = None) -> list[MemoryRecord]: ...

    @abstractmethod
    def save_record(self, record: MemoryRecord) -> None: ...

    @abstractmethod
    def delete_record(self, record_id: str) -> None: ...

    @abstractmethod
    def health(self) -> bool: ...


class PostgresMemoryRepository(MemoryRepository):
    """Neon/PostgreSQL repository with idempotent schema initialization."""

    table_name = "presentation_memories"

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or DATABASE_URL
        if not self.database_url or psycopg is None:
            raise MemoryRepositoryError("PostgreSQL memory is not configured")
        self.initialize()

    def initialize(self) -> None:
        """Create the single memory table and indexes safely on every application start."""
        statements = [
            f"""CREATE TABLE IF NOT EXISTS {self.table_name} (
                id UUID PRIMARY KEY,
                user_id TEXT NOT NULL,
                presentation_id TEXT,
                session_id TEXT,
                memory_type TEXT NOT NULL,
                content JSONB NOT NULL,
                importance DOUBLE PRECISION NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )""",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_scope ON {self.table_name} (user_id, presentation_id, memory_type)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_session ON {self.table_name} (user_id, presentation_id, session_id)",
        ]
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
        except Exception as error:
            raise MemoryRepositoryError("PostgreSQL schema initialization failed") from error

    def get_working(self, scope: MemoryScope) -> dict[str, MemoryRecord]:
        query = f"""SELECT id, user_id, presentation_id, session_id, memory_type, content,
                    importance, metadata, created_at, updated_at
                    FROM {self.table_name}
                    WHERE user_id = %s AND presentation_id = %s AND session_id = %s
                    AND memory_type = 'working_memory'"""
        return {record.content["key"]: record for record in self._fetch(query, (scope.user_id, scope.presentation_id, scope.session_id))}

    def save_working(self, scope: MemoryScope, records: dict[str, MemoryRecord]) -> None:
        delete_query = f"""DELETE FROM {self.table_name}
                           WHERE user_id = %s AND presentation_id = %s AND session_id = %s
                           AND memory_type = 'working_memory'"""
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(delete_query, (scope.user_id, scope.presentation_id, scope.session_id))
                for record in records.values():
                    self._upsert(cursor, record)
        except Exception as error:
            raise MemoryRepositoryError("PostgreSQL working-memory write failed") from error

    def clear_session(self, scope: MemoryScope) -> None:
        query = f"""DELETE FROM {self.table_name}
                    WHERE user_id = %s AND presentation_id = %s AND session_id = %s
                    AND memory_type = 'working_memory'"""
        self._execute(query, (scope.user_id, scope.presentation_id, scope.session_id))

    def list_records(self, user_id: str, presentation_id: str | None = None) -> list[MemoryRecord]:
        base = f"""SELECT id, user_id, presentation_id, session_id, memory_type, content,
                   importance, metadata, created_at, updated_at FROM {self.table_name} WHERE user_id = %s"""
        if presentation_id is None:
            return self._fetch(base + " AND presentation_id IS NULL", (user_id,))
        return self._fetch(base + " AND (presentation_id IS NULL OR presentation_id = %s)", (user_id, presentation_id))

    def save_record(self, record: MemoryRecord) -> None:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._upsert(cursor, record)
        except Exception as error:
            raise MemoryRepositoryError("PostgreSQL memory write failed") from error

    def delete_record(self, record_id: str) -> None:
        self._execute(f"DELETE FROM {self.table_name} WHERE id = %s", (record_id,))

    def health(self) -> bool:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _upsert(self, cursor, record: MemoryRecord) -> None:
        query = f"""INSERT INTO {self.table_name}
                    (id, user_id, presentation_id, session_id, memory_type, content, importance, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content, importance = EXCLUDED.importance,
                    metadata = EXCLUDED.metadata, updated_at = EXCLUDED.updated_at"""
        cursor.execute(query, (
            record.id, record.user_id, record.presentation_id, record.session_id, record.type,
            Jsonb(record.content), record.importance, Jsonb(record.metadata), record.created_at, record.updated_at,
        ))

    def _fetch(self, query: str, parameters: tuple) -> list[MemoryRecord]:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(query, parameters)
                return [self._record_from_row(row) for row in cursor.fetchall()]
        except Exception as error:
            raise MemoryRepositoryError("PostgreSQL memory read failed") from error

    def _execute(self, query: str, parameters: tuple) -> None:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(query, parameters)
        except Exception as error:
            raise MemoryRepositoryError("PostgreSQL memory write failed") from error

    def _connect(self):
        # The URL is never logged or sent outside this server-side repository.
        return psycopg.connect(self.database_url, connect_timeout=DATABASE_TIMEOUT_SECONDS)

    @staticmethod
    def _record_from_row(row) -> MemoryRecord:
        return MemoryRecord(
            id=str(row[0]), user_id=row[1], presentation_id=row[2], session_id=row[3], type=row[4],
            content=row[5], importance=row[6], metadata=row[7], created_at=row[8], updated_at=row[9],
        )


class UnavailableMemoryRepository(MemoryRepository):
    """Safe no-op storage used when Neon is unavailable."""

    def get_working(self, _scope): return {}
    def save_working(self, _scope, _records): pass
    def clear_session(self, _scope): pass
    def list_records(self, _user_id, _presentation_id=None): return []
    def save_record(self, _record): pass
    def delete_record(self, _record_id): pass
    def health(self): return False
