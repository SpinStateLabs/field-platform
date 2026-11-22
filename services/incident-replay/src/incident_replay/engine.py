"""Deterministic replay engine.

Everything in the post-mortem is a query result from the ledger, registry,
delegation-authority and the agent's registered FIELD manifest — no
inference, no narration, no LLM. If the ledger chain fails verification, the
report carries an INTEGRITY FAILED banner and says exactly where the chain
broke; nothing after a break is presented as trustworthy. A ledger too busy
to verify is reported as NOT VERIFIED — never as a break, never as OK.

RACI is read from data, and every party carries the label of where it came
from (``raci_sources`` holds the same labels as a map):

- R — the registry owner.
- A — a grant's grantor, judged at the first failure's ledger timestamp
  (see :func:`_accountable`): for ``D.expired`` / ``D.revoked`` the most
  recent grant covering the failing action that had lapsed that way; else the
  earliest grant covering it (exact membership, the sentinel's rule) that was
  in force then; else the earliest window-overlapping grant.
- C — the manifest's ``enforcement.kill_switch.authorized_operators`` when
  non-empty after dropping blank entries, else the clause-letter default.
- I — the manifest's ``identity.principal`` (— org) when not blank, else the
  default.
"""

from __future__ import annotations

from field_core.guarded_operator import perimeter_headers

import os
import re
import time
import unicodedata
from contextvars import ContextVar
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

import httpx

from field_core.clients import (
    AgentNotRegisteredError,
    HttpLike,
    ManifestResolver,
    RegistryClient,
    RegistryUnreachableError,
)

# Which executive is Consulted for a failed clause, by FIELD letter.
CLAUSE_EXEC = {
    "F": "CIO / GC (federation)",
    "I": "CIO (identity)",
    "E": "CISO / CFO (enforcement)",
    "L": "CFO / audit (ledger)",
    "D": "GC (delegation)",
    "R": "CIO (registry)",
}
DEFAULT_CONSULTED = "CISO"
DEFAULT_INFORMED = "CEO / board (attestation-reporter)"

# Verdict event types, exactly as conformance-sentinel writes them
# (engine.py ``_verdict``). In log-only mode a would-block/would-escalate is
# ledgered ONLY as a shadow event carrying ``would_block``, never as
# ``conformance.block`` — a replay that ignored shadows would report a
# violating log-only window as clean.
ENFORCED_FAILURES = ("conformance.block", "conformance.escalate")
SHADOW_FAILURES = ("conformance.shadow_block", "conformance.shadow_escalate")
FAILURE_EVENTS = ENFORCED_FAILURES + SHADOW_FAILURES
LOG_ONLY_LABEL = "(log-only, not enforced)"

# sealed-ledger's contract: a snapshot that cannot stabilise answers /verify
# with HTTP 200 ok=false and a reason starting with this prefix. The check did
# not run — it is not a chain break.
LEDGER_BUSY_PREFIX = "ledger busy:"

# The sentinel's clause for a presented token that was no longer in force,
# keyed to the grant status it reports (conformance-sentinel engine.py step 4).
LAPSED_CLAUSES = {"D.expired": "expired", "D.revoked": "revoked"}


