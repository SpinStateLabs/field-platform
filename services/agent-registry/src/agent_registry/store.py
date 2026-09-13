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
    updated_at   TEXT NOT NULL,
    attested_at  TEXT,
    attested_by  TEXT
);
"""

#: Columns added after v0.1 shipped. ``CREATE TABLE IF NOT EXISTS`` is a no-op
#: against an existing file, so a persisted estate database (GB10, Fly) would
#: never gain them: every added column needs an ``ALTER TABLE`` here as well as
#: a line in ``_SCHEMA``. Forward-only — an older image can still read the
#: table, it just ignores the extra columns.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("attested_at", "ALTER TABLE agents ADD COLUMN attested_at TEXT"),
    ("attested_by", "ALTER TABLE agents ADD COLUMN attested_by TEXT"),
)

#: Named-column insert. The positional ``INSERT INTO agents VALUES (?,?,...)``
#: this replaced was silently wrong the moment the column count changed.
_INSERT = (
    "INSERT INTO agents "
    "(agent_id, name, owner, domain, manifest_ref, status, created_at, "
    "updated_at, attested_at, attested_by) "
    "VALUES (:agent_id, :name, :owner, :domain, :manifest_ref, :status, "
    ":created_at, :updated_at, :attested_at, :attested_by)"
)

#: The columns a PATCH (``AgentUpdate``) may set. ``update`` builds its SET
#: clause from this fixed tuple, never from caller-supplied keys.
_PATCHABLE: tuple[str, ...] = ("name", "owner", "domain", "manifest_ref", "status")


class DuplicateAgentError(Exception):
    pass


class AgentNotFoundError(Exception):
    pass


def _maybe_ts(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw) if raw else None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class RegistryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # ONE connection shared by every request thread
        # (check_same_thread=False), so ``_lock`` guards EVERY use of it —
        # reads included, execute through fetch. Unlocked concurrent reads
        # returned spurious not-found and other agents' rows, and
        # ``update``'s read-then-write persisted another agent's
        # name/owner/domain (tests/test_registry_store_concurrency.py).
        # ``get``/``list`` fetch (materialise) rows inside the lock and
        # convert them after release. ``update``/``attest`` read, write and
        # read back in ONE hold (see ``update_with_previous``).
        # Plain Lock, not RLock: nothing that takes the lock runs while it
        # is held (``_migrate`` runs inside ``__init__``'s hold and takes
        # none; ``update``/``attest`` use the unlocked ``_fetch``, never
        # ``get``). The only unlocked mention of ``_conn`` is the binding
        # below; tests/test_registry_store_lock_coverage.py checks all of
        # this structurally (and proves ``_migrate``/``_fetch`` run only under
        # it).
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock, self._conn:
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """Add columns a persisted pre-v1.2 database does not have.

        ``CREATE TABLE IF NOT EXISTS`` does nothing to an existing table, so
        without this an estate database keeps its 8-column shape and every
        read of ``attested_at`` raises. Idempotent: run on every open."""
        present = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(agents)")
        }
        for column, ddl in _MIGRATIONS:
            if column not in present:
                self._conn.execute(ddl)

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
            attested_at=_maybe_ts(row["attested_at"]),
            attested_by=row["attested_by"],
        )

    def add(self, req: AgentCreate) -> AgentRecord:
        record = AgentRecord(**req.model_dump())
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT,
                    {
                        "agent_id": record.agent_id,
                        "name": record.name,
                        "owner": record.owner,
                        "domain": record.domain,
                        "manifest_ref": record.manifest_ref,
                        "status": record.status.value,
                        "created_at": record.created_at.isoformat(),
                        "updated_at": record.updated_at.isoformat(),
                        "attested_at": _iso_or_none(record.attested_at),
                        "attested_by": record.attested_by,
                    },
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateAgentError(record.agent_id) from exc
        return record

    def _fetch(self, agent_id: str) -> sqlite3.Row | None:
        """Read one row WITHOUT locking: the caller must hold ``_lock``."""
        return self._conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()

    def get(self, agent_id: str) -> AgentRecord:
        with self._lock:
            row = self._fetch(agent_id)
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
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def update(self, agent_id: str, patch: AgentUpdate) -> AgentRecord:
        return self.update_with_previous(agent_id, patch)[1]

    def update_with_previous(
        self, agent_id: str, patch: AgentUpdate
    ) -> tuple[AgentRecord, AgentRecord]:
        """Apply ``patch``; return ``(before, after)`` from one atomic step.

        Only the patched columns and ``updated_at`` are written, and the
        pre-image read, the UPDATE and the read-back run in ONE lock hold
        inside ONE ``BEGIN IMMEDIATE`` transaction. The old read-release-
        write-every-column version lost updates: a PATCH of ``manifest_ref``
        racing a kill wrote the stale ``status`` back, so the kill returned
        200 ``killed`` and the agent ended ``active``
        (tests/test_registry_update_atomicity.py). ``BEGIN IMMEDIATE`` makes
        the step atomic against other connections to the file as well (the
        CLI is a second process). ``before`` is the row this call changed and
        ``after`` the row exactly as it left it -- what the API's
        status-change ledger note must compare. Rows convert before commit,
        so a row that would not read back rolls back instead of persisting."""
        fields = patch.model_dump(exclude_none=True, mode="json")
        unknown = sorted(set(fields) - set(_PATCHABLE))
        if unknown:
            raise ValueError(f"not a patchable agent column: {unknown}")
        columns = [c for c in _PATCHABLE if c in fields]
        stamp = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            if columns:
                self._conn.execute("BEGIN IMMEDIATE")
            row = self._fetch(agent_id)
            if row is None:
                raise AgentNotFoundError(agent_id)
            before = after = self._row_to_record(row)
            if columns:
                self._conn.execute(
                    "UPDATE agents SET "
                    + ", ".join(f"{c}=?" for c in columns)
                    + ", updated_at=? WHERE agent_id=?",
                    [*(fields[c] for c in columns), stamp, agent_id],
                )
                after = self._row_to_record(self._fetch(agent_id))
        return before, after

    def set_status(self, agent_id: str, status: AgentStatus) -> AgentRecord:
        return self.update(agent_id, AgentUpdate(status=status))

    def attest(
        self, agent_id: str, attested_by: str, now: datetime | None = None
    ) -> AgentRecord:
        """Record a human re-attestation.

        Separate from ``update`` on purpose: ``AgentUpdate`` has no
        ``attested_*`` field and forbids extras, so this is the ONLY way the
        re-attestation clock moves.

        The UPDATE and the read-back share one lock hold and one transaction,
        so the returned record is the row as this call left it -- not a copy
        of an earlier read that a concurrent kill or edit made stale."""
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE agents SET attested_at=?, attested_by=?, updated_at=? "
                "WHERE agent_id=?",
                (stamp, attested_by, stamp, agent_id),
            )
            if cursor.rowcount == 0:
                raise AgentNotFoundError(agent_id)
            return self._row_to_record(self._fetch(agent_id))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
