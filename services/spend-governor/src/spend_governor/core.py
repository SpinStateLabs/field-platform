"""Spend metering core — models, arithmetic, and the SQLite store.

All money is integer cents; tokens and actions are integer counts.
Deterministic arithmetic only — no floats near a limit comparison, no LLM.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from field_core.manifest import FieldManifest

_log = logging.getLogger(__name__)

DEFAULT_ESCALATE_AT_PCT = 80  # cross this % of any cap -> human review


class SpendState(str, Enum):
    OK = "OK"
    ESCALATE = "ESCALATE"    # threshold crossed, human queue notified
    THROTTLED = "THROTTLED"  # a per-action or token rate window is exhausted
    BLOCK = "BLOCK"          # hard cap reached


#: Spend-cap windows the governor can compute (``window_start``).
SUPPORTED_CAP_PERIODS = ("daily", "monthly", "total")


class UnsupportedCapPeriodError(ValueError):
    """A manifest ``spend_cap.period`` the governor has no window for.

    ``per-run`` is the schema's own example and there is no run concept here;
    before D1f it was silently metered as ``total``. It is refused instead."""


class UnknownRatePeriodError(ValueError):
    """A ``rate_limits[].period`` outside the governor's period grammar."""


#: Periods a manifest may declare that have NO server-side meaning. ``session``
#: is the Claude Code Enforcement Gate's per-session tool-call budget: it is
#: recorded as declared-unenforced, never mapped to a window.
DECLARED_UNENFORCED_PERIODS = frozenset({"session"})
#: Rolling windows longer than this are refused (a typo'd 9999999d is not a limit).
MAX_RATE_PERIOD_SECONDS = 366 * 86400
_NAMED_RATE_PERIODS = {"hourly": 3600, "daily": 86400, "monthly": 30 * 86400}
_RATE_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_RATE_PERIOD_RE = re.compile(r"([1-9][0-9]{0,8})([smhd])")
RATE_PERIOD_GRAMMAR = "hourly|daily|monthly|<N>s|<N>m|<N>h|<N>d (or session: declared, unenforced)"


def parse_rate_period(period: str) -> int | None:
    """Seconds of the ROLLING window for a rate-limit period.

    ``hourly`` = 3600 s, ``daily`` = 86400 s, ``monthly`` = 30 days, ``<N>s|m|h|d``
    = N units. Returns None for a declared-unenforced period (``session``).
    Exact strings only: case and whitespace variants are unknown. Raises
    ``UnknownRatePeriodError`` for anything else — never a guessed window."""
    if period in DECLARED_UNENFORCED_PERIODS:
        return None
    if period in _NAMED_RATE_PERIODS:
        return _NAMED_RATE_PERIODS[period]
    match = _RATE_PERIOD_RE.fullmatch(period) if isinstance(period, str) else None
    if match is None:
        raise UnknownRatePeriodError(
            f"rate limit period {period!r} is not in the grammar {RATE_PERIOD_GRAMMAR}")
    seconds = int(match.group(1)) * _RATE_UNIT_SECONDS[match.group(2)]
    if seconds > MAX_RATE_PERIOD_SECONDS:
        raise UnknownRatePeriodError(
            f"rate limit period {period!r} is longer than 366 days — refused")
    return seconds


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
        if cap.period not in SUPPORTED_CAP_PERIODS:
            # D1f: never silently widen an unknown window (per-run) to total.
            raise UnsupportedCapPeriodError(
                f"spend_cap.period {cap.period!r} is not supported "
                f"({'|'.join(SUPPORTED_CAP_PERIODS)}) — refusing to meter it as 'total'"
            )
        period = cap.period
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
    # D1: per-action attribution. ``source`` "self" = the agent's own report;
    # "sentinel" = one ALLOW verdict metered by conformance-sentinel.
    action: str | None = None
    source: str = "self"