def _instant(value: str) -> datetime:
    """ISO 8601 → aware datetime; naive means UTC (the ledger's rule).

    Instants are compared as datetimes, never as strings: mixed offsets
    (``-05:00`` vs ``+00:00``) mis-order lexically."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


#: The most ledger events one replay reads (S3-12). The ledger's `/events` limit tops out
#: at 10000 and we ask for one more than the cap to detect a cut, so the cap stays below it.
MAX_TIMELINE_EVENTS = 5000
_MAX_TIMELINE_EVENTS_CEILING = 9999


def max_timeline_events() -> int:
    """`FIELD_REPLAY_MAX_EVENTS` as a whole number in 1..9999; anything else (blank,
    non-numeric, non-finite, fractional, out of range) falls back to the default. Read per
    replay so a change needs no restart; the bad value is never echoed."""
    import os
    import re

    raw = os.environ.get("FIELD_REPLAY_MAX_EVENTS", "").strip()
    if not re.fullmatch(r"[0-9]{1,9}", raw):   # 1-9 ASCII digits only: int() takes "5_000", "+100", Unicode digits, and raises past 4300 digits
        return MAX_TIMELINE_EVENTS
    value = int(raw)
    if 1 <= value <= _MAX_TIMELINE_EVENTS_CEILING:
        return value
    return MAX_TIMELINE_EVENTS


#: B-GL-incident-replay-503. A busy ledger refuses a second whole-ledger read with HTTP 503 and a Retry-After
#: (PR 1089's one-in-flight slot). Inside a replay that answer is waited out and the call repeated: each wait at
#: most RETRY_AFTER_CAP_S, MAX_RETRIES_PER_CALL retries per call, FIELD_REPLAY_RETRY_BUDGET_S seconds of waiting in
#: all per replay (default 20; 0 = never retry; a value that is not a whole number of at most 9 digits is 20).
#: When it runs out, ``verify`` answers "ledger busy:" (the replay reports INTEGRITY NOT VERIFIED, never intact and
#: never broken) and ``events`` raises ``LedgerBusyError`` (the API answers 503 + Retry-After). ``_sleep`` is a
#: module name so a test can replace it.
RETRY_BUDGET_ENV = "FIELD_REPLAY_RETRY_BUDGET_S"
DEFAULT_RETRY_BUDGET_S = 20
RETRY_AFTER_CAP_S = 10
MAX_RETRIES_PER_CALL = 3
DEFAULT_REFUSAL_RETRY_AFTER_S = 10
_sleep = time.sleep
_RETRY_LEFT: ContextVar[list[float] | None] = ContextVar("incident_replay_retry_left", default=None)


class LedgerBusyError(RuntimeError):
    """The ledger kept answering 503 inside the replay's retry budget."""

    def __init__(self, message: str, retry_after: int = DEFAULT_REFUSAL_RETRY_AFTER_S):
        super().__init__(message)
        self.retry_after = retry_after


def retry_budget_s() -> int:
    raw = os.environ.get(RETRY_BUDGET_ENV, "").strip()
    return int(raw) if raw.isascii() and raw.isdecimal() and len(raw) <= 9 else DEFAULT_RETRY_BUDGET_S


def _retry_after(resp: Any) -> int | None:
    """Seconds of an integer-seconds Retry-After header on ``resp`` (at most 9 digits), else None."""
    headers = getattr(resp, "headers", None)
    try:
        raw = headers.get("Retry-After") if headers is not None else None
    except Exception:  # noqa: BLE001 - an odd headers object is simply no header
        return None
    raw = raw.strip() if isinstance(raw, str) else ""
    return int(raw) if raw.isascii() and raw.isdecimal() and len(raw) <= 9 else None


class LedgerQueryClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        import os

        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=10.0, headers=perimeter_headers())

    def _get(self, path: str, **kw: Any):
        """GET, waiting out a 503 that carries a Retry-After within the replay's budget (none outside a replay)."""
        left = _RETRY_LEFT.get()
        retries = 0
        while True:
            resp = self._client.get(f"{self._base}{path}", **kw)
            wait = _retry_after(resp) if resp.status_code == 503 else None
            if wait is None or left is None or retries >= MAX_RETRIES_PER_CALL:
                return resp
            wait = min(wait, RETRY_AFTER_CAP_S)
            if wait > left[0]:
                return resp
            left[0] -= wait
            retries += 1
            _sleep(wait)

    def events(self, **params: Any) -> list[dict[str, Any]]:
        resp = self._get("/events", params=params)
        if resp.status_code == 503:
            raise LedgerBusyError(
                f"{LEDGER_BUSY_PREFIX} the ledger answered HTTP 503 to the events read; retry the replay",
                min(_retry_after(resp) or DEFAULT_REFUSAL_RETRY_AFTER_S, RETRY_AFTER_CAP_S))
        resp.raise_for_status()
        return resp.json()

    def verify(self) -> dict[str, Any]:
        resp = self._get("/verify")
        if resp.status_code == 503:
            # The check did not run: the same contract as a 200 ok=false "ledger busy:" (not a break, never OK).
            return {"ok": False, "length": 0,
                    "reason": f"{LEDGER_BUSY_PREFIX} the ledger answered HTTP 503 to /verify (a whole-ledger "
                              "request is already in flight)"}
        resp.raise_for_status()
        return resp.json()

    def health(self) -> dict[str, Any]:
        resp = self._client.get(f"{self._base}/health")
        resp.raise_for_status()
        return resp.json()


class TokenQueryClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        import os

        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_DELEGATION_URL", "http://127.0.0.1:8003"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=10.0, headers=perimeter_headers())

    def tokens(self, agent_id: str) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self._base}/tokens", params={"agent_id": agent_id})
        resp.raise_for_status()
        return resp.json()


AGENT_ID_MAX = 200

#: The registry's own id pattern (agent_registry.models). An id outside it cannot be in the registry, so replay does
#: not ask the registry about it: RegistryClient builds f"{base}/agents/{agent_id}" unquoted, and 'x/../health' or
#: 'a?b=1' would address another route (S5-15). It still replays the ledger trail (ledger-only ids such as the
#: federation broker's 'Org/agent' have events but no registry record).
_REGISTRY_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")


class UpstreamUnavailable(Exception):
    """A dependency the replay cannot do without (ledger, delegation) failed. ``dependency`` is the only text
    that may reach the caller: never the upstream status line or body."""

    def __init__(self, dependency: str):
        self.dependency = dependency
        super().__init__(f"{dependency} unavailable")


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=AGENT_ID_MAX)
    since: str = Field(description="ISO 8601 inclusive lower bound")
    until: str = Field(description="ISO 8601 inclusive upper bound")

    @field_validator("agent_id")
    @classmethod
    def _agent_id_is_one_printable_line(cls, value: str) -> str:
        # fixed text: the value is never repeated. A control, format or line-separator character would break the
        # markdown H1 this id is printed into (and the ledger filter), a blank id selects nothing.
        if not value.strip():
            raise ValueError("agent_id must not be blank")
        if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in value):
            raise ValueError("agent_id must not contain control or line-break characters")
        return value

    @field_validator("since", "until")
    @classmethod
    def _iso_instant(cls, value: str) -> str:
        # Bounds are compared as datetimes below; refuse a non-ISO bound at
        # the edge (422) instead of failing mid-replay. A date alone is
        # refused too: the ledger reads it as 00:00:00 UTC, so until=<day>
        # would drop that whole day and report it clean (attest reads a
        # date-only until as END of day — the conventions disagree).
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError):
            pass
        else:
            raise ValueError(
                f"a date alone is not an instant: {value!r} — give a time "
                f"and offset, e.g. 2026-08-18T00:00:00Z"
            )
        try:
            _instant(value)
        except (TypeError, ValueError):
            raise ValueError(f"not an ISO 8601 instant: {value!r}")
        return value

    @model_validator(mode="after")
    def _window_is_ordered(self) -> "ReplayRequest":
        # Bounds are inclusive, so equal is fine; an inverted window would reach the ledger and come back as an empty
        # timeline, a clean-looking post-mortem for a window that never existed (scout P-15). Compared as instants
        # (offsets differ), and the message repeats neither bound.
        if _instant(self.since) > _instant(self.until):
            raise ValueError("since is later than until: the window is inverted")
        return self


class TimelineEntry(BaseModel):
    ts: str
    event_type: str
    clause_id: str | None = None
    action: str | None = None
    # True: a verdict the sentinel applied; False: a log-only shadow verdict
    # (recorded, caller NOT blocked); None: not a conformance verdict.
    enforced: bool | None = None
    summary: str
    hash: str


class AuthorityGrant(BaseModel):
    token_id: str
    granted_by: str
    scope: list[str]
    issued_at: str
    expires_at: str
    revoked: bool
    revocation_id: str | None = None
    revoked_at: str | None = None

    def covers(self, action: str) -> bool:
        """Exact string membership — the same rule as
        ``field_core.delegation.DelegationToken.covers`` and the sentinel's
        scope check. No paraphrase, no case folding."""
        return action in self.scope

    def status_at(self, at: datetime) -> str | None:
        """``DelegationToken.status`` as it was at instant ``at``: revocation
        wins over expiry, and a grant is expired once ``at >= expires_at``.
        None when the grant was not yet issued, or is revoked with no
        ``revoked_at`` (its status at ``at`` cannot be known)."""
        if _instant(self.issued_at) > at:
            return None
        if self.revoked:
            if self.revoked_at is None:
                return None
            if _instant(self.revoked_at) <= at:
                return "revoked"
        return "expired" if at >= _instant(self.expires_at) else "active"


