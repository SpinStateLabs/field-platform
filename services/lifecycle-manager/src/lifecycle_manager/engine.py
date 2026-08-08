"""The lifecycle sweep.

Agents rot in three ways the platform can detect deterministically:

1. **Expiring authority** — delegation tokens lapsing within the horizon
   (default 30 days): renew deliberately or let them die deliberately.
2. **Re-attestation due** — registry records untouched for longer than the
   attestation period (default 90 days): someone must confirm the agent
   still does what its manifest says.
3. **Orphans** — agents whose human owner is not on the current roster
   (owners.csv): nobody is accountable. Escalated always; auto-killed only
   when the operator passes the flag — killing is never a silent default.

Every finding is a ledger event; the sweep is idempotent (re-running
re-reports, it does not duplicate kills).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SweepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expiry_horizon_days: int = Field(default=30, ge=1)
    reattestation_days: int = Field(default=90, ge=1)
    auto_kill_orphans: bool = False
    operator: str = Field(
        default="lifecycle-manager (scheduled)",
        description="Recorded on escalations and any auto-kills",
    )


class ExpiringAuthority(BaseModel):
    token_id: str
    agent_id: str
    granted_by: str
    expires_at: str
    days_left: int
    scope: list[str]


class ReattestationDue(BaseModel):
    agent_id: str
    owner: str
    last_updated: str
    days_stale: int


class Orphan(BaseModel):
    agent_id: str
    owner: str
    status: str
    reason: str
    auto_killed: bool = False


class SweepReport(BaseModel):
    swept_at: str
    config: SweepConfig
    agents_scanned: int
    tokens_scanned: int
    roster_size: int
    expiring: list[ExpiringAuthority]
    reattestation_due: list[ReattestationDue]
    orphans: list[Orphan]
    escalations_written: int
    method: str = (
        "deterministic sweep v0.1 over agent-registry + delegation-authority "
        "vs. owners.csv roster; no LLM"
    )


def parse_roster(csv_text: str) -> set[str]:
    """owners.csv: header row with an 'owner' column (extras ignored).
    Matching is case-insensitive on the full owner string."""
    reader = csv.DictReader(io.StringIO(csv_text))
    roster = set()
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        owner = row.get("owner") or row.get("name") or ""
        if owner:
            roster.add(owner.lower())
    return roster


def _parse_ts(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class LifecycleEngine:
    def __init__(self, registry, delegation, ledger=None, killswitch=None):
        """registry: RegistryClient · delegation: http client with GET /tokens
        · ledger: LedgerClient or None · killswitch: http client with
        POST /kill/{agent_id} or None (required only for auto-kill)."""
        self.registry = registry
        self.delegation = delegation
        self.ledger = ledger
        self.killswitch = killswitch

    def _ledger_note(self, event_type: str, payload: dict, agent_id: str | None) -> int:
        if self.ledger is None:
            return 0
        try:
            self.ledger.append(event_type, payload=payload, agent_id=agent_id)
            return 1
        except Exception:
            return 0

    def sweep(
        self,
        roster_csv: str,
        config: SweepConfig | None = None,
        now: datetime | None = None,
    ) -> SweepReport:
        config = config or SweepConfig()
        now = now or datetime.now(timezone.utc)
        roster = parse_roster(roster_csv)

        agents: list[dict[str, Any]] = self.registry.list_agents()
        tokens_resp = self.delegation.get("/tokens")
        tokens: list[dict[str, Any]] = (
            tokens_resp.json() if hasattr(tokens_resp, "json") else tokens_resp
        )

        escalations = 0

        # 1. Expiring authorities.
        expiring: list[ExpiringAuthority] = []
        horizon = now + timedelta(days=config.expiry_horizon_days)
        for t in tokens:
            if t.get("revoked"):
                continue
            expires = _parse_ts(t["expires_at"])
            if now <= expires <= horizon:
                days_left = (expires - now).days
                finding = ExpiringAuthority(
                    token_id=t["token_id"], agent_id=t["agent_id"],
                    granted_by=t["granted_by"], expires_at=t["expires_at"],
                    days_left=days_left, scope=t["scope"],
                )
                expiring.append(finding)
                escalations += self._ledger_note(
                    "lifecycle.expiring_authority",
                    {"token_id": finding.token_id, "days_left": days_left,
                     "granted_by": finding.granted_by, "operator": config.operator},
                    finding.agent_id,
                )

        # 2. Re-attestation due.
        reattest: list[ReattestationDue] = []
        stale_before = now - timedelta(days=config.reattestation_days)
        for a in agents:
            if a.get("status") != "active":
                continue
            updated = _parse_ts(a["updated_at"])
            if updated < stale_before:
                days_stale = (now - updated).days
                finding = ReattestationDue(
                    agent_id=a["agent_id"], owner=a["owner"],
                    last_updated=a["updated_at"], days_stale=days_stale,
                )
                reattest.append(finding)
                escalations += self._ledger_note(
                    "lifecycle.reattestation_due",
                    {"owner": finding.owner, "days_stale": days_stale,
                     "operator": config.operator},
                    finding.agent_id,
                )

        # 3. Orphans — owner not on the roster.
        orphans: list[Orphan] = []
        for a in agents:
            if a.get("status") == "retired":
                continue
            owner = str(a.get("owner", ""))
            if owner.lower() in roster:
                continue
            orphan = Orphan(
                agent_id=a["agent_id"], owner=owner, status=a.get("status", "?"),
                reason=f"owner '{owner}' not found in roster ({len(roster)} entries)",
            )
            escalations += self._ledger_note(
                "lifecycle.orphan",
                {"owner": owner, "operator": config.operator,
                 "auto_kill_requested": config.auto_kill_orphans},
                orphan.agent_id,
            )
            if (
                config.auto_kill_orphans
                and self.killswitch is not None
                and a.get("status") == "active"
            ):
                resp = self.killswitch.post(
                    f"/kill/{orphan.agent_id}",
                    json={"operator": config.operator,
                          "reason": "lifecycle sweep: orphaned agent (auto-kill flag set)"},
                )
                orphan.auto_killed = getattr(resp, "status_code", 0) == 200
            orphans.append(orphan)

        return SweepReport(
            swept_at=now.isoformat(),
            config=config,
            agents_scanned=len(agents),
            tokens_scanned=len(tokens),
            roster_size=len(roster),
            expiring=expiring,
            reattestation_due=reattest,
            orphans=orphans,
            escalations_written=escalations,
        )


def render_markdown(report: SweepReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("# Lifecycle sweep report")
    add("")
    add(f"*Swept:* {report.swept_at} · *Agents:* {report.agents_scanned} · "
        f"*Tokens:* {report.tokens_scanned} · *Roster:* {report.roster_size} humans")
    add(f"*Horizons:* expiry {report.config.expiry_horizon_days} d · "
        f"re-attestation {report.config.reattestation_days} d · "
        f"auto-kill orphans: {'ON' if report.config.auto_kill_orphans else 'off'}")
    add("")
    add(f"## Expiring authorities ({len(report.expiring)})")
    for e in report.expiring:
        add(f"- `{e.token_id[:8]}…` {e.agent_id} — {e.days_left} d left "
            f"(granted by {e.granted_by}; scope {', '.join(e.scope)})")
    if not report.expiring:
        add("- none within horizon")
    add("")
    add(f"## Re-attestation due ({len(report.reattestation_due)})")
    for r in report.reattestation_due:
        add(f"- {r.agent_id} — owner {r.owner}, record untouched {r.days_stale} d")
    if not report.reattestation_due:
        add("- none")
    add("")
    add(f"## Orphans ({len(report.orphans)})")
    for o in report.orphans:
        killed = " → AUTO-KILLED" if o.auto_killed else ""
        add(f"- {o.agent_id} ({o.status}) — {o.reason}{killed}")
    if not report.orphans:
        add("- none")
    add("")
    add(f"*Escalations written to ledger:* {report.escalations_written}")
    add(f"\n---\n*Method:* {report.method}")
    return "\n".join(lines)
