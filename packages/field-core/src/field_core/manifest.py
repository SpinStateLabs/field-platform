"""Pydantic models mirroring the FIELD v1 manifest JSON Schema.

Source of truth: ``schema/manifest-schema.json`` (vendored verbatim from the
shipped Force-Field plugin). These models must stay in lockstep with it —
``tests/test_validation_parity.py`` asserts key invariants against the
vendored schema file.

Critical-gap rules encoded structurally:
- ``ledger.cryptographic_seal`` is const ``true`` ("none" seal is impossible).
- ``seal_algorithm`` is a closed enum; "none" is not a member.
- ``federated.isolated: false`` requires at least one allowed peer.
- Kill switch and delegation grantor are required fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "field.spinstatelabs.ca/v1"

SEAL_ALGORITHMS = (
    "sha-256-merkle",
    "blake3-merkle",
    "ed25519-signed-chain",
    "sha-512-merkle",
)

# ISO 8601 date or datetime, mirroring the schema's delegation.expiry pattern.
EXPIRY_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}"
    r"([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$"
)


class _Strict(BaseModel):
    """additionalProperties: false everywhere in the schema."""

    model_config = ConfigDict(extra="forbid")


class Agent(_Strict):
    name: str = Field(min_length=1)
    description: str | None = None
    version: str | None = None


class AllowedPeer(_Strict):
    agent_id: str
    org: str | None = None
    trust_basis: str


class FederationContract(_Strict):
    peer: str
    contract_ref: str | None = None
    scope: str


class Federated(_Strict):
    """F — rules for operating across ownership/trust boundaries."""

    isolated: bool
    allowed_peers: list[AllowedPeer] | None = None
    contracts: list[FederationContract] | None = None

    @model_validator(mode="after")
    def _peers_required_when_not_isolated(self) -> "Federated":
        if self.isolated is False and not self.allowed_peers:
            raise ValueError(
                "federated.isolated is false but allowed_peers is empty; "
                "a non-isolated agent must declare at least one peer"
            )
        return self


class DataScope(_Strict):
    may_access: list[str] | None = None
    may_retain: list[str] | None = None
    may_transmit: list[str] | None = None


class Identity(_Strict):
    """I — attribution and sovereignty."""

    principal: str = Field(min_length=1)
    org: str | None = None
    jurisdiction: list[str] | None = None
    data_scope: DataScope | None = None
    model_provider: str | None = None


class KillSwitch(_Strict):
    endpoint: str = Field(min_length=1)
    method: str = Field(min_length=1)
    authorized_operators: list[str] | None = None


class SpendCap(_Strict):
    currency: str
    limit: float = Field(gt=0)
    period: str
    on_breach: str | None = None


class RateLimit(_Strict):
    action: str
    max: int = Field(ge=1)
    period: str


class Enforcement(_Strict):
    """E — the brakes and rails."""

    kill_switch: KillSwitch
    spend_cap: SpendCap | None = None
    escalation_triggers: list[str] | None = None
    rate_limits: list[RateLimit] | None = None
    irreversible_action_policy: Literal[
        "forbid", "require_human_approval", "allow_with_ledger"
    ]


class Ledger(_Strict):
    """L — the immutable audit trail. Sealing is baseline, not optional."""

    cryptographic_seal: Literal[True]
    seal_algorithm: Literal[
        "sha-256-merkle", "blake3-merkle", "ed25519-signed-chain", "sha-512-merkle"
    ]
    retention_days: int = Field(ge=1)
    logged_events: list[str] = Field(min_length=1)
    store: str | None = None


class Revocation(_Strict):
    method: str | None = None
    endpoint: str | None = None


class Delegation(_Strict):
    """D — the authorization chain from a human principal."""

    granted_by: str = Field(min_length=1)
    scope: list[str] = Field(min_length=1)
    expiry: str = Field(pattern=EXPIRY_PATTERN)
    revocation: Revocation | None = None


class RuntimeProtocol(_Strict):
    name: str
    version: str | None = None
    preset: Literal["analysis", "brainstorm", "draft", "audit"] | None = None


class FieldManifest(_Strict):
    """One manifest per agent. All five FIELD sections required."""

    schema_version: Literal["field.spinstatelabs.ca/v1"]
    agent: Agent
    federated: Federated
    identity: Identity
    enforcement: Enforcement
    ledger: Ledger
    delegation: Delegation
    runtime_protocol: RuntimeProtocol | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldManifest":
        return cls.model_validate(data)