class PostMortem(BaseModel):
    agent_id: str
    window: dict[str, str]
    generated_at: str
    ledger_integrity_ok: bool
    ledger_integrity_detail: str
    # intact | broken (the chain failed to verify) | unverified (the ledger
    # was busy: no verification result — ok stays false).
    ledger_integrity_status: Literal["intact", "broken", "unverified"]
    agent_record: dict[str, Any] | None
    authority: list[AuthorityGrant]
    timeline: list[TimelineEntry]
    first_failure: TimelineEntry | None
    counts: dict[str, int]
    raci: dict[str, str]
    # Where each RACI party came from (the label printed beside it).
    raci_sources: dict[str, str] = Field(default_factory=dict)
    # The grant Accountable was read from. For D.expired / D.revoked it may
    # have lapsed before the window, so it need not be in ``authority``.
    accountable_grant: AuthorityGrant | None = None
    manifest_resolved: bool = False
    # B0 resolver reason: ok | no_ref | missing | invalid.
    manifest_detail: str = "no_ref"
    # Facts about the evidence base that do not break the chain but limit
    # what the window can show (e.g. archived segments before the window).
    integrity_notes: list[str] = Field(default_factory=list)
    method: str = (
        "deterministic query engine v0.1 over sealed-ledger + agent-registry "
        "+ delegation-authority + the registered FIELD manifest; no LLM, "
        "no narration"
    )


def _clause_id(payload: dict[str, Any]) -> str | None:
    # Shadow verdicts carry the would-be clause as ``would_block`` (for
    # shadow_escalate too); enforced verdicts carry ``clause_id``.
    return payload.get("clause_id") or payload.get("would_block")


def _enforced(event_type: str) -> bool | None:
    if event_type in SHADOW_FAILURES:
        return False
    if event_type.startswith("conformance."):
        return True
    return None


#: A timeline summary is at most this many characters (before the truncation marker): the ledger caps no payload,
#: and an event's whole payload or kill reason must not inflate the post-mortem or its Markdown.
SUMMARY_MAX = 300


def _summarize(event: dict[str, Any]) -> str:
    text = _summary_text(event)
    if len(text) <= SUMMARY_MAX:
        return text
    return f"{text[:SUMMARY_MAX]}…[truncated {len(text) - SUMMARY_MAX} chars]"


