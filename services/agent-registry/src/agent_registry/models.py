"""Registry record models. Registry-owned; other services consume via HTTP."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_registry.redaction import fingerprint, redact, redact_text


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

    # hide_input_in_errors: a validation error must not quote an input that
    # may carry a credential.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    source: str  # "n8n" | "service-accounts" | "api-keys"
    identifier: str
    display_name: str
    reason: str
    evidence: dict[str, str] = Field(default_factory=dict)

    # v1.2 D3: a candidate echoes strings from the scanned input (an account
    # name, a key's owner, an n8n node name). Any of them can carry a pasted
    # credential, so every echoed string is redacted HERE, at the model, for
    # every scanner — not left to each scanner to remember.
    @field_validator("identifier", "display_name")
    @classmethod
    def _redact_str(cls, v: str) -> str:
        return redact_text(v)

    @field_validator("evidence")
    @classmethod
    def _redact_evidence(cls, v: dict[str, str]) -> dict[str, str]:
        return {redact_text(k): redact_text(val) for k, val in v.items()}


class SecretHit(BaseModel):
    """A credential-shaped string found by ``scan_secrets_text``.

    Built from the RAW value (``SecretHit(value=raw, ...)``) and keeping only
    its redaction: the validator below replaces ``value`` with ``redacted`` +
    ``fingerprint`` + ``length`` before the model exists (the raw value wins
    over any redaction passed alongside it). A model built WITHOUT ``value``
    (parsing a report back) is held to the redaction's shape: ``redacted``
    shows at most 11 characters around an ellipsis and ``fingerprint`` is 16
    hex — so no instance, however built, can carry a whole secret, and a
    validation error never quotes its input."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    pattern: str
    breadth: str = Field(description="low | moderate | broad | generic | very-broad")
    line: int = Field(ge=1)
    redacted: str
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{16}$")
    length: int = Field(ge=1)

    @model_validator(mode="before")
    @classmethod
    def _redact_raw(cls, data):
        if isinstance(data, dict) and "value" in data:
            data = dict(data)
            raw = str(data.pop("value"))
            data.update(redacted=redact(raw), fingerprint=fingerprint(raw),
                        length=len(raw))
        return data

    @field_validator("redacted")
    @classmethod
    def _is_a_redaction(cls, v: str) -> str:
        if v.count("…") != 1 or len(v) - 1 > 11:
            raise ValueError("redacted must be a redaction (at most 11 characters "
                             "around one ellipsis), never a value")
        return v


class DiscoveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scanned_workflows: int
    scanned_accounts: int
    registered_agents: int
    candidates: list[ShadowCandidate]
    # v1.2 D3 — defaults keep every pre-D3 report (and test) valid.
    scanned_api_keys: int = 0
    scanned_secret_hits: int = 0
    secret_hits: list[SecretHit] = Field(default_factory=list)
    method: str = (
        "deterministic heuristic v0.1 — AI-node detection in n8n exports + "
        "service-account name patterns; v1.2 D3 adds an API-key inventory "
        "owner check and labeled credential-pattern matching (redacted); "
        "no LLM involved"
    )
