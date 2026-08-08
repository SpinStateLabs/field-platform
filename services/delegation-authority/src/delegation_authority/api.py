"""FastAPI surface for delegation-authority.

Order of operations on mint (ENFORCED, fail-closed):
1. registry confirms the agent exists and is active;
2. the ledger acknowledges the mint event;
3. only then is the token persisted and returned.
Revoke follows the same ledger-first rule.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn
from pydantic import BaseModel, ConfigDict, Field, model_validator

from delegation_authority import __version__
from delegation_authority.clients import (
    AgentNotActiveError,
    AgentNotRegisteredError,
    LedgerClient,
    LedgerUnreachableError,
    RegistryClient,
    RegistryUnreachableError,
)
from delegation_authority.store import TokenNotFoundError, TokenStore
from field_core.delegation import DelegationToken, IntrospectionResult, TokenStatus


class MintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    granted_by: str = Field(min_length=1, description="Human grantor — never an agent")
    scope: list[str] = Field(min_length=1)
    ttl_seconds: int | None = Field(default=None, gt=0)
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _exactly_one_expiry(self) -> "MintRequest":
        if (self.ttl_seconds is None) == (self.expires_at is None):
            raise ValueError("provide exactly one of ttl_seconds or expires_at")
        return self


class IntrospectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_id: str


class HealthResponse(BaseModel):
    ok: bool
    service: str = "delegation-authority"
    version: str = __version__
    token_count: int


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "delegation" / "tokens.sqlite3"


def create_app(
    store: TokenStore | None = None,
    ledger: LedgerClient | None = None,
    registry: RegistryClient | None = None,
) -> FastAPI:
    app = FastAPI(
        title="delegation-authority",
        version=__version__,
        description="Scoped, expiring, revocable delegation tokens (FIELD letter D).",
    )
    install_authn(app)
    app.state.store = store or TokenStore(data_path())
    app.state.ledger = ledger or LedgerClient()
    app.state.registry = registry or RegistryClient()

    def _store() -> TokenStore:
        return app.state.store

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, token_count=len(_store().list()))

    @app.post("/tokens", response_model=DelegationToken, status_code=201)
    def mint(req: MintRequest) -> DelegationToken:
        try:
            app.state.registry.require_active_agent(req.agent_id)
        except AgentNotRegisteredError:
            raise HTTPException(404, f"agent '{req.agent_id}' is not registered")
        except AgentNotActiveError as exc:
            raise HTTPException(409, str(exc))
        except RegistryUnreachableError as exc:
            raise HTTPException(502, f"registry unreachable — refusing to mint: {exc}")

        now = datetime.now(timezone.utc)
        expires = req.expires_at or now + timedelta(seconds=req.ttl_seconds)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            raise HTTPException(422, "expires_at is in the past")

        token = DelegationToken(
            agent_id=req.agent_id,
            granted_by=req.granted_by,
            scope=req.scope,
            issued_at=now,
            expires_at=expires,
        )
        try:
            app.state.ledger.append(
                "delegation.mint",
                payload={
                    "token_id": token.token_id,
                    "granted_by": token.granted_by,
                    "scope": token.scope,
                    "expires_at": token.expires_at.isoformat(),
                },
                agent_id=token.agent_id,
            )
        except LedgerUnreachableError as exc:
            # Fail closed: unauditable authority must not exist.
            raise HTTPException(502, f"ledger unreachable — refusing to mint: {exc}")
        return _store().save(token)

    @app.get("/tokens", response_model=list[DelegationToken])
    def list_tokens(agent_id: str | None = None) -> list[DelegationToken]:
        return _store().list(agent_id=agent_id)

    @app.get("/tokens/{token_id}", response_model=DelegationToken)
    def get_token(token_id: str) -> DelegationToken:
        try:
            return _store().get(token_id)
        except TokenNotFoundError:
            raise HTTPException(404, f"token '{token_id}' not found")

    @app.post("/tokens/{token_id}/revoke", response_model=DelegationToken)
    def revoke(token_id: str) -> DelegationToken:
        try:
            token = _store().get(token_id)
        except TokenNotFoundError:
            raise HTTPException(404, f"token '{token_id}' not found")
        if token.revoked:
            return token  # idempotent
        revoked = token.revoke()
        try:
            app.state.ledger.append(
                "delegation.revoke",
                payload={
                    "token_id": token.token_id,
                    "revocation_id": revoked.revocation_id,
                },
                agent_id=token.agent_id,
            )
        except LedgerUnreachableError as exc:
            raise HTTPException(502, f"ledger unreachable — refusing to revoke: {exc}")
        return _store().save(revoked)

    @app.post("/introspect", response_model=IntrospectionResult)
    def introspect(req: IntrospectRequest) -> IntrospectionResult:
        try:
            token = _store().get(req.token_id)
        except TokenNotFoundError:
            return IntrospectionResult(
                token_id=req.token_id,
                active=False,
                status=TokenStatus.REVOKED,
                reason="unknown token id — treated as revoked (fail closed)",
            )
        status = token.status()
        return IntrospectionResult(
            token_id=token.token_id,
            active=status is TokenStatus.ACTIVE,
            status=status,
            agent_id=token.agent_id,
            scope=token.scope,
            expires_at=token.expires_at,
            reason=None if status is TokenStatus.ACTIVE else f"token is {status.value}",
        )

    return app
