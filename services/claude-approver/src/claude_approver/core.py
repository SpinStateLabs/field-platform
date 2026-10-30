"""The approver loop: one synchronous ``tick()`` with injectable clients.

Per tick, for every Console agent in the agent map:

1. ``beta.sessions.list(agent_id=...)`` (auto-paginated; archived sessions are
   excluded by the API default). Only sessions whose ``agent.id`` is that
   mapped id are touched; ``CLAUDE_APPROVER_ENVIRONMENT_ID`` narrows further.
2. For an ``idle`` session, the new events since the per-session cursor are
   read (``events.list(created_at_gte=<last processed_at>, order="asc")``,
   deduplicated by event id; the first read takes everything). The session
   object carries no ``stop_reason`` in the SDK (v2.3.0), so it is read off
   the latest ``session.status_idle`` event. When it is ``requires_action``,
   every ``agent.tool_use`` / ``agent.mcp_tool_use`` with
   ``evaluated_permission == "ask"`` and no ``user.tool_confirmation`` naming
   it is checked with the sentinel and answered; all of one session's
   confirmations go in one ``events.send``. A session with an unanswered
   ``agent.custom_tool_use`` is left untouched (v0 does not execute custom
   tools; counted ``custom_tool_pending``).
3. Usage: the session object's cumulative ``usage`` is compared with the last
   snapshot POSTED for that session (``$FIELD_DATA_DIR/claude-approver/
   usage-cursor.json``) and only the positive delta goes to the governor; the
   cursor moves only on a 201.

THE RULE: an ``allow`` is produced in exactly one place, ``_check``, and only
for a 200 whose JSON body has ``decision == "ALLOW"`` exactly. Every other
outcome (exception, timeout, non-200, non-JSON, non-object, unknown decision,
unusable map entry, unreadable estate secret, invalid tool map) is a deny.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote

import httpx

from field_core.authn import HEADER as AUTH_HEADER
from field_core.authn import auth_headers

from claude_approver import config
from claude_approver.config import AgentEntry, AgentMap, ToolMap

log = logging.getLogger("claude_approver")

SENTINEL_TIMEOUT_S = 10.0
HEARTBEAT_TIMEOUT_S = 5.0
GOVERNOR_TIMEOUT_S = 10.0
#: Upper bound on a deny_message (the API limit is not documented; a reject
#: would leave the call unanswered, which is still a fail-closed outcome).
DENY_MESSAGE_MAX = 1000
#: An idle session whose ``updated_at`` has not moved and that had nothing
#: pending is re-read at most this often (Managed Agents' 600 RPM org limit).
EVENTS_REFRESH_SECONDS = 60.0
DECISIONS_KEPT = 500
#: Confirmations remembered per session as "possibly sent" (a send that failed after the API may have applied it).
POSSIBLY_SENT_MAX = 64
#: After a send of UNKNOWN outcome, only these refusals mean "already confirmed" (the API's answer to a duplicate:
#: 400 "already confirmed", or 409): anything else a 4xx can say (401/403 a revoked key, 404, 422 ...) is a
#: permanent refusal and stays `confirm_rejected` (C-409, reviewer C-404 F-C404-1, coordinator ruling).
DUPLICATE_STATUSES = (400, 409)
HALT_POLL_INTERVAL_S = 0.2
REASON_MAX = 512

ASK_TYPES = ("agent.tool_use", "agent.mcp_tool_use")
#: Session statuses ``/halt`` may archive. ``running`` and ``rescheduling``
#: (SDK v2.3.0 literal: rescheduling | running | idle | terminated) are live.
ARCHIVABLE = frozenset({"idle", "terminated"})
ESCALATE_PREFIX = "escalated: a human holds this item; "
ORIGIN_HEADER = "x-field-kill-origin"
ORIGIN_VALUE = "kill-switch"
REASON_HEADER = "x-field-kill-reason"

REASON_CLASSES = (
    "sentinel_block", "sentinel_escalate", "sentinel_error", "unmapped", "config_error",
)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Attribute access for SDK models, key access for dicts."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_datetime(value: Any) -> datetime:
    """An aware datetime from a datetime or an ISO-8601 string (a trailing ``Z`` read as UTC, a naive time as
    UTC); TypeError for anything else, ValueError for an unparseable string."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        text = value.strip()
        moment = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
    else:
        raise TypeError(type(value).__name__)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _time_or_none(value: Any) -> datetime | None:
    """The instant a datetime or an ISO string names, or None for anything that is not a time."""
    try:
        return _as_datetime(value)
    except (TypeError, ValueError):
        return None


