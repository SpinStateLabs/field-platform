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


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    domain: str = "general"
    manifest_ref: str | None = None


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    owner: str | None = None
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
