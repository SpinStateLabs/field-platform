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

from field_core.authn import auth_headers

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from field_core.clients import (
    AgentNotRegisteredError,
    HttpLike,
    ManifestResolver,
    RegistryClient,
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


class LedgerQueryClient:
    def __init__(self, client: HttpLike | None = None, base_url: str | None = None):
        import os

        self._client = client
        self._base = (base_url or os.environ.get(
            "FIELD_LEDGER_URL", "http://127.0.0.1:8002"
        )).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=10.0, headers=auth_headers())

    def events(self, **params: Any) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self._base}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    def verify(self) -> dict[str, Any]:
        resp = self._client.get(f"{self._base}/verify")
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

            self._client = httpx.Client(timeout=10.0, headers=auth_headers())

    def tokens(self, agent_id: str) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self._base}/tokens", params={"agent_id": agent_id})
        resp.raise_for_status()
        return resp.json()


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    since: str = Field(description="ISO 8601 inclusive lower bound")
    until: str = Field(description="ISO 8601 inclusive upper bound")

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


def _summarize(event: dict[str, Any]) -> str:
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
        verification = self.ledger.verify()
        integrity_ok = bool(verification.get("ok"))
        reason = verification.get("reason")
        if integrity_ok:
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

        try:
            record = self.registry.get_agent(req.agent_id)
        except AgentNotRegisteredError:
            record = None

        manifest, manifest_detail = self.manifests.resolve_detail(
            (record or {}).get("manifest_ref")
        )

        events = self.ledger.events(
            agent_id=req.agent_id, since=req.since, until=req.until
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
        grants = [
            AuthorityGrant(
                token_id=t["token_id"],
                granted_by=t["granted_by"],
                scope=t["scope"],
                issued_at=t["issued_at"],
                expires_at=t["expires_at"],
                revoked=t["revoked"],
                revocation_id=t.get("revocation_id"),
                revoked_at=t.get("revoked_at"),
            )
            for t in self.delegation.tokens(req.agent_id)
        ]
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
            raci["Responsible"] = f"{record['owner']} (agent owner)"
            sources["Responsible"] = "registry owner"
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
    add(f"# Post-mortem — {pm.agent_id}")
    add("")
    if pm.ledger_integrity_status == "unverified":
        add("> ## ⚠ LEDGER INTEGRITY NOT VERIFIED (ledger busy)")
        add(f"> {pm.ledger_integrity_detail}")
        add("> Not a chain break: the ledger could not take a consistent "
            "snapshot. Until a retry verifies the chain, events below are "
            "unverified evidence.")
        add("")
    elif not pm.ledger_integrity_ok:
        add("> ## ⚠ LEDGER INTEGRITY FAILED")
        add(f"> {pm.ledger_integrity_detail}")
        add("> Events below cannot be treated as trustworthy evidence.")
        add("")
    add(f"*Window:* `{pm.window['since']}` → `{pm.window['until']}` · "
        f"*Generated:* {pm.generated_at}")
    add(f"*Ledger integrity:* {'OK — ' if pm.ledger_integrity_ok else ''}"
        f"{pm.ledger_integrity_detail}")
    for note in pm.integrity_notes:
        add("")
        add(f"> **Integrity note:** {note}")
    add("")

    add("## Agent")
    if pm.agent_record:
        r = pm.agent_record
        add(f"- **{r['agent_id']}** — {r['name']}")
        add(f"- Owner: {r['owner']} · Domain: {r['domain']} · Status: {r['status']}")
        add(f"- Manifest: `{r.get('manifest_ref') or '<none>'}`")
    else:
        add("- ⚠ agent not found in registry")
    add("")

    add("## Who granted authority")
    if pm.authority:
        add("| Token | Granted by | Scope | Issued | Expires | Revoked |")
        add("|---|---|---|---|---|---|")
        for a in pm.authority:
            add(
                f"| `{a.token_id[:8]}…` | {a.granted_by} | "
                f"{', '.join(a.scope)} | {a.issued_at[:19]} | "
                f"{a.expires_at[:19]} | {_revoked_text(a)} |"
            )
    else:
        add("- ⚠ no delegation grants overlapped this window")
    add("")

    add("## What ran (timeline)")
    if pm.timeline:
        for t in pm.timeline:
            add(f"- `{t.ts[:19]}` **{t.event_type}** — {t.summary}")
    else:
        add("- no ledger events for this agent in the window")
    add("")

    add("## Which clause failed first")
    if pm.first_failure:
        # A shadow verdict's summary already ends with the log-only label.
        add(
            f"- `{pm.first_failure.clause_id}` at `{pm.first_failure.ts[:19]}` — "
            f"{pm.first_failure.summary}"
        )
    else:
        add("- no BLOCK or ESCALATE (enforced or log-only shadow) in the window")
    add("")

    add("## Event counts")
    for et, n in sorted(pm.counts.items()):
        add(f"- {et}: {n}")
    add("")

    add("## RACI")
    if pm.manifest_resolved:
        add("*Manifest:* resolved — Consulted/Informed read from it where it "
            "declares them.")
    else:
        add(f"*Manifest:* not resolved (`{pm.manifest_detail}`) — Consulted and "
            f"Informed are labeled defaults.")
    add("")
    add("| Role | Party |")
    add("|---|---|")
    for role, party in pm.raci.items():
        add(f"| {role} | {party} |")
    add("")
    g = pm.accountable_grant
    if g:
        # May be a grant that lapsed before the window (D.expired / D.revoked).
        add(f"*Accountable grant:* `{g.token_id[:8]}…` by {g.granted_by} · "
            f"scope {', '.join(g.scope)} · issued {g.issued_at[:19]} · "
            f"expires {g.expires_at[:19]} · revoked {_revoked_text(g)}")
        add("")
    add(f"---\n*Method:* {pm.method}")
    return "\n".join(lines)


def _revoked_text(g: AuthorityGrant) -> str:
    if not g.revoked:
        return "no"
    return f"yes ({g.revoked_at[:19]})" if g.revoked_at else "yes"
