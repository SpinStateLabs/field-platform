"""SQLite-backed token store. Tokens are field-core DelegationToken records."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from field_core.delegation import DelegationToken

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token_id      TEXT PRIMARY KEY,
    agent_id      TEXT NOT NULL,
    granted_by    TEXT NOT NULL,
    scope         TEXT NOT NULL,           -- JSON array
    issued_at     TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    revoked       INTEGER NOT NULL DEFAULT 0,
    revocation_id TEXT,
    revoked_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tokens_agent ON tokens (agent_id);
"""


class TokenNotFoundError(Exception):
    pass


class TokenStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    @staticmethod
    def _row_to_token(row: sqlite3.Row) -> DelegationToken:
        import json

        return DelegationToken(
            token_id=row["token_id"],
            agent_id=row["agent_id"],
            granted_by=row["granted_by"],
            scope=json.loads(row["scope"]),
            issued_at=datetime.fromisoformat(row["issued_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            revoked=bool(row["revoked"]),
            revocation_id=row["revocation_id"],
            revoked_at=(
                datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None
            ),
        )

    def save(self, token: DelegationToken) -> DelegationToken:
        import json

        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO tokens VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    token.token_id,
                    token.agent_id,
                    token.granted_by,
                    json.dumps(token.scope),
                    token.issued_at.isoformat(),
                    token.expires_at.isoformat(),
                    int(token.revoked),
                    token.revocation_id,
                    token.revoked_at.isoformat() if token.revoked_at else None,
                ),
            )
        return token

    def get(self, token_id: str) -> DelegationToken:
        row = self._conn.execute(
            "SELECT * FROM tokens WHERE token_id = ?", (token_id,)
        ).fetchone()
        if row is None:
            raise TokenNotFoundError(token_id)
        return self._row_to_token(row)

    def list(self, agent_id: str | None = None) -> list[DelegationToken]:
        if agent_id:
            rows = self._conn.execute(
                "SELECT * FROM tokens WHERE agent_id = ? ORDER BY issued_at",
                (agent_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tokens ORDER BY issued_at"
            ).fetchall()
        return [self._row_to_token(r) for r in rows]

    def active_tokens_for(
        self, agent_id: str, now: datetime | None = None
    ) -> list[DelegationToken]:
        now = now or datetime.now(timezone.utc)
        return [t for t in self.list(agent_id) if t.is_active(now)]

    def close(self) -> None:
        self._conn.close()
