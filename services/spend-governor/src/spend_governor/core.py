"""Spend metering core — models, arithmetic, and the SQLite store.

All money is integer cents; tokens and actions are integer counts.
Deterministic arithmetic only — no floats near a limit comparison, no LLM.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from field_core.manifest import FieldManifest

DEFAULT_ESCALATE_AT_PCT = 80  # cross this % of any cap -> human review


class SpendState(str, Enum):
    OK = "OK"
    ESCALATE = "ESCALATE"  # threshold crossed, human queue notified
    BLOCK = "BLOCK"        # hard cap reached


class SpendCapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    currency: str = "USD"
    limit_cents: int | None = Field(default=None, gt=0)
    token_limit: int | None = Field(default=None, gt=0)
    action_limit: int | None = Field(default=None, gt=0)
    period: str = Field(default="daily", pattern=r"^(daily|monthly|total)$")
    escalate_at_pct: int = Field(default=DEFAULT_ESCALATE_AT_PCT, ge=1, le=100)
    on_breach: str = "halt"

    @model_validator(mode="after")
    def _at_least_one_limit(self) -> "SpendCapConfig":
        if self.limit_cents is None and self.token_limit is None and self.action_limit is None:
            raise ValueError("configure at least one of limit_cents/token_limit/action_limit")
        return self

    @classmethod
    def from_manifest(cls, manifest: FieldManifest, agent_id: str) -> "SpendCapConfig":
        """Derive the dollar cap from the manifest's enforcement.spend_cap.

        The manifest limit is a number in currency units; converted to cents
        with round-half-away banned — manifests must use at most 2 decimals.
        """
        cap = manifest.enforcement.spend_cap
        if cap is None:
            raise ValueError("manifest has no enforcement.spend_cap")
        cents = round(cap.limit * 100)
        if abs(cents - cap.limit * 100) > 1e-9:
            raise ValueError("spend_cap.limit has sub-cent precision; refuse to guess")
        period = cap.period if cap.period in ("daily", "monthly") else "total"
        return cls(
            agent_id=agent_id,
            currency=cap.currency,
            limit_cents=int(cents),
            period=period,
            on_breach=cap.on_breach or "halt",
        )


class SpendEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    agent_id: str
    ts: str
    cents: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    actions: int = Field(default=0, ge=0)
    note: str | None = None


class Escalation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    escalation_id: str
    agent_id: str
    ts: str
    kind: str          # "cents" | "tokens" | "actions"
    spent: int
    limit: int
    pct: int
    resolved: bool = False
    resolved_by: str | None = None


class SpendStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    state: SpendState
    period: str
    window_start: str
    currency: str
    spent_cents: int
    limit_cents: int | None
    spent_tokens: int
    token_limit: int | None
    spent_actions: int
    action_limit: int | None
    open_escalations: int
    detail: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS caps (
    agent_id TEXT PRIMARY KEY, currency TEXT, limit_cents INTEGER,
    token_limit INTEGER, action_limit INTEGER, period TEXT,
    escalate_at_pct INTEGER, on_breach TEXT
);
CREATE TABLE IF NOT EXISTS spend (
    event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    cents INTEGER NOT NULL, tokens INTEGER NOT NULL, actions INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_spend_agent_ts ON spend (agent_id, ts);
CREATE TABLE IF NOT EXISTS escalations (
    escalation_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    kind TEXT NOT NULL, spent INTEGER NOT NULL, "limit" INTEGER NOT NULL,
    pct INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, resolved_by TEXT
);
"""


def window_start(period: str, now: datetime) -> str:
    if period == "daily":
        return now.strftime("%Y-%m-%dT00:00:00+00:00")
    if period == "monthly":
        return now.strftime("%Y-%m-01T00:00:00+00:00")
    return "1970-01-01T00:00:00+00:00"  # total


class GovernorStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    # -- caps --
    def set_cap(self, cap: SpendCapConfig) -> SpendCapConfig:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO caps VALUES (?,?,?,?,?,?,?,?)",
                (
                    cap.agent_id, cap.currency, cap.limit_cents, cap.token_limit,
                    cap.action_limit, cap.period, cap.escalate_at_pct, cap.on_breach,
                ),
            )
        return cap

    def get_cap(self, agent_id: str) -> SpendCapConfig | None:
        row = self._conn.execute(
            "SELECT * FROM caps WHERE agent_id=?", (agent_id,)
        ).fetchone()
        if row is None:
            return None
        return SpendCapConfig(
            agent_id=row["agent_id"], currency=row["currency"],
            limit_cents=row["limit_cents"], token_limit=row["token_limit"],
            action_limit=row["action_limit"], period=row["period"],
            escalate_at_pct=row["escalate_at_pct"], on_breach=row["on_breach"],
        )

    # -- spend --
    def record(self, agent_id: str, cents: int, tokens: int, actions: int,
               note: str | None, now: datetime) -> SpendEvent:
        event = SpendEvent(
            event_id=str(uuid.uuid4()), agent_id=agent_id,
            ts=now.isoformat(), cents=cents, tokens=tokens, actions=actions,
            note=note,
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO spend VALUES (?,?,?,?,?,?,?)",
                (event.event_id, event.agent_id, event.ts, event.cents,
                 event.tokens, event.actions, event.note),
            )
        return event

    def totals_since(self, agent_id: str, since_iso: str) -> tuple[int, int, int]:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(cents),0) c, COALESCE(SUM(tokens),0) t, "
            "COALESCE(SUM(actions),0) a FROM spend WHERE agent_id=? AND ts>=?",
            (agent_id, since_iso),
        ).fetchone()
        return int(row["c"]), int(row["t"]), int(row["a"])

    # -- escalations --
    def add_escalation(self, esc: Escalation) -> Escalation:
        with self._lock, self._conn:
            self._conn.execute(
                'INSERT INTO escalations VALUES (?,?,?,?,?,?,?,?,?)',
                (esc.escalation_id, esc.agent_id, esc.ts, esc.kind, esc.spent,
                 esc.limit, esc.pct, int(esc.resolved), esc.resolved_by),
            )
        return esc

    def open_escalations(self, agent_id: str | None = None) -> list[Escalation]:
        q = "SELECT * FROM escalations WHERE resolved=0"
        params: list[str] = []
        if agent_id:
            q += " AND agent_id=?"
            params.append(agent_id)
        rows = self._conn.execute(q + " ORDER BY ts", params).fetchall()
        return [self._row_to_esc(r) for r in rows]

    def has_open_escalation(self, agent_id: str, kind: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM escalations WHERE agent_id=? AND kind=? AND resolved=0",
            (agent_id, kind),
        ).fetchone()
        return row is not None

    def resolve_escalation(self, escalation_id: str, resolved_by: str) -> Escalation:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE escalations SET resolved=1, resolved_by=? WHERE escalation_id=?",
                (resolved_by, escalation_id),
            )
        row = self._conn.execute(
            "SELECT * FROM escalations WHERE escalation_id=?", (escalation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(escalation_id)
        return self._row_to_esc(row)

    @staticmethod
    def _row_to_esc(row: sqlite3.Row) -> Escalation:
        return Escalation(
            escalation_id=row["escalation_id"], agent_id=row["agent_id"],
            ts=row["ts"], kind=row["kind"], spent=row["spent"],
            limit=row["limit"], pct=row["pct"], resolved=bool(row["resolved"]),
            resolved_by=row["resolved_by"],
        )

    def close(self) -> None:
        self._conn.close()


def evaluate(
    cap: SpendCapConfig,
    spent_cents: int,
    spent_tokens: int,
    spent_actions: int,
    open_escalations: int,
) -> tuple[SpendState, str]:
    """Pure decision arithmetic: BLOCK at/over any limit; ESCALATE at threshold."""
    pairs = (
        ("cents", spent_cents, cap.limit_cents),
        ("tokens", spent_tokens, cap.token_limit),
        ("actions", spent_actions, cap.action_limit),
    )
    for kind, spent, limit in pairs:
        if limit is not None and spent >= limit:
            return SpendState.BLOCK, f"{kind} cap reached: {spent} >= {limit}"
    for kind, spent, limit in pairs:
        # threshold: spent * 100 >= limit * pct  (integer arithmetic, no floats)
        if limit is not None and spent * 100 >= limit * cap.escalate_at_pct:
            return (
                SpendState.ESCALATE,
                f"{kind} at {spent}/{limit} — crossed {cap.escalate_at_pct}% threshold",
            )
    if open_escalations:
        return SpendState.ESCALATE, f"{open_escalations} unresolved escalation(s)"
    return SpendState.OK, "within limits"
