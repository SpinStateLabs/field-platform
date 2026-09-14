"""Delegation token model — scoped, expiring, revocable authority.

The model and status logic live here (single source of truth); the
delegation-authority service adds storage, HTTP endpoints, and ledger
writes around them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_serializer


class TokenStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class DelegationToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = Field(min_length=1)
    granted_by: str = Field(min_length=1, description="Human grantor — never an agent")
    scope: list[str] = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False
    revocation_id: str | None = None
    revoked_at: datetime | None = None
    #: v1.2 D1e: the DOA roster row's ceiling, stamped at mint (None = no
    #: ceiling). conformance-sentinel enforces it as ``E.spend_cap`` on the
    #: agent's governor-metered spend since ``issued_at``.
    max_spend_usd: float | None = Field(default=None, ge=0)

    @model_serializer(mode="wrap")
    def _omit_absent_ceiling(self, handler):
        # A token with no ceiling serialises exactly as before D1e, so an older
        # client parsing it with extra='forbid' (field-agent bootstrap) still
        # accepts it. A stamped ceiling (0 included) is always present.
        data = handler(self)
        if self.max_spend_usd is None and isinstance(data, dict):
            data.pop("max_spend_usd", None)
        return data

    def status(self, now: datetime | None = None) -> TokenStatus:
        # Revocation wins over expiry: a revoked token stays revoked.
        if self.revoked:
            return TokenStatus.REVOKED
        now = now or datetime.now(timezone.utc)
        if now >= self.expires_at:
            return TokenStatus.EXPIRED
        return TokenStatus.ACTIVE

    def is_active(self, now: datetime | None = None) -> bool:
        return self.status(now) is TokenStatus.ACTIVE

    def revoke(self, now: datetime | None = None) -> "DelegationToken":
        """Return a revoked copy carrying a fresh revocation id."""
        return self.model_copy(
            update={
                "revoked": True,
                "revocation_id": str(uuid.uuid4()),
                "revoked_at": now or datetime.now(timezone.utc),
            }
        )

    def covers(self, action: str) -> bool:
        """True if ``action`` is inside this token's scope (exact match)."""
        return action in self.scope


class IntrospectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_id: str
    active: bool
    status: TokenStatus
    agent_id: str | None = None
    scope: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    reason: str | None = None
    #: v1.2 D1e: what conformance-sentinel needs to bound spend under the
    #: token (None for an unknown token, and for a token with no ceiling).
    issued_at: datetime | None = None
    max_spend_usd: float | None = None
