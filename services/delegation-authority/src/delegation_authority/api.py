"""FastAPI surface for delegation-authority.

Order of operations on mint (ENFORCED, fail-closed):
1. registry confirms the agent exists and is active;
2. the DOA roster gate, when ``FIELD_DOA_ROSTER`` is set (see below);
3. the ledger acknowledges the mint event;
4. only then is the token persisted and returned.
Revoke follows the same ledger-first rule.

DOA roster gate (only when ``FIELD_DOA_ROSTER`` is set — unset is today's
behaviour exactly, recorded as ``doa_checked: false``). In this order:

* roster load — missing/unreadable/invalid ⇒ **503, before any ledger write**
  (a roster that cannot be read never degrades into an unchecked mint);
* ``granted_by`` on the roster and ``active`` ⇒ else **403 D.grantor**;
* requested scope ⊆ that grantor's ``allowed_scope`` ⇒ else **403 D.grantor**;
* the agent manifest resolved from the registry record's ``manifest_ref``
  (field-core's one resolver) — no ref / missing / invalid ⇒ **422 D.scope**,
  fail closed;
* requested scope ⊆ ``manifest.delegation.scope`` ⇒ else **422 D.scope**;
* token lifetime ≤ ``max_ttl_days`` (both the ``ttl_seconds`` and the
  ``expires_at`` form) ⇒ else **403 D.grantor**.

``max_spend_usd`` (v1.2 D1e): the matched roster row's value is recorded on
the ledger row (``doa_row``) AND stamped on the token (``DelegationToken.
max_spend_usd``); ``/introspect`` returns it with ``issued_at``. This service
never enforces it — conformance-sentinel does, as ``E.spend_cap`` on the
agent's governor-metered spend since ``issued_at``. A mint with the roster
unset, or under a row without the key, carries no ceiling.
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
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
from delegation_authority.doa import DoaRosterError, load_roster, roster_path
from delegation_authority.store import TokenNotFoundError, TokenStore
from field_core.clients import resolve_manifest_detail
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
    build_sha: str | None = None  # FIELD_BUILD_SHA; "unknown" when unset


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "delegation" / "tokens.sqlite3"


def _epoch(value: datetime) -> int:
    """Seconds since the epoch. A naive stored value is read as UTC — never as
    the server's local zone, which would shift `exp` by the UTC offset."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def _clause(status: int, clause_id: str, message: str) -> HTTPException:
    """Refusal carrying the field-core clause id that fired."""
    return HTTPException(status, {"clause_id": clause_id, "message": message})


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
        return HealthResponse(ok=True, token_count=len(_store().list()),
                              build_sha=build_sha())

    @app.post("/tokens", response_model=DelegationToken, status_code=201)
    def mint(req: MintRequest) -> DelegationToken:
        try:
            record = app.state.registry.require_active_agent(req.agent_id)
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

        doa_checked = False
        doa_row: dict[str, object] | None = None
        ceiling: float | None = None  # D1e: the matched roster row's max_spend_usd
        configured = roster_path()
        if configured:
            # Fail closed: a roster we cannot read is never an unchecked mint.
            try:
                roster = load_roster(configured)
            except DoaRosterError as exc:
                raise HTTPException(
                    503, f"DOA roster unavailable — refusing to mint: {exc}"
                )
            doa_checked = True

            row = roster.find(req.granted_by)
            if row is None:
                raise _clause(
                    403,
                    "D.grantor",
                    f"grantor '{req.granted_by}' is not on the DOA roster",
                )
            if not row.active:
                raise _clause(
                    403,
                    "D.grantor",
                    f"grantor '{req.granted_by}' is on the DOA roster but inactive",
                )
            doa_row = row.ledger_row()
            ceiling = row.max_spend_usd

            beyond = row.may_delegate(req.scope)
            if beyond:
                raise _clause(
                    403,
                    "D.grantor",
                    f"grantor '{row.grantor}' may not delegate {beyond}",
                )

            manifest, reason = resolve_manifest_detail(record.get("manifest_ref"))
            if manifest is None:
                raise _clause(
                    422,
                    "D.scope",
                    f"no valid FIELD manifest for '{req.agent_id}' ({reason}) — "
                    "scope cannot be checked against the manifest, refusing to mint",
                )
            declared = set(manifest.delegation.scope)
            outside = [s for s in req.scope if s not in declared]
            if outside:
                raise _clause(
                    422,
                    "D.scope",
                    f"{outside} outside the agent manifest's delegation.scope",
                )

            # Covers both expiry forms: ttl_seconds and expires_at collapse to
            # the same computed lifetime above.
            if expires - now > timedelta(days=row.max_ttl_days):
                raise _clause(
                    403,
                    "D.grantor",
                    f"token lifetime exceeds grantor '{row.grantor}' "
                    f"max_ttl_days={row.max_ttl_days}",
                )

        token = DelegationToken(
            agent_id=req.agent_id,
            granted_by=req.granted_by,
            scope=req.scope,
            issued_at=now,
            expires_at=expires,
            max_spend_usd=ceiling,
        )
        try:
            app.state.ledger.append(
                "delegation.mint",
                payload={
                    "token_id": token.token_id,
                    "granted_by": token.granted_by,
                    "scope": token.scope,
                    "expires_at": token.expires_at.isoformat(),
                    "doa_checked": doa_checked,
                    "doa_row": doa_row,
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
            issued_at=token.issued_at,
            max_spend_usd=token.max_spend_usd,
        )

    @app.post("/oauth/introspect", response_model=None)
    async def oauth_introspect(request: Request) -> dict[str, object]:
        """RFC 7662-shaped introspection over `application/x-www-form-urlencoded`.

        The body is parsed by hand with ``urllib.parse.parse_qs``: declaring a
        ``Form()`` parameter needs ``python-multipart``, which is not installed,
        and its absence makes ``create_app()`` raise at route registration —
        which would break every suite that builds this app.

        Deliberate response choices, also stated in the README:
        * ``scope`` is the RFC's space-delimited string, and ``scope_list``
          (an RFC-permitted extension member) carries the exact FIELD scope
          strings, because FIELD scopes contain spaces ("read timesheets") and
          the standard field alone cannot be split back apart;
        * ``token_type: "opaque"`` is this spec's choice, not an
          RFC-registered value — these tokens are database records, not
          bearer credentials;
        * revoked, expired and unknown all return exactly ``{"active": false}``
          and nothing else: an introspection response must not leak WHY.
        """
        raw = await request.body()
        fields = urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"))
        token_id = (fields.get("token") or [""])[0].strip()
        if not token_id:
            raise HTTPException(
                400,
                "form field 'token' is required "
                "(application/x-www-form-urlencoded, RFC 7662 §2.1)",
            )
        try:
            # Off the event loop: this handler is async (it reads the raw
            # body), and TokenStore.get waits on the store's threading.Lock.
            # Called inline, that wait stalled every other request to the
            # service (tests/test_oauth_introspect_event_loop.py).
            token = await run_in_threadpool(_store().get, token_id)
        except TokenNotFoundError:
            return {"active": False}
        if token.status() is not TokenStatus.ACTIVE:
            return {"active": False}
        return {
            "active": True,
            "scope": " ".join(token.scope),
            "scope_list": list(token.scope),
            "exp": _epoch(token.expires_at),
            "iat": _epoch(token.issued_at),
            "sub": token.agent_id,
            "client_id": token.agent_id,
            "token_type": "opaque",
        }

    return app
