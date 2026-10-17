"""Optional durable local sessions, with atomic cross-process transactions."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from time import time
from typing import Any, TypeVar

from app.domain.errors import DomainError

T = TypeVar("T")
QUOTA_SESSION = "00000000-0000-0000-0000-000000000000"


class SQLiteSessionBackend:
    def __init__(self, path: Path, ttl_seconds: int, max_sessions: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.ttl_seconds, self.max_sessions = path, ttl_seconds, max_sessions
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(id TEXT PRIMARY KEY, payload TEXT NOT NULL, touched REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def load(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM sessions WHERE id=? AND (touched>? OR id=?)",
                (session_id, time() - self.ttl_seconds, QUOTA_SESSION),
            ).fetchone()
        return json.loads(row[0]) if row else {}

    def atomic(self, session_id: str, operation: Callable[[dict[str, Any]], T]) -> T:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM sessions WHERE touched<=? AND id<>?",
                (time() - self.ttl_seconds, QUOTA_SESSION),
            )
            row = connection.execute(
                "SELECT payload FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if (
                row is None
                and connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                >= self.max_sessions
            ):
                raise DomainError(
                    "DEMO_CAPACITY_REACHED", "Demo session capacity reached. Try again later.", 503
                )
            payload = json.loads(row[0]) if row else {}
            result = operation(payload)
            connection.execute(
                "INSERT INTO sessions VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "payload=excluded.payload,touched=excluded.touched",
                (session_id, json.dumps(payload), time()),
            )
        return result

    def reset(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE id=?", (session_id,))
