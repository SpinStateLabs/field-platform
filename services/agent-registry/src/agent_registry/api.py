"""FastAPI surface for the agent registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request

from field_core import operator_auth, operator_health
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from field_core.clients import resolve_manifest_detail
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_registry import __version__
from agent_registry.discover import discover
from agent_registry.redaction import ScanInputError, redact_text
from agent_registry.models import (
    AgentCreate,
    AgentRecord,
    AgentStatus,
    AgentUpdate,
    DiscoveryReport,
)
from agent_registry.store import (
    AgentNotFoundError,
    DuplicateAgentError,
    RegistryStore,
)


class DiscoverRequest(BaseModel):
    """``extra='forbid'`` (v1.2 D3): a typo'd input field (``api_key_csv``) is
    a 422, never a 200 report that silently scanned nothing."""

    model_config = ConfigDict(extra="forbid")

    n8n_export: dict[str, Any] | list[dict[str, Any]] | None = None
    accounts_csv: str | None = Field(
        default=None, description="Raw CSV text: account,type[,owner][,notes]"
    )
    api_keys_csv: str | None = Field(
        default=None,
        description="Raw CSV text: key_name,owner,service,created,last_used"
        "[,last_used_by] — at most 1 MiB",
    )
    secrets_text: str | None = Field(
        default=None,
        description="Free text scanned for credential-shaped strings (reported "
        "redacted) — at most 1 MiB",
    )
    principals_csv: str | None = Field(
        default=None,
        description="owners.csv (owner[,aliases]) widening the known owners and "
        "principals for api_keys_csv — at most 1 MiB",
    )


class AttestRequest(BaseModel):
    """Body of ``POST /agents/{id}/attest``.

    ``attested_by`` is stripped and must not be blank: an attestation signed
    by nobody is worse than no attestation, because it silently resets the
    lifecycle re-attestation clock. ``extra='forbid'`` also stops a caller
    smuggling ``attested_at`` in to backdate it."""

    model_config = ConfigDict(extra="forbid")

    attested_by: str = Field(min_length=1, description="Human who attested")

    @field_validator("attested_by")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("attested_by must not be blank or whitespace")
        return stripped


class HealthResponse(operator_health.OperatorHealthWithManifests):
    ok: bool
    service: str = "agent-registry"
    version: str = __version__
    agent_count: int
    build_sha: str | None = None  # FIELD_BUILD_SHA; "unknown" when unset


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "registry" / "agents.sqlite3"


def unresolvable_manifest_ref(manifest_ref: str | None) -> dict | None:
    """v1.2 D3b: None when ``manifest_ref`` is unset or resolves; otherwise the
    refusal body. Resolution is field-core's shared resolver — the SAME one
    the sentinel, delegation, kill-switch and ledger retention use — against
    ``FIELD_MANIFEST_DIR`` in THIS process, so a ref refused here is a ref
    every reader on the estate would fail to resolve too."""
    manifest, reason = resolve_manifest_detail(manifest_ref)
    if manifest is not None or reason == "no_ref":
        return None
    return {
        "error": "manifest_ref does not resolve",
        "manifest_ref": manifest_ref,
        "reason": reason,  # missing | invalid (field_core RESOLVE_REASONS)
        "manifest_dir": os.environ.get("FIELD_MANIFEST_DIR", "."),
        "hint": "install the manifest first (a relative ref resolves under "
        "manifest_dir), or register without a manifest_ref",
    }


def validation_errors_without_values(exc: RequestValidationError) -> list[dict]:
    """A request-validation 422's errors as ``type``, ``loc`` and ``msg`` only.

    FastAPI's default handler returns every error's ``input`` — for a typo'd
    ``/discover`` field under ``extra='forbid'`` or a wrong-typed value that is
    the raw secret, and a ``missing`` error quotes the whole body — plus
    ``ctx``, which can carry a validator's exception. Both are dropped. A key
    pasted as a field NAME lands in ``loc``, so string ``loc`` parts and
    ``msg`` pass through the same echo redaction as a discovery candidate
    (v1.2 D3-R1; tests/test_d3_scan_hardening.py)."""
    return [
        {
            "type": err.get("type"),
            "loc": [redact_text(p) if isinstance(p, str) else p
                    for p in err.get("loc", ())],
            "msg": redact_text(str(err.get("msg", ""))),
        }
        for err in exc.errors()
    ]


def create_app(store: RegistryStore | None = None, ledger=None) -> FastAPI:
    """ledger: optional LedgerClient-compatible object. When omitted, one is
    wired from FIELD_LEDGER_URL if set — identity changes are then ledger
    events. Best-effort: the registry must stay usable when audit is down
    (the gap is visible as missing registry.* events)."""
    app = FastAPI(
        title="agent-registry",
        version=__version__,
        description="Agent identity records + shadow-agent discovery (FIELD letter I).",
    )
    install_authn(app)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_without_values(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Every route, not just /discover: same 422 shape, minus the values.
        return JSONResponse(status_code=422,
                            content={"detail": validation_errors_without_values(exc)})

    app.state.store = store or RegistryStore(data_path())
    if ledger is None and os.environ.get("FIELD_LEDGER_URL"):
        from field_core.clients import LedgerClient

        ledger = LedgerClient()
    app.state.ledger = ledger

    def _store() -> RegistryStore:
        return app.state.store

    op_health = operator_health.install(app, ledger_getter=lambda a: a.state.ledger)
    guard_attest = op_health.guard("attest")

    def _ledger_note(event_type: str, payload: dict, agent_id: str) -> None:
        if app.state.ledger is None:
            return
        payload = operator_auth.merge_payload(payload)
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            pass

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        agents = _store().list()
        # C-8: manifests_unresolved counts the agents that can still be killed
        # or revived (not retired) whose manifest_ref does not resolve here.
        return HealthResponse(ok=True, agent_count=len(agents), build_sha=build_sha(),
                              **op_health.health_fields(manifest_refs=lambda: [
                                  a.manifest_ref for a in agents
                                  if a.status != AgentStatus.RETIRED]))

    guard_register = op_health.guard("register")

    @app.post("/agents", response_model=AgentRecord, status_code=201)
    def add_agent(req: AgentCreate, _op: object = Depends(guard_register)) -> AgentRecord:
        # D3b: checked BEFORE the duplicate check and before any write, so an
        # unresolvable ref persists nothing and ledgers nothing — and a
        # re-registration carrying a bad ref is a 422, not a 409 that invites
        # the caller to PATCH the bad ref on (PATCH itself is not checked;
        # README LIMITS).
        refusal = unresolvable_manifest_ref(req.manifest_ref)
        if refusal is not None:
            raise HTTPException(422, refusal)
        try:
            record = _store().add(req)
        except DuplicateAgentError:
            raise HTTPException(409, f"agent '{req.agent_id}' already registered")
        _ledger_note(
            "registry.registered",
            {"name": record.name, "owner": record.owner,
             "domain": record.domain, "manifest_ref": record.manifest_ref},
            record.agent_id,
        )
        return record

    @app.get("/agents", response_model=list[AgentRecord])
    def list_agents(
        status: AgentStatus | None = None, domain: str | None = None
    ) -> list[AgentRecord]:
        return _store().list(status=status, domain=domain)

    @app.get("/agents/{agent_id}", response_model=AgentRecord)
    def get_agent(agent_id: str) -> AgentRecord:
        try:
            return _store().get(agent_id)
        except AgentNotFoundError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")

    @app.patch("/agents/{agent_id}", response_model=AgentRecord)
    def update_agent(agent_id: str, patch: AgentUpdate, request: Request) -> AgentRecord:
        # Phase G. A status change is a kill / revive / decommission by another
        # name, so it needs the same operator check as those routes - scope AND
        # the manifest's authorized_operators. Replacing manifest_ref or owner
        # could defeat that list, so those need the registry_edit scope. name
        # and domain are cosmetic and stay open (declared in the README table).
        needs: list[str] = []
        if patch.status is not None:
            needs.append({AgentStatus.KILLED: "kill",
                          AgentStatus.RETIRED: "decommission"}.get(patch.status, "revive"))
        if (patch.manifest_ref is not None or patch.owner is not None
                or patch.domain is not None):
            # manifest_ref and owner can defeat authorized_operators; domain
            # steers domain halts and fleet-halt. name stays open (cosmetic).
            needs.append("registry_edit")
        if needs and operator_auth.mode() != operator_auth.OFF:
            try:
                auth = operator_auth.authorize_sync(
                    request.headers, needs[0], request.url.path, app.state.ledger)
                for extra in needs[1:]:
                    operator_auth.authenticate(request.headers, extra)
                try:
                    current = _store().get(agent_id)
                except AgentNotFoundError:
                    raise HTTPException(404, f"agent '{agent_id}' not registered")
                # (the assert_operator exemption lives in the shared function)
                operator_auth.check_record_authorized(auth, current.manifest_ref)
                if patch.manifest_ref is not None:
                    # POST checks resolvability (D3b); so must an edit, or one
                    # registry_edit PATCH makes an agent unkillable (503).
                    refusal = unresolvable_manifest_ref(patch.manifest_ref)
                    if refusal is not None:
                        raise HTTPException(422, refusal)
            except operator_auth.OperatorRefused as exc:
                raise op_health.http_refusal(exc, action=",".join(needs),
                                             path=request.url.path,
                                             headers=request.headers,
                                             agent_id=agent_id) from None
            if (patch.status is not None and patch.status != AgentStatus.RETIRED
                    and current.status == AgentStatus.RETIRED):
                # a decommission is terminal (the kill-switch refuses it too):
                # no transition out of retired, for any identity
                raise HTTPException(409, f"agent '{agent_id}' is retired - "
                                    "a decommission cannot be reversed here")
        # ``before`` must be the row THIS write changed, read in the same
        # atomic step: a separate get() first let a concurrent PATCH's kill
        # land in between, so an edit of another field ledgered a second
        # registry.status_changed (tests/test_registry_update_atomicity.py).
        try:
            before, record = _store().update_with_previous(agent_id, patch)
        except AgentNotFoundError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        if record.status != before.status:
            _ledger_note(
                "registry.status_changed",
                {"from": before.status.value, "to": record.status.value},
                agent_id,
            )
        else:
            _ledger_note(
                "registry.updated",
                {"fields": sorted(patch.model_dump(exclude_none=True))},
                agent_id,
            )
        return record

    @app.post("/agents/{agent_id}/attest", response_model=AgentRecord)
    def attest_agent(agent_id: str, req: AttestRequest,
                     _op: object = Depends(guard_attest)) -> AgentRecord:
        """Record a human re-attestation: the ONLY way ``attested_at`` moves.

        A PATCH cannot do this — ``AgentUpdate`` has no such field and forbids
        extras — so the lifecycle re-attestation clock survives kill/revive
        cycles and every other ordinary record edit."""
        req.attested_by = operator_auth.bind_body_operator(req.attested_by)
        try:
            record = _store().attest(agent_id, req.attested_by)
        except AgentNotFoundError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")
        _ledger_note(
            "registry.attested",
            {"attested_by": record.attested_by,
             "attested_at": record.attested_at.isoformat()
             if record.attested_at else None},
            agent_id,
        )
        return record

    @app.post("/discover", response_model=DiscoveryReport)
    def run_discovery(req: DiscoverRequest) -> DiscoveryReport:
        if all(v is None for v in (req.n8n_export, req.accounts_csv,
                                   req.api_keys_csv, req.secrets_text)):
            raise HTTPException(
                422, "provide n8n_export, accounts_csv, api_keys_csv and/or "
                "secrets_text — nothing to scan"
            )
        try:
            return discover(
                registered=_store().list(),
                n8n_export=req.n8n_export,
                accounts_csv=req.accounts_csv,
                api_keys_csv=req.api_keys_csv,
                secrets_text=req.secrets_text,
                principals_csv=req.principals_csv,
            )
        except ScanInputError as exc:  # malformed or > 1 MiB: never an empty report
            raise HTTPException(422, str(exc))

    return app