class RateLimitEntry(BaseModel):
    """One ``enforcement.rate_limits`` entry, verbatim from the manifest."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    max: int = Field(ge=1)
    period: str = Field(min_length=1)


class RateLimitSet(BaseModel):
    """``PUT /rate-limits/{agent_id}`` body: the agent's WHOLE set (replaces)."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    rate_limits: list[RateLimitEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _known_periods_no_duplicates(self) -> "RateLimitSet":
        seen: set[tuple[str, str]] = set()
        for entry in self.rate_limits:
            parse_rate_period(entry.period)  # UnknownRatePeriodError -> 422
            key = (entry.action, entry.period)
            if key in seen:
                raise ValueError(
                    f"duplicate rate limit for action {entry.action!r} period "
                    f"{entry.period!r} — ambiguous, refused")
            seen.add(key)
        return self

    @classmethod
    def from_manifest(cls, manifest: FieldManifest, agent_id: str) -> "RateLimitSet":
        return cls(agent_id=agent_id, rate_limits=[
            RateLimitEntry(action=r.action, max=r.max, period=r.period)
            for r in manifest.enforcement.rate_limits or []
        ])


class RateLimitRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    max: int
    period: str
    period_seconds: int | None  # None = declared, no server-side window
    status: Literal["enforced", "declared_unenforced"]


class RateLimitsView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    rate_limits: list[RateLimitRow]


class ThrottleInfo(BaseModel):
    """Why a status is THROTTLED: the exhausted window."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["action", "tokens"]
    action: str | None       # the rate-limited action (None for the token window)
    count: int
    max: int
    period: str
    period_seconds: int


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
    # token-cost governance (0 when the agent reports no LLM usage)
    token_cost_units: int = 0        # integer 1e-7 USD from priced usage
    token_cost_display: str = "$0"
    # D1 throttle + A/B metering. ``spent_actions`` is what ``action_limit``
    # compares: per action max(self, metered) plus unattributed rows.
    spent_actions_self: int = 0
    spent_actions_metered: int = 0
    retry_after_seconds: int | None = None   # set only when state is THROTTLED
    throttled: ThrottleInfo | None = None    # set only when state is THROTTLED


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
CREATE TABLE IF NOT EXISTS usage (
    event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_units INTEGER, priced INTEGER NOT NULL DEFAULT 1, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_agent_ts ON usage (agent_id, ts);
CREATE TABLE IF NOT EXISTS usage_policies (
    agent_id TEXT PRIMARY KEY, allowed_models TEXT NOT NULL,
    token_rate_limit INTEGER, rate_window_seconds INTEGER NOT NULL DEFAULT 3600
);
CREATE TABLE IF NOT EXISTS rate_limits (
    agent_id TEXT NOT NULL, action TEXT NOT NULL, max INTEGER NOT NULL,
    period TEXT NOT NULL, period_seconds INTEGER,
    PRIMARY KEY (agent_id, action, period)
);
"""

#: D1 spend attribution, added to ``spend`` by ``_migrate_spend_attribution``
#: at EVERY open (fresh and persisted databases take the same ALTER path, so
#: the column order is identical). ``spend`` in ``_SCHEMA`` above stays the
#: pre-D 7-column table on purpose. Once added, a pre-D image's positional
#: 7-value ``INSERT INTO spend VALUES`` fails on this database (README LIMITS,
#: rollback).
_SPEND_ATTRIBUTION_COLUMNS = (
    ("action", "ALTER TABLE spend ADD COLUMN action TEXT"),
    ("source", "ALTER TABLE spend ADD COLUMN source TEXT NOT NULL DEFAULT 'self'"),
)
_SPEND_ACTION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_spend_agent_action_ts ON spend (agent_id, action, ts)"
)

