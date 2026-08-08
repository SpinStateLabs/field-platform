"""Conformance verdict model — the shared shape of every enforcement decision.

Clause ids are stable strings keyed to the FIELD letter whose rule failed.
Services must cite one of these ids on every BLOCK / ESCALATE so incidents
can be replayed against the manifest clause that fired.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


# Stable clause registry. Add ids; never repurpose one.
CLAUSES: dict[str, str] = {
    "F.isolated": "federated: agent is isolated; cross-org exchange not permitted",
    "F.peer": "federated: counterparty is not an allowed peer under contract",
    "I.principal": "identity: no declared principal for this agent",
    "I.manifest": "identity: FIELD manifest missing or invalid for this agent",
    "E.kill_switch": "enforcement: agent is killed or kill switch unreachable",
    "E.spend_cap": "enforcement: spend cap reached",
    "E.spend_threshold": "enforcement: spend threshold crossed; human review required",
    "E.rate_limit": "enforcement: rate limit for this action exhausted",
    "E.irreversible": "enforcement: irreversible action policy forbids or gates this action",
    "E.escalation_trigger": "enforcement: a declared escalation trigger matched",
    "L.seal": "ledger: ledger unsealed or seal invalid",
    "L.unreachable": "ledger: ledger not reachable; actions may not proceed unlogged",
    "D.token": "delegation: no delegation token presented",
    "D.scope": "delegation: action outside delegated scope",
    "D.expired": "delegation: delegation token expired",
    "D.revoked": "delegation: delegation token revoked",
    "R.unregistered": "registry: agent not registered",
}


class ConformanceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    agent_id: str
    action: str
    clause_id: str | None = Field(
        default=None,
        description="Failed clause id (required for BLOCK/ESCALATE); see CLAUSES.",
    )
    reasons: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    context: dict[str, Any] = Field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    def clause_text(self) -> str | None:
        if self.clause_id is None:
            return None
        return CLAUSES.get(self.clause_id, "<unknown clause>")
