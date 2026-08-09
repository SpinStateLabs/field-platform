"""FastAPI surface for the agent registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn
from pydantic import BaseModel, Field

from agent_registry import __version__
from agent_registry.discover import discover
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
    n8n_export: dict[str, Any] | list[dict[str, Any]] | None = None
    accounts_csv: str | None = Field(
        default=None, description="Raw CSV text: account,type[,owner][,notes]"
    )


class HealthResponse(BaseModel):
    ok: bool
    service: str = "agent-registry"
    version: str = __version__
    agent_count: int


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "registry" / "agents.sqlite3"


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
    app.state.store = store or RegistryStore(data_path())
    if ledger is None and os.environ.get("FIELD_LEDGER_URL"):
        from field_core.clients import LedgerClient

        ledger = LedgerClient()
    app.state.ledger = ledger

    def _store() -> RegistryStore:
        return app.state.store

    def _ledger_note(event_type: str, payload: dict, agent_id: str) -> None:
        if app.state.ledger is None:
            return
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            pass

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, agent_count=len(_store().list()))

    @app.post("/agents", response_model=AgentRecord, status_code=201)
    def add_agent(req: AgentCreate) -> AgentRecord:
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
    def update_agent(agent_id: str, patch: AgentUpdate) -> AgentRecord:
        try:
            before = _store().get(agent_id)
            record = _store().update(agent_id, patch)
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

    @app.post("/discover", response_model=DiscoveryReport)
    def run_discovery(req: DiscoverRequest) -> DiscoveryReport:
        if req.n8n_export is None and req.accounts_csv is None:
            raise HTTPException(
                422, "provide n8n_export and/or accounts_csv — nothing to scan"
            )
        return discover(
            registered=_store().list(),
            n8n_export=req.n8n_export,
            accounts_csv=req.accounts_csv,
        )

    return app