def _summary_text(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    et = event["event_type"]
    if et.startswith("conformance."):
        clause = _clause_id(payload)
        text = f"{et.split('.')[1].upper()} '{payload.get('action')}'" + (
            f" [{clause}]" if clause else ""
        )
        if et in SHADOW_FAILURES:
            text += f" {LOG_ONLY_LABEL}"
        return text
    if et == "delegation.mint":
        return (f"token {str(payload.get('token_id'))[:8]}… minted by "
                f"{payload.get('granted_by')} scope={payload.get('scope')}")
    if et == "delegation.revoke":
        return f"token {str(payload.get('token_id'))[:8]}… revoked"
    if et.startswith("kill."):
        return f"{et} by {payload.get('operator', '?')} ({payload.get('reason', '')})"
    if et.startswith("spend."):
        return f"{et} {payload}"
    return et


def _accountable(
    grants: list[AuthorityGrant],
    overlapping: list[AuthorityGrant],
    failure: TimelineEntry | None,
) -> tuple[AuthorityGrant | None, str]:
    """(grant, label) for RACI Accountable. A grant's status is judged at the
    first failure's ledger timestamp — never at replay time — so a grant
    revoked before the failure, or minted after it, is never "covering".

    1. ``D.expired`` / ``D.revoked``: the presented token had lapsed by
       definition, possibly before ``since``, so EVERY grant for the agent is
       a candidate: the most recently issued one covering the action whose
       status then was expired / revoked.
    2. The earliest window-overlapping grant covering the action that was in
       force (``active``) then.
    3. The earliest window-overlapping grant (no failure, or nothing covers).

    ``min``/``max`` keep the first of equal instants, so ties stay in token
    order."""
    action = failure.action if failure else None
    if failure is not None and action is not None:
        at = _instant(failure.ts)
        lapsed = LAPSED_CLAUSES.get(failure.clause_id or "")
        if lapsed:
            candidates = [g for g in grants
                          if g.covers(action) and g.status_at(at) == lapsed]
            if candidates:
                return (max(candidates, key=lambda g: _instant(g.issued_at)),
                        f"{lapsed} grant covering '{action}'")
        covering = [g for g in overlapping
                    if g.covers(action) and g.status_at(at) == "active"]
        if covering:
            return (min(covering, key=lambda g: _instant(g.issued_at)),
                    f"grant covering '{action}'")
    if overlapping:
        return (min(overlapping, key=lambda g: _instant(g.issued_at)),
                "earliest overlapping grant")
    return None, "none"


class ReplayEngine:
    def __init__(
        self,
        ledger: LedgerQueryClient,
        registry: RegistryClient,
        delegation: TokenQueryClient,
        manifests: ManifestResolver | None = None,
    ):
        self.ledger = ledger
        self.registry = registry
        self.delegation = delegation
        # The B0 shared resolver (FIELD_MANIFEST_DIR, mtime cache).
        self.manifests = manifests or ManifestResolver()

    def _earliest_live_note(
        self, since: str, verification: dict[str, Any]
    ) -> str | None:
        """C2 retention: closed segments may be archived out of the live
        ledger. A window that starts before the earliest LIVE event cannot
        show the archived events, so the report says so. A pre-C2 ledger's
        ``/health`` has no ``earliest_live_*`` fields ⇒ no note."""
        try:
            health = self.ledger.health()
        except Exception as exc:
            return (f"earliest-live check unavailable: ledger /health "
                    f"unreadable ({type(exc).__name__})")
        if not isinstance(health, dict):
            return None
        earliest_ts = health.get("earliest_live_ts")
        earliest_index = health.get("earliest_live_index")
        # index 0 is the first event ever written: nothing is archived, so
        # a window starting before it misses nothing.
        if (not earliest_ts or isinstance(earliest_index, bool)
                or not isinstance(earliest_index, int) or earliest_index <= 0):
            return None
        try:
            before = _instant(since) < _instant(earliest_ts)
        except (TypeError, ValueError):
            return (f"earliest-live check unavailable: ledger /health "
                    f"earliest_live_ts is not ISO 8601 ({earliest_ts!r})")
        if not before:
            return None
        archived = health.get("archived_segments")
        if archived is None:
            archived = verification.get("archived_segments")
        return (
            f"window starts before the earliest live event (segments archived: "
            f"{'unknown' if archived is None else archived}) — the earliest "
            f"live event is global index {earliest_index} at {earliest_ts}; "
            f"earlier events are not in the live ledger and not in this report"
        )

    def replay(self, req: ReplayRequest) -> PostMortem:
        token = _RETRY_LEFT.set([float(retry_budget_s())])
        try:
            return self._replay(req)
        finally:
            _RETRY_LEFT.reset(token)

    def _replay(self, req: ReplayRequest) -> PostMortem:
        try:
            verification = self.ledger.verify()   # a 503 is answered inside verify() (main: ok false, busy)
        except (httpx.HTTPError, ValueError) as exc:   # S2-23 (PR 607): any other failure is a 502
            raise UpstreamUnavailable("ledger") from exc
        raw_ok = verification.get("ok")
        integrity_ok = raw_ok is True       # a truthy string or number is not an ok
        reason = verification.get("reason")
        if not isinstance(raw_ok, bool):
            # No verification result: not a break, and never intact.
            integrity_status = "unverified"
            integrity_detail = ("INTEGRITY NOT VERIFIED: the ledger's /verify answer carries no "
                                "boolean ok — retry the replay")
        elif integrity_ok:
            integrity_status = "intact"
            integrity_detail = f"chain intact over {verification.get('length')} events"
        elif isinstance(reason, str) and reason.startswith(LEDGER_BUSY_PREFIX):
            # No verification result: not a break, and never OK.
            integrity_status = "unverified"
            integrity_detail = f"INTEGRITY NOT VERIFIED: {reason} — retry the replay"
        else:
            integrity_status = "broken"
            integrity_detail = f"CHAIN BROKEN: {reason}"
        notes = [n for n in (self._earliest_live_note(req.since, verification),) if n]

        record = None
        registry_unreachable = False
        if _REGISTRY_ID.fullmatch(req.agent_id):
            try:
                record = self.registry.get_agent(req.agent_id)
            except AgentNotRegisteredError:
                record = None
            except RegistryUnreachableError:
                # Not "unregistered": the registry could not be asked. The report is still built (S2-23).
                record = None
                registry_unreachable = True
                notes.append("registry unreachable: the agent record and its owner are not shown")

        manifest, manifest_detail = self.manifests.resolve_detail(
            (record or {}).get("manifest_ref")
        )

        cap = max_timeline_events()
        # One more than the cap, so a cut is detectable. The ledger's `limit` keeps the
        # LAST N matches: the oldest events are the ones a cut drops.
        try:
            events = self.ledger.events(
                agent_id=req.agent_id, since=req.since, until=req.until, limit=cap + 1
            )
        except (httpx.HTTPError, ValueError) as exc:   # S2-23 (PR 607); LedgerBusyError (503) passes through
            raise UpstreamUnavailable("ledger") from exc
        if len(events) > cap:
            events = events[-cap:]
            notes.append(
                f"timeline truncated: showing the newest {cap} of at least {cap + 1} "
                f"events; first_failure may be earlier than the window shown"
            )
        timeline = [
            TimelineEntry(
                ts=e["ts"],
                event_type=e["event_type"],
                clause_id=_clause_id(e.get("payload") or {}),
                action=(e.get("payload") or {}).get("action"),
                enforced=_enforced(e["event_type"]),
                summary=_summarize(e),
                hash=e["hash"],
            )
            for e in events
        ]

        # Enforced and log-only shadow verdicts both count; whichever the
        # ledger recorded first is the first failure.
        first_failure = next(
            (t for t in timeline if t.event_type in FAILURE_EVENTS), None
        )

        counts: dict[str, int] = {}
        for t in timeline:
            counts[t.event_type] = counts.get(t.event_type, 0) + 1

        since, until = _instant(req.since), _instant(req.until)
        try:
            records = self.delegation.tokens(req.agent_id)
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamUnavailable("delegation") from exc
        grants: list[AuthorityGrant] = []
        unreadable = 0
        for t in records if isinstance(records, list) else []:
            try:
                g = AuthorityGrant(
                    token_id=t["token_id"],
                    granted_by=t["granted_by"],
                    scope=t["scope"],
                    issued_at=t["issued_at"],
                    expires_at=t["expires_at"],
                    revoked=t["revoked"],
                    revocation_id=t.get("revocation_id"),
                    revoked_at=t.get("revoked_at"),
                )
                _instant(g.issued_at), _instant(g.expires_at)   # an unparseable timestamp is unreadable too
            except (KeyError, TypeError, ValueError, AttributeError):
                unreadable += 1
                continue
            grants.append(g)
        if unreadable or not isinstance(records, list):
            notes.append(f"{unreadable or 1} delegation token record(s) unreadable, not shown")
        # A grant is relevant if it overlapped the window: issued by `until`
        # and not yet expired at `since` (expired once now >= expires_at, as
        # DelegationToken.status rules).
        authority = [
            g for g in grants
            if _instant(g.issued_at) <= until and _instant(g.expires_at) > since
        ]

        failed_letter = (
            first_failure.clause_id.split(".")[0]
            if first_failure and first_failure.clause_id
            else None
        )
        raci: dict[str, str] = {}
        sources: dict[str, str] = {}

        if record:
            raci["Responsible"] = f"{record.get('owner') or '<owner not recorded>'} (agent owner)"
            sources["Responsible"] = "registry owner"
        elif registry_unreachable:
            raci["Responsible"] = "<registry unreachable>"
            sources["Responsible"] = "none"
        else:
            raci["Responsible"] = "<unregistered agent>"
            sources["Responsible"] = "none"

        grant, source = _accountable(grants, authority, first_failure)
        raci["Accountable"] = (
            f"{grant.granted_by} ({source})" if grant else "<no grantor found>"
        )
        sources["Accountable"] = source

        # The schema allows blank / whitespace-only strings; they name nobody.
        declared = (
            manifest.enforcement.kill_switch.authorized_operators or []
        ) if manifest else []
        operators = [o.strip() for o in declared if o and o.strip()]
        if operators:
            sources["Consulted"] = "manifest kill_switch.authorized_operators"
            raci["Consulted"] = f"{', '.join(operators)} ({sources['Consulted']})"
        else:
            sources["Consulted"] = "default"
            raci["Consulted"] = (
                f"{CLAUSE_EXEC.get(failed_letter or '', DEFAULT_CONSULTED)} (default)"
            )

        principal = manifest.identity.principal.strip() if manifest else ""
        if principal:
            org = (manifest.identity.org or "").strip()
            sources["Informed"] = "manifest identity"
            raci["Informed"] = (
                principal + (f" — {org}" if org else "") + " (manifest identity)"
            )
        else:
            sources["Informed"] = "default"
            raci["Informed"] = f"{DEFAULT_INFORMED} (default)"

        return PostMortem(
            agent_id=req.agent_id,
            window={"since": req.since, "until": req.until},
            generated_at=datetime.now(timezone.utc).isoformat(),
            ledger_integrity_ok=integrity_ok,
            ledger_integrity_detail=integrity_detail,
            ledger_integrity_status=integrity_status,
            agent_record=record,
            authority=authority,
            timeline=timeline,
            first_failure=first_failure,
            counts=counts,
            raci=raci,
            raci_sources=sources,
            accountable_grant=grant,
            manifest_resolved=manifest is not None,
            manifest_detail=manifest_detail,
            integrity_notes=notes,
        )


def render_markdown(pm: PostMortem) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Post-mortem — {_md(pm.agent_id)}")
    add("")
    if pm.ledger_integrity_status == "unverified":
        add("> ## ⚠ LEDGER INTEGRITY NOT VERIFIED (ledger busy)")
        add(f"> {_md(pm.ledger_integrity_detail)}")
        add("> Not a chain break: the ledger could not take a consistent "
            "snapshot. Until a retry verifies the chain, events below are "
            "unverified evidence.")
        add("")
    elif not pm.ledger_integrity_ok:
        add("> ## ⚠ LEDGER INTEGRITY FAILED")
        add(f"> {_md(pm.ledger_integrity_detail)}")
        add("> Events below cannot be treated as trustworthy evidence.")
        add("")
    add(f"*Window:* {_code(pm.window['since'])} → {_code(pm.window['until'])} · "
        f"*Generated:* {pm.generated_at}")
    add(f"*Ledger integrity:* {'OK — ' if pm.ledger_integrity_ok else ''}"
        f"{_md(pm.ledger_integrity_detail)}")
    for note in pm.integrity_notes:
        add("")
        add(f"> **Integrity note:** {_md(note)}")
    add("")

    add("## Agent")
    if pm.agent_record:
        r = pm.agent_record
        add(f"- **{_md(r['agent_id'])}** — {_md(r['name'])}")
        add(f"- Owner: {_md(r.get('owner') or '<owner not recorded>')} · Domain: {_md(r['domain'])} · "
            f"Status: {_md(r['status'])}")
        add(f"- Manifest: {_code(r.get('manifest_ref') or '<none>')}")
    elif pm.raci.get("Responsible") == "<registry unreachable>":
        add("- ⚠ registry unreachable — agent record not shown")
    else:
        add("- ⚠ agent not found in registry")
    add("")

    add("## Who granted authority")
    if pm.authority:
        add("| Token | Granted by | Scope | Issued | Expires | Revoked |")
        add("|---|---|---|---|---|---|")
        for a in pm.authority:
            add(
                f"| {_code(a.token_id[:8] + '…', cell=True)} | {_md(a.granted_by, cell=True)} | "
                f"{_md(', '.join(a.scope), cell=True)} | {_md(a.issued_at[:19], cell=True)} | "
                f"{_md(a.expires_at[:19], cell=True)} | {_md(_revoked_text(a), cell=True)} |"
            )
    else:
        add("- ⚠ no delegation grants overlapped this window")
    add("")

    add("## What ran (timeline)")
    if pm.timeline:
        for t in pm.timeline:
            add(f"- {_code(t.ts[:19])} **{_md(t.event_type)}** — {_md(t.summary)}")
    else:
        add("- no ledger events for this agent in the window")
    add("")

    add("## Which clause failed first")
    if pm.first_failure:
        # A shadow verdict's summary already ends with the log-only label.
        add(
            f"- {_code(pm.first_failure.clause_id)} at {_code(pm.first_failure.ts[:19])} — "
            f"{_md(pm.first_failure.summary)}"
        )
    else:
        add("- no BLOCK or ESCALATE (enforced or log-only shadow) in the window")
    add("")

    add("## Event counts")
    for et, n in sorted(pm.counts.items()):
        add(f"- {_md(et)}: {n}")
    add("")

    add("## RACI")
    if pm.manifest_resolved:
        add("*Manifest:* resolved — Consulted/Informed read from it where it "
            "declares them.")
    else:
        add(f"*Manifest:* not resolved ({_code(pm.manifest_detail)}) — Consulted and "
            f"Informed are labeled defaults.")
    add("")
    add("| Role | Party |")
    add("|---|---|")
    for role, party in pm.raci.items():
        add(f"| {_md(role, cell=True)} | {_md(party, cell=True)} |")
    add("")
    g = pm.accountable_grant
    if g:
        # May be a grant that lapsed before the window (D.expired / D.revoked).
        add(f"*Accountable grant:* {_code(g.token_id[:8] + '…')} by {_md(g.granted_by)} · "
            f"scope {_md(', '.join(g.scope))} · issued {_md(g.issued_at[:19])} · "
            f"expires {_md(g.expires_at[:19])} · revoked {_md(_revoked_text(g))}")
        add("")
    add(f"---\n*Method:* {pm.method}")
    return "\n".join(lines)


_LINE_BREAKS = re.compile(r"[\s\u2028\u2029\x85]+")
MD_FIELD_MAX = 300


def _one_md_line(value: Any) -> str:
    """Every run of whitespace and line breaks (including U+2028, U+2029, NEL, VT, FF) becomes one space; capped at
    MD_FIELD_MAX with an ellipsis."""
    text = _LINE_BREAKS.sub(" ", str(value)).strip()
    if len(text) > MD_FIELD_MAX:
        text = text[: MD_FIELD_MAX - 1] + "…"
    return text


def _md(value: Any, cell: bool = False) -> str:
    """Payload-, grant- and registry-derived text for ONE markdown line of plain text.

    - Line structure: every run of whitespace and line breaks becomes one space, so text such as
      "x\\n## Which clause failed first" can never start a heading or a list item of its own; capped at MD_FIELD_MAX.
    - Inline structure (S-C6, review of the rebuild of PR 521): a backslash is doubled, ``<`` is written ``&lt;`` (no
      raw HTML, no autolink: an HTML-passing renderer would otherwise show a forged ``<h2>`` section), a backtick is
      escaped (it cannot open a code span) and ``](`` is escaped (no inline link or image). Emphasis characters are
      left as they are (they cannot add a block, a link or HTML).
    - ``cell=True`` also escapes table pipes."""
    text = _one_md_line(value)
    text = text.replace("\\", "\\\\").replace("<", "&lt;").replace("`", "\\`").replace("](", "\\](")
    return text.replace("|", "\\|") if cell else text


def _code(value: Any, cell: bool = False) -> str:
    """Payload-, grant- or registry-derived text shown as ONE inline code span: one line and capped like ``_md``, the
    fence one backtick longer than the longest run of backticks in the text (so the text cannot close the span early
    and break out into markup), padded with a space when the text starts or ends with a backtick. Inside a code span
    ``<`` and ``](`` are literal; ``cell=True`` escapes table pipes for a table cell."""
    text = _one_md_line(value)
    if cell:
        text = text.replace("|", "\\|")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _revoked_text(g: AuthorityGrant) -> str:
    if not g.revoked:
        return "no"
    return f"yes ({g.revoked_at[:19]})" if g.revoked_at else "yes"
