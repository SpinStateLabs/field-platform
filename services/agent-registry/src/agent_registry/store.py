"""SQLite-backed agent record store (stdlib sqlite3, no ORM)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from agent_registry.models import AgentCreate, AgentRecord, AgentStatus, AgentUpdate

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    owner        TEXT NOT NULL,
    domain       TEXT NOT NULL DEFAULT 'general',
    manifest_ref TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


class DuplicateAgentError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


class RegistryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AgentRecord:
        return AgentRecord(
            agent_id=row["agent_id"],
            name=row["name"],
            owner=row["owner"],
            domain=row["domain"],
            manifest_ref=row["manifest_ref"],
            status=AgentStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def add(self, req: AgentCreate) -> AgentRecord:
        record = AgentRecord(**req.model_dump())
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    "INSERT INTO agents VALUES (?,?,?,?,?,?,?,?)",
                    (
                        record.agent_id,
                        record.name,
                        record.owner,
                        record.domain,
                        record.manifest_ref,
                        record.status.value,
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateAgentError(record.agent_id) from exc
        return record

    def get(self, agent_id: str) -> AgentRecord:
        row = self._conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            raise AgentNotFoundError(agent_id)
        return self._row_to_record(row)

    def list(
        self,
        status: AgentStatus | None = None,
        domain: str | None = None,
    ) -> list[AgentRecord]:
        query, params = "SELECT * FROM agents", []
        clauses = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if domain is not None:
            clauses.append("domain = ?")
            params.append(domain)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY agent_id"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def update(self, agent_id: str, patch: AgentUpdate) -> AgentRecord:
        current = self.get(agent_id)
        fields = patch.model_dump(exclude_none=True)
        if not fields:
            return current
        updated = current.model_copy(
            update={**fields, "updated_at": datetime.now(timezone.utc)}
        )
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE agents SET name=?, owner=?, domain=?, manifest_ref=?, "
                "status=?, updated_at=? WHERE agent_id=?",
                (
                    updated.name,
                    updated.owner,
                    updated.domain,
                    updated.manifest_ref,
                    updated.status.value,
                    updated.updated_at.isoformat(),
                    agent_id,
                ),
            )
        return updated

    def set_status(self, agent_id: str, status: AgentStatus) -> AgentRecord:
        return self.update(agent_id, AgentUpdate(status=status))

    def close(self) -> None:
        self._conn.close()