def _later(a: Any, b: Any) -> bool:
    """``a > b`` for processed_at values (datetimes from the SDK). Times are compared as the instants they name
    (C-419, C-430): text order is wrong inside one calendar day (``str(datetime)`` has a space where an ISO string
    has a ``T``) and across offsets (``14:30+02:00`` is 12:30Z but sorts after ``13:00Z``). A value that is NOT a
    time is never later than a real time and any real time is later than it (C-438, reviewer C-437 F-C437-1):
    ``_read_events`` sends the cursor back as ``created_at_gte``, so one unparsable ``processed_at`` must not
    become the cursor and stay there. Two values that are neither times compare by their own order, or as text
    when they have none; two datetimes compare directly."""
    if isinstance(a, datetime) and isinstance(b, datetime):
        try:
            return a > b
        except TypeError:             # one naive, one aware: read both as instants below
            pass
    ta, tb = _time_or_none(a), _time_or_none(b)
    if ta is not None and tb is not None:
        return ta > tb
    if ta is not None:
        return True                   # a real time is later than anything that is not one
    if tb is not None:
        return False                  # and nothing that is not a time is later than a real time
    try:
        return a > b
    except TypeError:
        return str(a) > str(b)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exc_label(exc: BaseException) -> str:
    """A label for an exception that can never carry a secret: the class name
    and, for SDK HTTP errors, the status code. Never ``str(exc)``."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    return f"{name} {status}" if isinstance(status, int) else name


#: 4xx answers that are NOT a refusal of the request itself: retried.
_RETRYABLE_4XX = frozenset({408, 429})


def _is_rejection(exc: BaseException) -> bool:
    """True for an SDK HTTP error with a 4xx status (bar 408/429): the API
    refused this request and will refuse it again. Transport errors and 5xx
    carry no such status and are retried."""
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and 400 <= status < 500 and status not in _RETRYABLE_4XX


def _rejection_outcome(exc: BaseException) -> str:
    """``conflict`` for a rejection that is how the API answers a duplicate confirmation, else ``rejected``."""
    return "conflict" if getattr(exc, "status_code", None) in DUPLICATE_STATUSES else "rejected"


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile; ``None`` for no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil(n * pct / 100)
    return ordered[int(rank) - 1]


@dataclass
class Verdict:
    result: str  # "allow" | "deny"
    reason_class: str  # "allowed" or one of REASON_CLASSES
    deny_message: str | None = None
    decision: str | None = None  # the sentinel's decision string, when it gave one
    clause_id: str | None = None
    ms_sentinel: float | None = None
    shadowed: bool = False


@dataclass
class Estate:
    """Where one agent's FIELD calls go. The perimeter header is NOT held
    here: ``headers()`` reads it at call time, once per request, so a rotated
    or removed ``secret_file`` is honoured by the very next call."""

    sentinel: str
    killswitch: str
    governor: str
    routed: bool  # True when the map entry named an estate_base_url
    secret_file: str | None = None

    def headers(self) -> dict[str, str] | None:
        """``None`` when a configured secret file is unreadable or blank."""
        if not self.routed:
            return auth_headers()
        if not self.secret_file:
            return {}
        secret = config.read_secret_file(self.secret_file)
        return {AUTH_HEADER: secret} if secret is not None else None


def estate_for(entry: AgentEntry) -> Estate:
    if entry.estate_base_url:
        base = entry.estate_base_url
        return Estate(f"{base}/sentinel", f"{base}/killswitch", f"{base}/governor", True,
                      entry.secret_file)
    return Estate(config.sentinel_url(), config.killswitch_url(), config.governor_url(), False)


@dataclass
class SessionState:
    console_id: str = ""
    cursor: Any = None  # newest processed_at seen
    seen: set[str] = field(default_factory=set)
    asks: dict[str, Any] = field(default_factory=dict)  # event id -> ask event, unanswered
    ask_seq: dict[str, int] = field(default_factory=dict)  # event id -> read order
    answered: set[str] = field(default_factory=set)  # tool_use_ids confirmed (by anyone)
    #: asks never to be answered again: a confirmation the API rejected 4xx, or
    #: an ask the latest requires_action idle did not list (an interrupted turn)
    stale: set[str] = field(default_factory=set)
    customs: dict[str, Any] = field(default_factory=dict)  # unanswered custom tool uses
    stop_reason: str | None = None
    #: ``stop_reason.event_ids`` of the latest status_idle; None when absent
    stop_event_ids: list[str] | None = None
    #: event id -> the result ("allow" or "deny") of a confirmation whose send failed with an UNKNOWN outcome (5xx,
    #: transport error, 408, 429: the API may have applied it). The next tick still takes a FRESH sentinel verdict (a
    #: kill or a revoked token since must win), and a 4xx for the event then means "already applied", not
    #: "rejected" (C-258). Bounded by POSSIBLY_SENT_MAX, oldest forgotten first.
    possibly_sent: dict[str, str] = field(default_factory=dict)
    idle_seq: int = -1  # read order of the latest status_idle
    seq: int = 0
    updated_at: Any = None
    last_read: float | None = None


class UsageCursor:
    """Last usage snapshot POSTED per session, persisted with an atomic
    replace so a restart never re-posts a delta the governor already has.

    A cursor file that exists but cannot be parsed disables usage posting
    (``error`` is set and shown on ``/stats``) rather than starting from zero,
    which would double-post every session's history."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict[str, int]] = {}
        self.error: str | None = None
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:
            self.error = "usage cursor unreadable"
            return
        try:
            raw = json.loads(text)
            if not isinstance(raw, dict):
                raise ValueError
            data: dict[str, dict[str, int]] = {}
            for sid, snap in raw.items():
                if not isinstance(snap, dict):
                    raise ValueError
                data[str(sid)] = {k: int(snap.get(k, 0)) for k in USAGE_FIELDS}
            self.data = data
        except (ValueError, TypeError):
            self.error = "usage cursor is corrupt"

    def get(self, sid: str) -> dict[str, int]:
        return dict(self.data.get(sid) or {k: 0 for k in USAGE_FIELDS})

    def set(self, sid: str, snap: dict[str, int]) -> None:
        """Persist FIRST, then advance the in-memory cursor: if the write
        fails (OSError propagates) memory is unchanged, so the next tick
        re-posts the delta rather than losing it from disk."""
        new = dict(self.data)
        new[sid] = dict(snap)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(json.dumps(new, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self.data = new


#: governor UsageRequest field -> Session.usage attribute (SDK v2.3.0
#: BetaManagedAgentsSessionUsage). Cache-creation tokens have no governor
#: field (UsageRequest is extra="forbid") and are not metered: README LIMITS.
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens")
_USAGE_SOURCE = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_tokens": "cache_read_input_tokens",
}


def default_cursor_path() -> Path:
    return config.data_dir() / "claude-approver" / "usage-cursor.json"


class Approver:
    def __init__(
        self,
        *,
        client: Any = None,
        client_factory: Callable[[str], Any] | None = None,
        http: httpx.Client | None = None,
        cursor_path: Path | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if client_factory is None:
            from claude_approver.client import make_client

            client_factory = make_client
        self._fixed_client = client
        self._factory = client_factory
        self._client: Any = None
        self._client_key_fp: int | None = None
        self.http = http or httpx.Client(follow_redirects=False)
        self.cursor = UsageCursor(cursor_path or default_cursor_path())
        self.sleep = sleep
        self.clock = clock
        self.sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()  # guards counters/decisions
        self._tick_lock = threading.Lock()  # one tick at a time
        self.counters: dict[str, int] = {
            "allowed": 0, "heartbeats": 0, "heartbeat_failures": 0, "usage_posts": 0,
            "usage_failures": 0, "ticks": 0, "tick_errors": 0, "send_failures": 0,
            "list_failures": 0, "custom_tool_pending": 0, "confirm_rejected": 0,
            "asks_superseded": 0, "confirm_duplicate": 0, "confirm_duplicate_conflict": 0,
        }
        self.denied: dict[str, int] = {c: 0 for c in REASON_CLASSES}
        self.decisions: deque[dict[str, Any]] = deque(maxlen=DECISIONS_KEPT)
        self.last_tick_at: str | None = None
        self.last_error: str | None = None
        self.last_tick_had_client = False
        self.map_error: str | None = None
        self.tool_map_error: str | None = None
        self.custom_seen: set[str] = set()
        self.custom_pending_now = 0
        self.agents_mapped = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ client

    def get_client(self) -> Any:
        """The Managed Agents client, or ``None`` without a readable key.

        The key file is re-read every call; a changed key rebuilds the client
        (only a hash of the key is kept for the comparison)."""
        if self._fixed_client is not None:
            return self._fixed_client
        key = config.read_api_key()
        if key is None:
            self._client = None
            self._client_key_fp = None
            return None
        fp = hash(key)
        if self._client is None or fp != self._client_key_fp:
            try:
                self._client = self._factory(key)
            except Exception as exc:  # never str(exc): it could echo the key
                self._note_error(f"client construction failed ({_exc_label(exc)})")
                self._client = None
                return None
            self._client_key_fp = fp
        return self._client

    # ---------------------------------------------------------------- metrics

    def _note_error(self, label: str) -> None:
        with self._lock:
            self.last_error = label
        log.warning("claude-approver: %s", label)

    def _count(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + n

    def stats(self) -> dict[str, Any]:
        with self._lock:
            decisions = list(self.decisions)
            counters = dict(self.counters)
            denied = dict(self.denied)
            out: dict[str, Any] = {
                **counters,
                "denied": denied,
                "denied_total": sum(denied.values()),
                "last_tick_at": self.last_tick_at,
                "last_error": self.last_error,
                "agent_map_error": self.map_error,
                "tool_map_error": self.tool_map_error,
                "usage_cursor_error": self.cursor.error,
                "custom_tool_pending_now": self.custom_pending_now,
                "agents_mapped": self.agents_mapped,
            }
        ms_s = [d["ms_sentinel"] for d in decisions if d.get("ms_sentinel") is not None]
        ms_t = [d["ms_total"] for d in decisions if d.get("ms_total") is not None]
        out["latency"] = {
            "n": len(decisions),
            "ms_sentinel_p50": percentile(ms_s, 50), "ms_sentinel_p95": percentile(ms_s, 95),
            "ms_total_p50": percentile(ms_t, 50), "ms_total_p95": percentile(ms_t, 95),
        }
        out["decisions"] = decisions
        return out

    # ------------------------------------------------------------- sentinel

    def _check(self, entry: AgentEntry, estate: Estate, action: str, context: dict) -> Verdict:
        """One sentinel round trip. The ONLY producer of ``allow``."""
        headers = estate.headers()  # read per request (a rotated secret_file is honoured)
        if headers is None:
            return Verdict("deny", "config_error", "claude-approver: estate secret unreadable")
        body = {
            "agent_id": entry.field_agent_id,
            "action": action,
            "token_id": entry.token_id,
            "irreversible": False,
            "context": context,
        }
        t0 = time.perf_counter()
        try:
            resp = self.http.post(
                f"{estate.sentinel}/check", json=body, headers=headers,
                timeout=SENTINEL_TIMEOUT_S,
            )
        except httpx.TimeoutException:
            return Verdict("deny", "sentinel_error", "claude-approver: sentinel timed out",
                           ms_sentinel=_ms(t0))
        except Exception as exc:
            return Verdict("deny", "sentinel_error",
                           f"claude-approver: sentinel unreachable ({type(exc).__name__})",
                           ms_sentinel=_ms(t0))
        ms = _ms(t0)
        if resp.status_code != 200:
            return Verdict("deny", "sentinel_error",
                           f"claude-approver: sentinel answered HTTP {resp.status_code}",
                           ms_sentinel=ms)
        try:
            data = resp.json()
        except Exception:
            return Verdict("deny", "sentinel_error", "claude-approver: sentinel answered non-JSON",
                           ms_sentinel=ms)
        if not isinstance(data, dict):
            return Verdict("deny", "sentinel_error",
                           "claude-approver: sentinel answered a non-object", ms_sentinel=ms)
        decision = data.get("decision")
        clause = data.get("clause_id")
        clause = clause if isinstance(clause, str) and clause else None
        reasons = data.get("reasons")
        reasons_text = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) else ""
        if decision == "ALLOW":
            ctx = data.get("context")
            shadowed = bool(isinstance(ctx, dict) and ctx.get("shadowed") is True)
            return Verdict("allow", "allowed", None, "ALLOW", clause, ms, shadowed)
        if decision == "BLOCK":
            return Verdict("deny", "sentinel_block",
                           f"{clause or 'no clause'}: {reasons_text}", "BLOCK", clause, ms)
        if decision == "ESCALATE":
            return Verdict("deny", "sentinel_escalate",
                           f"{ESCALATE_PREFIX}{clause or 'no clause'}: {reasons_text}",
                           "ESCALATE", clause, ms)
        return Verdict("deny", "sentinel_error",
                       "claude-approver: sentinel answered an unknown decision", ms_sentinel=ms)

    def _heartbeat(self, entry: AgentEntry, estate: Estate) -> None:
        """Best effort: a failure is logged and counted, never raised, and
        never changes a verdict that has already been sent."""
        headers = estate.headers()
        if headers is None:
            self._count("heartbeat_failures")
            return
        try:
            resp = self.http.post(
                f"{estate.killswitch}/heartbeat/{quote(entry.field_agent_id or '', safe='')}",
                headers=headers, timeout=HEARTBEAT_TIMEOUT_S,
            )
            ok = 200 <= resp.status_code < 300
        except Exception as exc:
            ok = False
            self._note_error(f"heartbeat failed ({type(exc).__name__})")
        self._count("heartbeats" if ok else "heartbeat_failures")

    # ------------------------------------------------------------------ tick

    def tick(self) -> dict[str, Any]:
        """One poll cycle. Never raises; returns a small summary."""
        with self._tick_lock:
            summary = {"sessions": 0, "answered": 0, "usage_posts": 0}
            try:
                self._tick(summary)
            except Exception as exc:  # the poller must survive anything
                self._count("tick_errors")
                self._note_error(f"tick failed ({_exc_label(exc)})")
            with self._lock:
                self.counters["ticks"] += 1
                self.last_tick_at = _now_iso()
            return summary

    def _tick(self, summary: dict[str, Any]) -> None:
        client = self.get_client()
        self.last_tick_had_client = client is not None
        amap = config.load_agent_map()
        tmap = config.load_tool_map()
        with self._lock:
            self.map_error = amap.error
            self.tool_map_error = tmap.error
        if client is None:
            return
        self.cursor.load()
        env_filter = config.environment_filter()
        model_cache: dict[str, str] = {}
        listed: set[str] = set()
        unlisted_agents: set[str] = set()
        pending_custom = 0
        for console_id, entry in amap.entries.items():
            try:
                sessions = list(client.beta.sessions.list(agent_id=console_id))
            except Exception as exc:
                self._count("list_failures")
                self._note_error(f"sessions.list failed ({_exc_label(exc)})")
                unlisted_agents.add(console_id)
                continue
            for session in sessions:
                sid = _get(session, "id")
                if not sid or _get(_get(session, "agent"), "id") != console_id:
                    continue  # never touch a session the filter should not have returned
                if env_filter and _get(session, "environment_id") != env_filter:
                    continue
                if _get(session, "archived_at") is not None:
                    continue
                listed.add(sid)
                summary["sessions"] += 1
                status = _get(session, "status")
                if status == "idle":
                    summary["answered"] += self._approve_session(
                        client, session, entry, tmap,
                    )
                    pending_custom += len(self.sessions.get(sid, SessionState()).customs)
                if entry.problem is None:
                    if self._post_usage(client, session, entry, model_cache):
                        summary["usage_posts"] += 1
        for sid, st in list(self.sessions.items()):
            # forget sessions that left the listing (archived, deleted, unmapped);
            # keep the state of an agent whose listing failed this tick
            if sid not in listed and st.console_id not in unlisted_agents:
                del self.sessions[sid]
        with self._lock:
            self.custom_pending_now = pending_custom
            self.agents_mapped = len(amap.entries)

    # ------------------------------------------------------------- approvals

    def _read_events(self, client: Any, sid: str, state: SessionState) -> None:
        params: dict[str, Any] = {"session_id": sid, "order": "asc"}
        if state.cursor is not None:
            params["created_at_gte"] = state.cursor
        for ev in client.beta.sessions.events.list(**params):
            eid = _get(ev, "id")
            if not eid or eid in state.seen:
                continue
            state.seen.add(eid)
            state.seq += 1
            etype = _get(ev, "type")
            if etype in ASK_TYPES:
                if (_get(ev, "evaluated_permission") == "ask" and eid not in state.answered
                        and eid not in state.stale):
                    state.asks[eid] = ev
                    state.ask_seq[eid] = state.seq
            elif etype == "user.tool_confirmation":
                tid = _get(ev, "tool_use_id")
                if tid:
                    state.answered.add(tid)
                    state.asks.pop(tid, None)
                    state.possibly_sent.pop(tid, None)
            elif etype == "agent.custom_tool_use":
                state.customs[eid] = ev
                state.ask_seq[eid] = state.seq
            elif etype == "user.custom_tool_result":
                state.customs.pop(_get(ev, "custom_tool_use_id"), None)
            elif etype == "session.status_idle":
                stop = _get(ev, "stop_reason")
                state.stop_reason = _get(stop, "type")
                ids = _get(stop, "event_ids")
                state.stop_event_ids = (
                    [str(i) for i in ids] if isinstance(ids, (list, tuple)) else None)
                state.idle_seq = state.seq
            elif etype in ("session.status_running", "session.status_rescheduled",
                           "session.status_terminated"):
                state.stop_reason = None
                state.stop_event_ids = None
            processed = _get(ev, "processed_at")
            # C-445 (reviewer C-443 F-C443-1): a value that is not a time is never stored as the cursor, not even
            # when nothing better is known yet: the cursor goes back to the API as `created_at_gte`
            if (processed is not None and _time_or_none(processed) is not None
                    and (state.cursor is None or _later(processed, state.cursor))):
                state.cursor = processed

    def _approve_session(self, client: Any, session: Any, entry: AgentEntry,
                         tmap: ToolMap) -> int:
        sid = _get(session, "id")
        state = self.sessions.setdefault(sid, SessionState(console_id=entry.console_agent_id))
        updated = _get(session, "updated_at")
        now = self.clock()
        fresh = (
            updated is not None and updated == state.updated_at and not state.asks
            and not state.customs and state.last_read is not None
            and now - state.last_read < EVENTS_REFRESH_SECONDS
        )
        if not fresh:
            try:
                self._read_events(client, sid, state)
            except Exception as exc:
                self._count("list_failures")
                self._note_error(f"events.list failed ({_exc_label(exc)})")
                return 0
            state.updated_at = updated
            state.last_read = now
        if state.stop_reason == "requires_action" and state.stop_event_ids is not None:
            self._drop_superseded(state)
        for cid in state.customs:
            if cid not in self.custom_seen:
                self.custom_seen.add(cid)
                self._count("custom_tool_pending")
        if state.stop_reason != "requires_action" or not state.asks:
            return 0
        if state.customs:
            return 0  # v0 executes no custom tool: leave the session untouched
        if state.stop_event_ids is None:
            eligible = list(state.asks)  # no event_ids on the idle event: every open ask
        else:
            listed = set(state.stop_event_ids)
            eligible = [eid for eid in state.asks if eid in listed]
        if not eligible:
            return 0
        return self._answer(client, session, entry, tmap, state, eligible)

    def _drop_superseded(self, state: SessionState) -> None:
        """The latest ``requires_action`` idle names the events the session is
        blocked on (``stop_reason.event_ids``). An ask or custom tool use read
        BEFORE that idle and not named by it belongs to an earlier turn (one
        ended by ``user.interrupt``, say): it is never answered, now or later."""
        listed = set(state.stop_event_ids or ())
        for pending in (state.asks, state.customs):
            for eid in list(pending):
                if eid not in listed and state.ask_seq.get(eid, state.seq + 1) < state.idle_seq:
                    del pending[eid]
                    state.stale.add(eid)
                    state.possibly_sent.pop(eid, None)
                    self._count("asks_superseded")

    def _answer(self, client: Any, session: Any, entry: AgentEntry, tmap: ToolMap,
                state: SessionState, eligible: list[str]) -> int:
        sid = _get(session, "id")
        console_id = entry.console_agent_id
        estate = estate_for(entry) if entry.problem is None else None
        planned: list[tuple[str, dict, dict]] = []  # (event id, confirmation, record)
        for eid in eligible:
            ev = state.asks[eid]
            t_start = time.perf_counter()
            tool = _get(ev, "name") or ""
            action: str | None = None
            if entry.problem is not None:
                verdict = Verdict("deny", "unmapped", f"claude-approver: {entry.problem}")
            elif tmap.error is not None:
                verdict = Verdict("deny", "config_error", f"claude-approver: {tmap.error}")
            elif not tool:
                verdict = Verdict("deny", "sentinel_error", "claude-approver: tool event has no name")
            else:
                action = config.resolve_action(tool, entry, tmap)
                context = {
                    "source": "claude-approver",
                    "console_session_id": sid,
                    "console_agent_id": console_id,
                    "tool_name": tool,
                    "event_id": eid,
                    "event_type": _get(ev, "type"),
                }
                server = _get(ev, "mcp_server_name")
                if server:
                    context["mcp_server_name"] = server
                thread = _get(ev, "session_thread_id")
                if thread:
                    context["session_thread_id"] = thread
                verdict = self._check(entry, estate, action, context)
            confirmation: dict[str, Any] = {
                "type": "user.tool_confirmation", "tool_use_id": eid, "result": verdict.result,
            }
            if verdict.result == "deny":
                confirmation["deny_message"] = (verdict.deny_message or "claude-approver: denied")[
                    :DENY_MESSAGE_MAX]
            record = {
                "at": _now_iso(), "console_session_id": sid, "event_id": eid,
                "tool_name": tool, "action": action, "decision": verdict.result,
                "sentinel_decision": verdict.decision, "reason_class": verdict.reason_class,
                "clause_id": verdict.clause_id, "shadowed": verdict.shadowed,
                "ms_sentinel": verdict.ms_sentinel, "_t0": t_start,
            }
            planned.append((eid, confirmation, record))
        if not planned:
            return 0
        outcomes = self._send(client, sid, [c for _, c, _ in planned])
        done = 0
        for (eid, confirmation, record), outcome in zip(planned, outcomes):
            t0 = record.pop("_t0")
            record["ms_total"] = _ms(t0)
            ok = outcome == "sent"
            record["sent"] = ok
            if outcome in ("rejected", "conflict"):
                record["rejected"] = True
            with self._lock:
                self.decisions.append(record)
                if ok:
                    if record["decision"] == "allow":
                        self.counters["allowed"] += 1
                    else:
                        self.denied[record["reason_class"]] = (
                            self.denied.get(record["reason_class"], 0) + 1)
            if outcome in ("rejected", "conflict"):
                state.asks.pop(eid, None)
                remembered = state.possibly_sent.pop(eid, None)
                if remembered is not None and outcome == "conflict":
                    # an earlier send may have been applied and this one is the API refusing a duplicate (400/409):
                    # the ask is answered, not stranded (C-258). Counted as a duplicate; not counted as allowed or
                    # denied here. The record carries what the EARLIER send said (C-409): if the new verdict differs
                    # (a kill since), the effective answer may be the earlier one, and that is counted too.
                    record["possibly_applied"] = remembered
                    state.answered.add(eid)
                    self._count("confirm_duplicate")
                    if remembered != confirmation["result"]:
                        self._count("confirm_duplicate_conflict")
                    continue
                # terminal: the API will not take this confirmation; never
                # re-check the sentinel or re-send for this event
                state.stale.add(eid)
                self._count("confirm_rejected")
                continue
            if not ok:
                # 5xx / transport / 408 / 429: the confirmation MAY have been applied. Remember that, bounded, so a
                # 4xx on the next tick's send is read as "already applied" (the next tick still re-checks the sentinel)
                state.possibly_sent[eid] = confirmation["result"]
                while len(state.possibly_sent) > POSSIBLY_SENT_MAX:
                    del state.possibly_sent[next(iter(state.possibly_sent))]
                continue
            done += 1
            state.answered.add(eid)
            state.asks.pop(eid, None)
            state.possibly_sent.pop(eid, None)
            if estate is not None and record["reason_class"] != "unmapped":
                self._heartbeat(entry, estate)
        return done

    def _send(self, client: Any, sid: str, confirmations: list[dict]) -> list[str]:
        """All of one session's confirmations in one ``events.send``. Returns
        one outcome per confirmation: ``sent``, ``rejected`` (a 4xx on a
        single-event send: terminal), ``conflict`` (a rejection whose status is one of ``DUPLICATE_STATUSES``: terminal
        too, unless an earlier send of the event may have been applied) or ``retry`` (5xx, transport error, 408, 429:
        the next tick tries again).

        A batch the API REJECTS (4xx) is split and each confirmation sent
        alone, so one stale confirmation (someone answered it in the Console
        meanwhile) cannot strand the rest; a batch that fails any other way is
        not split (no burst of N sends against a failing API)."""
        n = len(confirmations)
        try:
            client.beta.sessions.events.send(session_id=sid, events=confirmations)
            return ["sent"] * n
        except Exception as exc:
            self._count("send_failures")
            self._note_error(f"events.send failed ({_exc_label(exc)})")
            if not _is_rejection(exc):
                return ["retry"] * n
            first_outcome = _rejection_outcome(exc)
        if n == 1:
            return [first_outcome]
        results = []
        for c in confirmations:
            try:
                client.beta.sessions.events.send(session_id=sid, events=[c])
                results.append("sent")
            except Exception as exc:
                self._count("send_failures")
                self._note_error(f"events.send failed ({_exc_label(exc)})")
                results.append(_rejection_outcome(exc) if _is_rejection(exc) else "retry")
        return results

    # ----------------------------------------------------------------- usage

    def _model_for(self, client: Any, session: Any, console_id: str,
                   cache: dict[str, str]) -> str:
        """The session's own agent snapshot (``session.agent.model.id``) first,
        then ``agents.retrieve`` (cached per tick), else ``unknown`` (the
        governor then ledgers ``usage.unpriced``, a visible signal)."""
        snap = _get(_get(_get(session, "agent"), "model"), "id")
        if isinstance(snap, str) and snap:
            return snap
        if console_id not in cache:
            model = "unknown"
            try:
                agent = client.beta.agents.retrieve(console_id)
                m = _get(agent, "model")
                mid = m if isinstance(m, str) else _get(m, "id")
                if isinstance(mid, str) and mid:
                    model = mid
            except Exception as exc:
                self._note_error(f"agents.retrieve failed ({_exc_label(exc)})")
            cache[console_id] = model
        return cache[console_id]

    def _usage_snapshot(self, client: Any, session: Any) -> dict[str, int] | None:
        usage = _get(session, "usage")
        if usage is None:
            try:
                page = client.beta.sessions.events.list(
                    session_id=_get(session, "id"), types=["session.usage"], order="desc", limit=1,
                )
                ev = next(iter(page), None)
            except Exception as exc:
                self._note_error(f"events.list failed ({_exc_label(exc)})")
                return None
            usage = _get(ev, "usage")
            if usage is None:
                return None
        snap: dict[str, int] = {}
        for k, src in _USAGE_SOURCE.items():
            v = _get(usage, src)
            snap[k] = int(v) if isinstance(v, (int, float)) and v >= 0 else 0
        return snap

    def _post_usage(self, client: Any, session: Any, entry: AgentEntry,
                    model_cache: dict[str, str]) -> bool:
        if self.cursor.error is not None:
            return False
        sid = _get(session, "id")
        snap = self._usage_snapshot(client, session)
        if snap is None:
            return False
        last = self.cursor.get(sid)
        delta = {k: max(0, snap[k] - last.get(k, 0)) for k in USAGE_FIELDS}
        if not any(delta.values()):
            return False
        estate = estate_for(entry)
        body = {
            "agent_id": entry.field_agent_id,
            "model": self._model_for(client, session, entry.console_agent_id, model_cache),
            **delta,
            "note": f"console session {sid}",
        }
        headers = estate.headers()  # read per request
        if headers is None:
            self._count("usage_failures")
            self._note_error("usage post skipped (estate secret unreadable)")
            return False
        try:
            resp = self.http.post(f"{estate.governor}/usage", json=body, headers=headers,
                                  timeout=GOVERNOR_TIMEOUT_S)
        except Exception as exc:
            self._count("usage_failures")
            self._note_error(f"usage post failed ({type(exc).__name__})")
            return False
        if resp.status_code != 201:
            self._count("usage_failures")
            self._note_error(f"usage post answered HTTP {resp.status_code}")
            return False
        try:
            self.cursor.set(sid, {k: max(snap[k], last.get(k, 0)) for k in USAGE_FIELDS})
        except OSError as exc:
            # posted but not recorded: UsageCursor.set writes the file before it
            # advances memory, so memory is unchanged and the next tick re-posts
            # this delta (an over-count the governor ledgers, never a loss)
            self._note_error(f"usage cursor write failed ({type(exc).__name__})")
        self._count("usage_posts")
        return True

    # ------------------------------------------------------------------ halt

    def halt(self, field_agent_id: str, reason: str | None) -> tuple[int, dict[str, Any]]:
        """Interrupt, wait for ``idle``/``terminated``, archive. Returns (status, body).

        Every interrupt is sent first (one pass), then each session is polled
        and archived, so the interrupts land inside a short caller timeout
        even when the archive wait is long. Only ``idle`` and ``terminated``
        are archivable: a session still ``running`` or ``rescheduling`` (a live
        session being moved) after ``CLAUDE_APPROVER_HALT_WAIT_SECONDS`` is
        reported ``archived: false`` and is never force-archived."""
        amap = config.load_agent_map()
        consoles = amap.consoles_for(field_agent_id)
        if not consoles:
            return 404, {"detail": "agent is not in CLAUDE_APPROVER_AGENT_MAP"}
        client = self.get_client()
        if client is None:
            return 503, {"detail": "no Managed Agents client (API key file absent or unreadable)"}
        wait = config.halt_wait_seconds()
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        targets: list[dict[str, Any]] = []
        for cid in consoles:
            try:
                sessions = list(client.beta.sessions.list(agent_id=cid))
            except Exception as exc:
                errors.append({"console_agent_id": cid, "error": f"sessions.list failed ({_exc_label(exc)})"})
                continue
            for s in sessions:
                sid = _get(s, "id")
                if not sid or _get(_get(s, "agent"), "id") != cid:
                    continue
                if _get(s, "archived_at") is not None or _get(s, "status") == "terminated":
                    continue
                targets.append({"id": sid, "interrupted": False, "archived": False,
                                "final_status": _get(s, "status")})
        for r in targets:
            try:
                client.beta.sessions.events.send(session_id=r["id"], events=[{"type": "user.interrupt"}])
                r["interrupted"] = True
            except Exception as exc:
                r["error"] = f"interrupt failed ({_exc_label(exc)})"
        for r in targets:
            deadline = self.clock() + wait
            status = r["final_status"]
            try:
                while True:
                    status = _get(client.beta.sessions.retrieve(r["id"]), "status")
                    if status in ARCHIVABLE or self.clock() >= deadline:
                        break
                    self.sleep(HALT_POLL_INTERVAL_S)
            except Exception as exc:
                r["error"] = f"retrieve failed ({_exc_label(exc)})"
                r["final_status"] = status
                continue
            r["final_status"] = status
            if status not in ARCHIVABLE:
                continue
            try:
                client.beta.sessions.archive(r["id"])
                r["archived"] = True
            except Exception as exc:
                r["error"] = f"archive failed ({_exc_label(exc)})"
        results.extend(targets)
        body: dict[str, Any] = {"agent_id": field_agent_id, "reason": reason, "sessions": results}
        if errors:
            body["errors"] = errors
        return 200, body

    # ---------------------------------------------------------------- poller

    def start(self) -> threading.Thread:
        """Run ``tick()`` in a daemon thread every ``CLAUDE_APPROVER_POLL_SECONDS``."""
        if self._thread is not None and self._thread.is_alive():
            return self._thread

        def _loop() -> None:
            while not self._stop.is_set():
                self.tick()
                self._stop.wait(config.poll_seconds())

        self._stop.clear()
        self._thread = threading.Thread(target=_loop, name="claude-approver-poller", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()

    def polling(self) -> bool:
        return bool(self._thread is not None and self._thread.is_alive()
                    and self.last_tick_had_client)


def decode_reason(raw: str | None) -> str | None:
    if raw is None:
        return None
    return unquote(raw)[:REASON_MAX]


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 3)
