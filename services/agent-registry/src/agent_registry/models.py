"""Registry record models. Registry-owned; other services consume via HTTP."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AgentStatus(str, Enum):
    ACTIVE = "active"
    KILLED = "killed"
    RETIRED = "retired"


class AgentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1, description="Human owner — never an agent")
    domain: str = Field(
        default="general",
        description="Operating domain, e.g. finance, hr; kill-switch can kill by domain",
    )
    manifest_ref: str | None = Field(
        default=None, description="Path/URL of this agent's FIELD manifest"
    )
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attested_at: datetime | None = Field(
        default=None,
        description="Last human re-attestation (POST /agents/{id}/attest). "
        "Deliberately absent from AgentCreate/AgentUpdate: with extra='forbid' "
        "a PATCH that tries to set it is a 422, so the re-attestation clock "
        "cannot be reset by any ordinary record edit.",
    )
    attested_by: str | None = Field(
        default=None,
        description="Name the attester supplied. A recorded string, NOT an "
        "authenticated identity — see README 'Enforced vs. Declared'.",
    )


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    domain: str = "general"
    manifest_ref: str | None = None


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # min_length matches AgentRecord/AgentCreate: an empty name or owner is a
    # 422 here, at the request boundary. Without it the value reached the
    # store and failed only on read-back (a 500; before the atomic update, a
    # persisted row that made every read of the registry 500).
    # tests/test_registry_update_validation.py. Omitted (None) stays allowed.
    name: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, min_length=1)
    domain: str | None = None
    manifest_ref: str | None = None
    status: AgentStatus | None = None


class ShadowCandidate(BaseModel):
    """An unregistered-agent candidate found by the discovery scanner."""

    model_config = ConfigDict(extra="forbid")

    source: str  # "n8n" | "service-accounts"
    identifier: str
    display_name: str
    reason: str
    evidence: dict[str, str] = Field(default_factory=dict)


class DiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned_workflows: int
    scanned_accounts: int
    registered_agents: int
    candidates: list[ShadowCandidate]
    method: str = (
        "deterministic heuristic v0.1 — AI-node detection in n8n exports + "
        "service-account name patterns; no LLM involved"
    )
