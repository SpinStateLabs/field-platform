"""Deterministic replay engine.

Everything in the post-mortem is a query result from the ledger, registry,
and delegation-authority — no inference, no narration, no LLM. If the
ledger chain fails verification, the report carries an INTEGRITY FAILED
banner and says exactly where the chain broke; nothing after a break is
presented as trustworthy.
"""

from __future__ import annotations

from field_core.authn import auth_headers

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from field_core.clients import (
    AgentNotRegisteredError,
    HttpLike,
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


class TimelineEntry(BaseModel):
    ts: str
    event_type: str
    clause_id: str | None = None
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


class PostMortem(BaseModel):
    agent_id: str
    window: dict[str, str]
    generated_at: str
    ledger_integrity_ok: bool
    ledger_integrity_detail: str
    agent_record: dict[str, Any] | None
    authority: list[AuthorityGrant]
    timeline: list[TimelineEntry]
    first_failure: TimelineEntry | None
    counts: dict[str, int]
    raci: dict[str, str]
    method: str = (
        "deterministic query engine v0.1 over sealed-ledger + agent-registry "
        "+ delegation-authority; no LLM, no narration"
    )


def _summarize(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    et = event["event_type"]
    if et.startswith("conformance."):
        return f"{et.split('.')[1].upper()} '{payload.get('action')}'" + (
            f" [{payload.get('clause_id')}]" if payload.get("clause_id") else ""
        )
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


class ReplayEngine:
    def __init__(
        self,
        ledger: LedgerQueryClient,
        registry: RegistryClient,
        delegation: TokenQueryClient,
    ):
        self.ledger = ledger
        self.registry = registry
        self.delegation = delegation

    def replay(self, req: ReplayRequest) -> PostMortem:
        verification = self.ledger.verify()
        integrity_ok = bool(verification.get("ok"))
        integrity_detail = (
            f"chain intact over {verification.get('length')} events"
            if integrity_ok
            else f"CHAIN BROKEN: {verification.get('reason')}"
        )

        try:
            record = self.registry.get_agent(req.agent_id)
        except AgentNotRegisteredError:
            record = None

        events = self.ledger.events(
            agent_id=req.agent_id, since=req.since, until=req.until
        )
        timeline = [
            TimelineEntry(
                ts=e["ts"],
                event_type=e["event_type"],
                clause_id=(e.get("payload") or {}).get("clause_id"),
                summary=_summarize(e),
                hash=e["hash"],
            )
            for e in events
        ]

        first_failure = next(
            (
                t for t in timeline
                if t.event_type in ("conformance.block", "conformance.escalate")
            ),
            None,
        )

        counts: dict[str, int] = {}
        for t in timeline:
            counts[t.event_type] = counts.get(t.event_type, 0) + 1

        tokens = self.delegation.tokens(req.agent_id)
        authority = [
            AuthorityGrant(
                token_id=t["token_id"],
                granted_by=t["granted_by"],
                scope=t["scope"],
                issued_at=t["issued_at"],
                expires_at=t["expires_at"],
                revoked=t["revoked"],
                revocation_id=t.get("revocation_id"),
            )
            for t in tokens
            # a grant is relevant if it overlapped the window
            if t["issued_at"] <= req.until and t["expires_at"] >= req.since
        ]

        failed_letter = (
            first_failure.clause_id.split(".")[0]
            if first_failure and first_failure.clause_id
            else None
        )
        raci = {
            "Responsible": (
                f"{record['owner']} (agent owner)" if record else "<unregistered agent>"
            ),
            "Accountable": (
                authority[0].granted_by + " (grantor)" if authority else "<no grantor found>"
            ),
            "Consulted": CLAUSE_EXEC.get(failed_letter or "", "CISO (default)"),
            "Informed": "CEO / board (attestation-reporter)",
        }

        return PostMortem(
            agent_id=req.agent_id,
            window={"since": req.since, "until": req.until},
            generated_at=datetime.now(timezone.utc).isoformat(),
            ledger_integrity_ok=integrity_ok,
            ledger_integrity_detail=integrity_detail,
            agent_record=record,
            authority=authority,
            timeline=timeline,
            first_failure=first_failure,
            counts=counts,
            raci=raci,
        )


def render_markdown(pm: PostMortem) -> str:
    lines: list[str] = []
    add = lines.append
    add(f"# Post-mortem — {pm.agent_id}")
    add("")
    if not pm.ledger_integrity_ok:
        add("> ## ⚠ LEDGER INTEGRITY FAILED")
        add(f"> {pm.ledger_integrity_detail}")
        add("> Events below cannot be treated as trustworthy evidence.")
        add("")
    add(f"*Window:* `{pm.window['since']}` → `{pm.window['until']}` · "
        f"*Generated:* {pm.generated_at}")
    add(f"*Ledger integrity:* {'OK — ' if pm.ledger_integrity_ok else ''}"
        f"{pm.ledger_integrity_detail}")
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
                f"{a.expires_at[:19]} | {'yes' if a.revoked else 'no'} |"
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
        add(
            f"- `{pm.first_failure.clause_id}` at `{pm.first_failure.ts[:19]}` — "
            f"{pm.first_failure.summary}"
        )
    else:
        add("- no BLOCK or ESCALATE in the window")
    add("")

    add("## Event counts")
    for et, n in sorted(pm.counts.items()):
        add(f"- {et}: {n}")
    add("")

    add("## RACI")
    add("| Role | Party |")
    add("|---|---|")
    for role, party in pm.raci.items():
        add(f"| {role} | {party} |")
    add("")
    add(f"---\n*Method:* {pm.method}")
    return "\n".join(lines)