#: At most ONE open escalation per (agent, kind), as a database invariant.
#: Deliberately NOT in ``_SCHEMA``: on a persisted database that already holds
#: duplicate open rows (written before the check-and-insert became atomic)
#: ``CREATE UNIQUE INDEX`` raises, and a store must never fail to open over
#: it. ``_migrate_open_escalation_index`` creates it when it can and retries
#: on every open, so it appears once humans have resolved the duplicates.
_OPEN_ESCALATION_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_escalations_open "
    "ON escalations (agent_id, kind) WHERE resolved=0"
)


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
        # ONE connection shared by every request thread
        # (check_same_thread=False), so ``_lock`` guards EVERY use of it —
        # reads included, execute through fetch. Unlocked concurrent reads
        # returned no cap/policy for configured agents, empty escalation
        # queues and another agent's cap
        # (tests/test_governor_store_concurrency.py).
        # Rows are fetched (materialised) inside the lock and converted after
        # release. Plain Lock, not RLock: no method calls another while
        # holding it (``_migrate_open_escalation_index`` runs inside
        # ``__init__``'s hold and takes none). The only unlocked mention of
        # ``_conn`` is the binding below;
        # tests/test_governor_store_lock_coverage.py checks that structurally.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        with self._lock, self._conn:
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
            self.open_escalation_index = self._migrate_open_escalation_index()
            self.spend_columns_added = self._migrate_spend_attribution()

    def _migrate_spend_attribution(self) -> list[str]:
        """Add ``spend.action`` / ``spend.source`` when missing (PRAGMA → ALTER).

        Runs at open, inside ``__init__``'s hold. Returns the columns added by
        THIS open ([] when already present). Rows written before the columns
        existed read back as ``action`` NULL (unattributed: totals only) and
        ``source`` 'self'. Idempotent."""
        present = {row[1] for row in self._conn.execute("PRAGMA table_info(spend)").fetchall()}
        added: list[str] = []
        for column, ddl in _SPEND_ATTRIBUTION_COLUMNS:
            if column not in present:
                self._conn.execute(ddl)
                added.append(column)
        self._conn.execute(_SPEND_ACTION_INDEX)
        if added:
            existing = self._conn.execute("SELECT COUNT(*) FROM spend").fetchone()[0]
            log = _log.warning if existing else _log.debug
            log("spend-governor: spend table gained column(s) %s at open (%s existing "
                "row(s) now read as source='self', action unattributed); a pre-D1 "
                "image can no longer INSERT into this database", ", ".join(added), existing)
        return added

    def _migrate_open_escalation_index(self) -> bool:
        """Create the one-open-escalation-per-(agent, kind) unique index.

        Returns whether the index is in place. A persisted database may
        already hold duplicate open escalations; then the index cannot be
        built, and the store still opens (the duplicates stay visible in the
        human queue, never auto-resolved) with a warning. The check-and-insert
        in ``add_escalation_if_none_open`` prevents new duplicates either way.
        Idempotent: run on every open."""
        try:
            self._conn.execute(_OPEN_ESCALATION_INDEX)
        except sqlite3.IntegrityError:
            groups = self._conn.execute(
                "SELECT COUNT(*) FROM (SELECT 1 FROM escalations WHERE resolved=0 "
                "GROUP BY agent_id, kind HAVING COUNT(*) > 1)"
            ).fetchone()[0]
            _log.warning(
                "spend-governor: %s (agent, kind) pair(s) already have more than "
                "one open escalation; unique index uq_escalations_open not "
                "created (retried on next open once they are resolved)", groups,
            )
            return False
        return True

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
        with self._lock:
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
               note: str | None, now: datetime, action: str | None = None,
               source: str = "self") -> SpendEvent:
        event = SpendEvent(
            event_id=str(uuid.uuid4()), agent_id=agent_id,
            ts=now.isoformat(), cents=cents, tokens=tokens, actions=actions,
            note=note, action=action, source=source,
        )
        with self._lock, self._conn:
            # Named columns: the table has 9 columns after the D1 migration.
            self._conn.execute(
                "INSERT INTO spend (event_id, agent_id, ts, cents, tokens, actions, "
                "note, action, source) VALUES (?,?,?,?,?,?,?,?,?)",
                (event.event_id, event.agent_id, event.ts, event.cents,
                 event.tokens, event.actions, event.note, event.action, event.source),
            )
        return event

    def action_counts_since(
        self, agent_id: str, since_iso: str
    ) -> list[tuple[str | None, str, int]]:
        """``(action, source, SUM(actions))`` per group in the cap window
        (``ts >= since``, like ``totals_since``)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT action, source, COALESCE(SUM(actions),0) a FROM spend "
                "WHERE agent_id=? AND ts>=? GROUP BY action, source",
                (agent_id, since_iso),
            ).fetchall()
        return [(r["action"], r["source"], int(r["a"])) for r in rows]

    def action_rows_after(
        self, agent_id: str, action: str, after_iso: str
    ) -> list[tuple[str, str, int]]:
        """``(ts, source, actions)`` for ONE action, ``ts > after`` (a rolling
        window's strict lower edge), oldest first. ``action=?`` is SQLite's
        BINARY comparison: exact bytes, no case or whitespace folding."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, source, actions FROM spend WHERE agent_id=? AND action=? "
                "AND ts>? AND actions>0 ORDER BY ts, event_id",
                (agent_id, action, after_iso),
            ).fetchall()
        return [(r["ts"], r["source"], int(r["actions"])) for r in rows]

    def token_rows_after(self, agent_id: str, after_iso: str) -> list[tuple[str, int]]:
        """``(ts, input+output tokens)`` usage rows with ``ts > after``, oldest
        first — the same tokens ``window_tokens`` sums, with the strict edge a
        rolling throttle needs (``window_tokens`` stays inclusive for
        rogue_burst)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, input_tokens+output_tokens t FROM usage "
                "WHERE agent_id=? AND ts>? ORDER BY ts, event_id",
                (agent_id, after_iso),
            ).fetchall()
        return [(r["ts"], int(r["t"])) for r in rows]

    # -- rate limits --
    def set_rate_limits(self, limits: RateLimitSet) -> list[RateLimitRow]:
        """Replace the agent's whole rate-limit set in one transaction."""
        rows = [
            (limits.agent_id, e.action, e.max, e.period, parse_rate_period(e.period))
            for e in limits.rate_limits
        ]
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM rate_limits WHERE agent_id=?", (limits.agent_id,))
            self._conn.executemany(
                "INSERT INTO rate_limits (agent_id, action, max, period, period_seconds) "
                "VALUES (?,?,?,?,?)",
                rows,
            )
        return [_rate_row(action, mx, period, secs) for _, action, mx, period, secs in rows]

    def get_rate_limits(self, agent_id: str) -> list[RateLimitRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT action, max, period, period_seconds FROM rate_limits "
                "WHERE agent_id=? ORDER BY action, period",
                (agent_id,),
            ).fetchall()
        return [_rate_row(r["action"], int(r["max"]), r["period"], r["period_seconds"])
                for r in rows]

    def totals_since(self, agent_id: str, since_iso: str) -> tuple[int, int, int]:
        with self._lock:
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

    def add_escalation_if_none_open(self, esc: Escalation) -> tuple[Escalation, bool]:
        """Open ``esc`` unless its agent already has an OPEN escalation of its kind.

        Returns ``(open_escalation, created)``: ``esc`` and True when this
        call inserted it, else the escalation already open and False. The
        check and the insert run in ONE lock hold inside ONE ``BEGIN
        IMMEDIATE`` transaction (atomic against other connections to the file
        too). The old ``has_open_escalation()`` then ``add_escalation()`` took
        two holds, so concurrent spends crossing the threshold together each
        saw "none open" and each opened one (and ledgered one)
        (tests/test_escalation_atomicity.py)."""
        if esc.resolved:
            raise ValueError("add_escalation_if_none_open opens an escalation; "
                             "got resolved=True")
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                "SELECT * FROM escalations WHERE agent_id=? AND kind=? AND resolved=0 "
                "ORDER BY ts, escalation_id LIMIT 1",
                (esc.agent_id, esc.kind),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    'INSERT INTO escalations VALUES (?,?,?,?,?,?,?,?,?)',
                    (esc.escalation_id, esc.agent_id, esc.ts, esc.kind, esc.spent,
                     esc.limit, esc.pct, 0, None),
                )
        if row is not None:
            return self._row_to_esc(row), False
        return esc, True

    def open_escalations(self, agent_id: str | None = None) -> list[Escalation]:
        q = "SELECT * FROM escalations WHERE resolved=0"
        params: list[str] = []
        if agent_id:
            q += " AND agent_id=?"
            params.append(agent_id)
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY ts", params).fetchall()
        return [self._row_to_esc(r) for r in rows]

    def has_open_escalation(self, agent_id: str, kind: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM escalations WHERE agent_id=? AND kind=? AND resolved=0",
                (agent_id, kind),
            ).fetchone()
        return row is not None

    def resolve_escalation(self, escalation_id: str, resolved_by: str) -> Escalation:
        """Resolve; the FIRST resolver wins. Returns the stored row, whose
        ``resolved_by`` is ``resolved_by`` only if this call (or an earlier
        one by the same human) resolved it. See ``resolve_escalation_once``."""
        return self.resolve_escalation_once(escalation_id, resolved_by)[0]

    def resolve_escalation_once(
        self, escalation_id: str, resolved_by: str
    ) -> tuple[Escalation, bool]:
        """Resolve an OPEN escalation; return ``(stored_row, resolved_now)``.

        First resolver wins: the UPDATE only matches ``resolved=0``, so a
        second resolve never rewrites ``resolved_by`` (the old ``WHERE
        escalation_id=?`` let the last resolver overwrite the human of
        record). ``resolved_now`` is True only for the call that flipped the
        row. The UPDATE and the read-back share ONE lock hold and ONE
        transaction, so the returned row is the row as stored after this
        call. Raises ``KeyError`` for an unknown id."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE escalations SET resolved=1, resolved_by=? "
                "WHERE escalation_id=? AND resolved=0",
                (resolved_by, escalation_id),
            )
            resolved_now = cursor.rowcount == 1
            row = self._conn.execute(
                "SELECT * FROM escalations WHERE escalation_id=?", (escalation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(escalation_id)
        return self._row_to_esc(row), resolved_now

    @staticmethod
    def _row_to_esc(row: sqlite3.Row) -> Escalation:
        return Escalation(
            escalation_id=row["escalation_id"], agent_id=row["agent_id"],
            ts=row["ts"], kind=row["kind"], spent=row["spent"],
            limit=row["limit"], pct=row["pct"], resolved=bool(row["resolved"]),
            resolved_by=row["resolved_by"],
        )

    # -- usage policies --
    def set_policy(self, policy: "UsagePolicy") -> "UsagePolicy":
        import json

        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO usage_policies VALUES (?,?,?,?)",
                (policy.agent_id, json.dumps(policy.allowed_models),
                 policy.token_rate_limit, policy.rate_window_seconds),
            )
        return policy

    def get_policy(self, agent_id: str) -> "UsagePolicy | None":
        import json

        from spend_governor.usage import UsagePolicy

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM usage_policies WHERE agent_id=?", (agent_id,)
            ).fetchone()
        if row is None:
            return None
        return UsagePolicy(
            agent_id=row["agent_id"],
            allowed_models=json.loads(row["allowed_models"]),
            token_rate_limit=row["token_rate_limit"],
            rate_window_seconds=row["rate_window_seconds"],
        )

    # -- usage events --
    def record_usage(self, rec: "UsageRecord") -> "UsageRecord":
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO usage VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rec.event_id, rec.agent_id, rec.ts, rec.model,
                 rec.input_tokens, rec.output_tokens, rec.cache_read_tokens,
                 rec.cost_units, int(rec.priced), rec.note),
            )
        return rec

    def window_tokens(self, agent_id: str, since_iso: str) -> int:
        """input+output tokens for the agent since since_iso (burst check)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(input_tokens+output_tokens),0) t "
                "FROM usage WHERE agent_id=? AND ts>=?",
                (agent_id, since_iso),
            ).fetchone()
        return int(row["t"])

    def usage_totals_since(self, agent_id: str, since_iso: str):
        """Return (total_in, total_out, total_cost_units_priced, by_model rows)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT model, COALESCE(SUM(input_tokens),0) i, "
                "COALESCE(SUM(output_tokens),0) o, "
                "COALESCE(SUM(cost_units),0) c, MIN(priced) p "
                "FROM usage WHERE agent_id=? AND ts>=? GROUP BY model ORDER BY model",
                (agent_id, since_iso),
            ).fetchall()
        total_in = sum(r["i"] for r in rows)
        total_out = sum(r["o"] for r in rows)
        total_cost = sum(r["c"] for r in rows if r["p"])
        return total_in, total_out, total_cost, rows

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _rate_row(action: str, mx: int, period: str, seconds: int | None) -> RateLimitRow:
    return RateLimitRow(
        action=action, max=mx, period=period, period_seconds=seconds,
        status="enforced" if seconds is not None else "declared_unenforced",
    )


def action_totals(groups: Iterable[tuple[str | None, str, int]]) -> tuple[int, int, int]:
    """Option A counting over ``(action, source, count)`` groups.

    Returns ``(self_total, metered_total, counted)``. ``counted`` is what the
    ``action_limit`` cap compares: for each named action max(self-reported,
    sentinel-metered) — the same action checked AND self-reported counts once,
    never twice, and an action only one side saw is never lost — plus every
    unattributed (``action`` NULL) row. Any source other than ``sentinel`` is
    self-reported."""
    self_by: dict[str, int] = {}
    metered_by: dict[str, int] = {}
    self_total = metered_total = unattributed = 0
    for action, source, count in groups:
        if source == "sentinel":
            metered_total += count
            bucket = metered_by
        else:
            self_total += count
            bucket = self_by
        if action is None:
            unattributed += count
        else:
            bucket[action] = bucket.get(action, 0) + count
    counted = unattributed + sum(
        max(self_by.get(a, 0), metered_by.get(a, 0)) for a in set(self_by) | set(metered_by)
    )
    return self_total, metered_total, counted


def window_action_rows(rows: Iterable[tuple[str, str, int]]) -> list[tuple[str, int]]:
    """Option A precedence for ONE action's rolling window: the sentinel-metered
    rows when any exist in the window, else the self-reported rows."""
    rows = list(rows)
    metered = [(ts, n) for ts, source, n in rows if source == "sentinel"]
    if metered:
        return metered
    return [(ts, n) for ts, source, n in rows if source != "sentinel"]


def _utc(ts: str | datetime) -> datetime:
    value = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def window_retry_after(
    rows: Iterable[tuple[str | datetime, int]], limit: int, period_seconds: int,
    now: datetime,
) -> tuple[int, int | None]:
    """Rolling-window throttle arithmetic, integer only.

    ``rows`` are ``(ts, amount)`` already inside the window (``ts > now -
    period``), any order. Returns ``(count, retry_after_seconds)``; the second
    is None unless ``count >= limit`` (THROTTLED). A row leaves the window when
    ``ts + period <= now``; retry_after is the whole seconds, rounded UP, until
    enough of the OLDEST amounts have left that ``count < limit``. It is at
    least 1 (a row still in the window has strictly positive time left)."""
    ordered = sorted(((_utc(ts), int(n)) for ts, n in rows), key=lambda r: r[0])
    count = sum(n for _, n in ordered)
    if count < limit:
        return count, None
    must_shed = count - limit + 1
    shed = 0
    period = timedelta(seconds=period_seconds)
    one_second = timedelta(seconds=1)
    now = _utc(now)
    for ts, amount in ordered:
        shed += amount
        if shed >= must_shed:
            remaining = ts + period - now
            whole = -((-remaining) // one_second)  # ceil on timedelta, no floats
            return count, max(1, whole)
    raise AssertionError("unreachable: shedding every row empties the window")


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
