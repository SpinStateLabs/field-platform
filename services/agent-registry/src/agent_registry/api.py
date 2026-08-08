"""FastAPI surface for the agent registry."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
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


def create_app(store: RegistryStore | None = None) -> FastAPI:
    app = FastAPI(
        title="agent-registry",
        version=__version__,
        description="Agent identity records + shadow-agent discovery (FIELD letter I).",
    )
    app.state.store = store or RegistryStore(data_path())

    def _store() -> RegistryStore:
        return app.state.store

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, agent_count=len(_store().list()))

    @app.post("/agents", response_model=AgentRecord, status_code=201)
    def add_agent(req: AgentCreate) -> AgentRecord:
        try:
            return _store().add(req)
        except DuplicateAgentError:
            raise HTTPException(409, f"agent '{req.agent_id}' already registered")

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
            return _store().update(agent_id, patch)
        except AgentNotFoundError:
            raise HTTPException(404, f"agent '{agent_id}' not registered")

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
