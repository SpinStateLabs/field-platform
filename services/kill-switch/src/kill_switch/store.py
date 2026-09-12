"""SQLite-backed heartbeat check-in store (stdlib sqlite3, no ORM).

Deliberately the same shape as ``agent_registry.store.RegistryStore``:
parent ``mkdir``, a ``threading.Lock``, ``check_same_thread=False`` (uvicorn
serves from a thread pool), ``sqlite3.Row``, ``CREATE TABLE IF NOT EXISTS``,
and an explicit ``close()`` so Windows/Google-Drive temp dirs can be removed.

HONESTY: a row here means "this agent POSTed a check-in at this instant".
It is evidence of a check-in, never evidence that the process is alive now,
and its absence is not evidence that the process is dead — an agent that
never calls ``POST /heartbeat`` simply reads stale forever.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeats (
    agent_id   TEXT PRIMARY KEY,
    last_seen  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'unknown',
    checkins   INTEGER NOT NULL DEFAULT 0
);
"""


class HeartbeatStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def record(self, agent_id: str, seen_at: datetime, status: str) -> None:
        """Upsert one check-in. ``status`` is what the registry said at
        check-in time (``unregistered`` for a shadow agent nobody registered)."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO heartbeats (agent_id, last_seen, status, checkins) "
                "VALUES (?,?,?,1) "
                "ON CONFLICT(agent_id) DO UPDATE SET "
                "last_seen=excluded.last_seen, status=excluded.status, "
                "checkins=heartbeats.checkins+1",
                (agent_id, seen_at.astimezone(timezone.utc).isoformat(), status),
            )

    def get(self, agent_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM heartbeats WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return None if row is None else self._row_to_dict(row)

    def all(self) -> dict[str, dict]:
        rows = self._conn.execute(
            "SELECT * FROM heartbeats ORDER BY agent_id"
        ).fetchall()
        return {row["agent_id"]: self._row_to_dict(row) for row in rows}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "agent_id": row["agent_id"],
            "last_seen": datetime.fromisoformat(row["last_seen"]),
            "status": row["status"],
            "checkins": row["checkins"],
        }

    def close(self) -> None:
        self._conn.close()
