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
-- v1.2 D1e: a token's spend ceiling, stamped once at mint. A side table, not
-- a tokens column: a pre-D1e image writes tokens with a positional 9-value
-- INSERT, which a 10-column table refuses, so a column would break its mints
-- AND revokes after an image rollback. This table is created at open (under
-- the init lock) and a pre-D1e image simply never reads it.
CREATE TABLE IF NOT EXISTS token_spend_ceilings (
    token_id      TEXT PRIMARY KEY,
    max_spend_usd REAL NOT NULL
);
"""

_SELECT = (
    "SELECT t.*, c.max_spend_usd AS max_spend_usd FROM tokens t "
    "LEFT JOIN token_spend_ceilings c ON c.token_id = t.token_id"
)


class TokenNotFoundError(Exception):
    pass


class TokenStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # ONE connection shared by every request thread
        # (check_same_thread=False), so ``_lock`` guards EVERY use of it —
        # reads included, execute through fetch. Unlocked concurrent reads
        # returned spurious not-found, another token's row, and decode
        # errors (tests/test_token_store_concurrency.py). Rows are fetched
        # (materialised) inside the lock and converted after release.
        # Plain Lock, not RLock: no method calls another while holding it.
        # The only unlocked mention of ``_conn`` is the binding below;
        # tests/test_token_store_lock_coverage.py checks all of this
        # structurally.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock, self._conn:
            self._conn.row_factory = sqlite3.Row
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
            max_spend_usd=row["max_spend_usd"],
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
            if token.max_spend_usd is not None:
                # Stamped once: a later save (revoke) never changes or removes it.
                self._conn.execute(
                    "INSERT OR IGNORE INTO token_spend_ceilings VALUES (?,?)",
                    (token.token_id, token.max_spend_usd),
                )
            ceiling = self._conn.execute(
                "SELECT max_spend_usd FROM token_spend_ceilings WHERE token_id = ?",
                (token.token_id,),
            ).fetchone()
        stored = ceiling[0] if ceiling is not None else None
        if stored == token.max_spend_usd:
            return token
        return token.model_copy(update={"max_spend_usd": stored})

    def get(self, token_id: str) -> DelegationToken:
        with self._lock:
            row = self._conn.execute(
                f"{_SELECT} WHERE t.token_id = ?", (token_id,)
            ).fetchone()
        if row is None:
            raise TokenNotFoundError(token_id)
        return self._row_to_token(row)

    def list(self, agent_id: str | None = None) -> list[DelegationToken]:
        with self._lock:
            if agent_id:
                rows = self._conn.execute(
                    f"{_SELECT} WHERE t.agent_id = ? ORDER BY t.issued_at",
                    (agent_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    f"{_SELECT} ORDER BY t.issued_at"
                ).fetchall()
        return [self._row_to_token(r) for r in rows]

    def active_tokens_for(
        self, agent_id: str, now: datetime | None = None
    ) -> list[DelegationToken]:
        now = now or datetime.now(timezone.utc)
        return [t for t in self.list(agent_id) if t.is_active(now)]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
