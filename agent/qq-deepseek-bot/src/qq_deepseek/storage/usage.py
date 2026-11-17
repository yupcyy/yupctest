"""SQLite storage for per-request LLM usage; records no message text or secrets."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from qq_deepseek.core.usage import TokenUsage


class SQLiteUsageStore:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.path.exists()
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        try:
            if is_new:
                self.path.chmod(0o600)
            with self._lock, self._connection:
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA busy_timeout=10000")
                self._connection.execute("""
                    CREATE TABLE IF NOT EXISTS llm_usage (
                        request_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        model TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        prompt_tokens INTEGER NOT NULL CHECK(prompt_tokens >= 0),
                        completion_tokens INTEGER NOT NULL CHECK(completion_tokens >= 0),
                        cache_hit_tokens INTEGER CHECK(cache_hit_tokens >= 0),
                        cache_miss_tokens INTEGER CHECK(cache_miss_tokens >= 0)
                    )
                """)
                self._connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at
                    ON llm_usage(created_at)
                """)
                self._connection.execute("""
                    CREATE INDEX IF NOT EXISTS idx_llm_usage_conversation
                    ON llm_usage(conversation_id, created_at)
                """)
        except BaseException:
            self._connection.close()
            raise

    def insert(self, usage: TokenUsage) -> bool:
        """Idempotent by request_id. Returns False for an existing record."""
        with self._lock, self._connection:
            cursor = self._connection.execute("""
                INSERT OR IGNORE INTO llm_usage
                (request_id, created_at, model, conversation_id, operation,
                 prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usage.request_id, usage.created_at, usage.model, usage.conversation_id,
                usage.operation, usage.prompt_tokens, usage.completion_tokens,
                usage.cache_hit_tokens, usage.cache_miss_tokens,
            ))
            return cursor.rowcount == 1

    def rows(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        conversation_id: str | None = None,
        limit: int = 10000,
    ) -> list[TokenUsage]:
        if not 1 <= limit <= 100000:
            raise ValueError("limit must be between 1 and 100000")
        conditions, params = [], []
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)
        if until is not None:
            conditions.append("created_at < ?")
            params.append(until)
        if conversation_id is not None:
            conditions.append("conversation_id = ?")
            params.append(conversation_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = ("SELECT request_id, created_at, model, conversation_id, operation, "
                 "prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens "
                 "FROM llm_usage" + where + " ORDER BY created_at DESC, request_id DESC LIMIT ?")
        params.append(limit)
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [TokenUsage(*row[:4], row[5], row[6], row[7], row[8], row[4]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
