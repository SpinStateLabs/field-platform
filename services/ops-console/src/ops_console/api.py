"""FastAPI surface for ops-console.

Design rule: the console is a CLIENT, not an authority. Every mutation
proxies through the service that owns it (kill-switch, delegation-authority,
spend-governor), so every action lands on the sealed ledger exactly as if a
CLI operator had done it. The console adds zero new power — it only makes
existing power visible and reachable.

Aggregation follows the attestation-reporter rule: an unreachable service
renders as unavailable, never as a fabricated empty state.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from field_core.authn import auth_headers, install as install_authn
from ops_console import __version__


class ServiceClient:
    """Thin httpx-compatible wrapper with graceful failure."""

    def __init__(self, client=None, base_url: str | None = None,
                 env: str = "", default: str = ""):
        self._client = client
        self.base = (base_url or os.environ.get(env, default)).rstrip("/")
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                base_url=self.base, timeout=10.0, headers=auth_headers()
            )

    def get(self, path: str, **kw) -> tuple[int, Any]:
        try:
            resp = self._client.get(path, **kw)
            return resp.status_code, resp.json()
        except Exception as exc:
            return 0, str(exc)

    def post(self, path: str, **kw) -> tuple[int, Any]:
        try:
            resp = self._client.post(path, **kw)
            return resp.status_code, resp.json()
        except Exception as exc:
            return 0, str(exc)


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    source: str
    data: Any = None
    error: str | None = None


class Overview(BaseModel):
    generated_at: str
    agents: Section
    tokens: Section
    escalations: Section
    ledger_verify: Section
    recent_events: Section


class OperatorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, description="Human operator — recorded")
    reason: str = Field(default="via ops-console", min_length=1)


class ResolveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(min_length=1)


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    token_id: str | None = None
    irreversible: bool = False


def _page() -> str:
    root = resources.files("ops_console") / "static"
    return Path(str(root / "console.html")).read_text(encoding="utf-8")


def create_app(
    registry: ServiceClient | None = None,
    ledger: ServiceClient | None = None,
    delegation: ServiceClient | None = None,
    governor: ServiceClient | None = None,
    killswitch: ServiceClient | None = None,
    sentinel: ServiceClient | None = None,
) -> FastAPI:
    app = FastAPI(
        title="ops-console",
        version=__version__,
        description="Dashboard over every governed agent (client, not authority).",
    )
    # The HTML shell holds no data; /api/* requires the secret when set.
    install_authn(app, open_paths={"/"})

    app.state.registry = registry or ServiceClient(
        env="FIELD_REGISTRY_URL", default="http://127.0.0.1:8001")
    app.state.ledger = ledger or ServiceClient(
        env="FIELD_LEDGER_URL", default="http://127.0.0.1:8002")
    app.state.delegation = delegation or ServiceClient(
        env="FIELD_DELEGATION_URL", default="http://127.0.0.1:8003")
    app.state.governor = governor or ServiceClient(
        env="FIELD_GOVERNOR_URL", default="http://127.0.0.1:8006")
    app.state.killswitch = killswitch or ServiceClient(
        env="FIELD_KILLSWITCH_URL", default="http://127.0.0.1:8005")
    app.state.sentinel = sentinel or ServiceClient(
        env="FIELD_SENTINEL_URL", default="http://127.0.0.1:8004")

    def _section(client: ServiceClient, path: str, label: str,
                 **kw) -> Section:
        status, data = client.get(path, **kw)
        if status == 200:
            return Section(available=True, source=f"GET {client.base}{path}",
                           data=data)
        return Section(available=False, source=f"GET {client.base}{path}",
                       error=f"status {status}: {data}" if status else str(data))

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "ops-console", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return _page()

    @app.get("/api/overview", response_model=Overview)
    def overview() -> Overview:
        return Overview(
            generated_at=datetime.now(timezone.utc).isoformat(),
            agents=_section(app.state.registry, "/agents", "agents"),
            tokens=_section(app.state.delegation, "/tokens", "tokens"),
            escalations=_section(app.state.governor, "/escalations", "escalations"),
            ledger_verify=_section(app.state.ledger, "/verify", "verify"),
            recent_events=_section(
                app.state.ledger, "/events", "events", params={"limit": 25}
            ),
        )

    def _proxy(client: ServiceClient, path: str, body: dict | None,
               ok_codes=(200, 201)) -> Any:
        status, data = client.post(path, json=body)
        if status in ok_codes:
            return data
        raise HTTPException(status or 502, detail=data)

    @app.post("/api/agents/{agent_id}/kill")
    def kill(agent_id: str, action: OperatorAction) -> Any:
        return _proxy(app.state.killswitch, f"/kill/{agent_id}",
                      action.model_dump())

    @app.post("/api/agents/{agent_id}/revive")
    def revive(agent_id: str, action: OperatorAction) -> Any:
        return _proxy(app.state.killswitch, f"/revive/{agent_id}",
                      action.model_dump())

    @app.post("/api/agents/{agent_id}/drill")
    def drill(agent_id: str, action: OperatorAction) -> Any:
        return _proxy(app.state.killswitch, f"/drill/{agent_id}",
                      action.model_dump())

    @app.post("/api/tokens/{token_id}/revoke")
    def revoke(token_id: str) -> Any:
        return _proxy(app.state.delegation, f"/tokens/{token_id}/revoke", None)

    @app.post("/api/escalations/{escalation_id}/resolve")
    def resolve(escalation_id: str, action: ResolveAction) -> Any:
        return _proxy(app.state.governor,
                      f"/escalations/{escalation_id}/resolve",
                      action.model_dump())

    @app.post("/api/check")
    def check(req: CheckRequest) -> Any:
        """Dry-run harness: ask the sentinel what WOULD happen. The verdict
        is real and lands on the ledger like any other check."""
        return _proxy(app.state.sentinel, "/check", req.model_dump())

    return app
