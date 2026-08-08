"""FastAPI surface + CLI helpers for compliance-crosswalk."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from compliance_crosswalk import __version__
from compliance_crosswalk.engine import (
    CoverageReport,
    EvidenceSources,
    evaluate,
    render_markdown,
)
from compliance_crosswalk.mapping import CONTROLS, FRAMEWORKS


class CrosswalkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: dict[str, Any] = Field(description="FIELD manifest data")
    agent_id: str | None = None
    sources: EvidenceSources | None = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="compliance-crosswalk",
        version=__version__,
        description="Manifest fields → control-framework requirements, with "
        "evidence packs. Citations are stubs until official texts are ingested.",
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "compliance-crosswalk", "version": __version__}

    @app.get("/frameworks")
    def frameworks() -> dict[str, str]:
        return FRAMEWORKS

    @app.get("/controls")
    def controls() -> list[dict]:
        return [c.model_dump() for c in CONTROLS]

    @app.post("/crosswalk", response_model=CoverageReport)
    def crosswalk(req: CrosswalkRequest) -> CoverageReport:
        return evaluate(req.manifest, agent_id=req.agent_id, sources=req.sources)

    @app.post("/crosswalk/markdown", response_class=PlainTextResponse)
    def crosswalk_markdown(req: CrosswalkRequest) -> str:
        return render_markdown(
            evaluate(req.manifest, agent_id=req.agent_id, sources=req.sources)
        )

    return app


def collect_evidence(agent_id: str) -> EvidenceSources:
    """Gather live artifacts from the running platform (used by the CLI)."""
    import httpx

    from field_core.clients import AgentNotRegisteredError, RegistryClient

    registry_record = None
    try:
        registry_record = RegistryClient().get_agent(agent_id)
    except Exception:
        pass

    def _get(url: str) -> Any:
        try:
            resp = httpx.get(url, timeout=5.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    import os

    ledger_base = os.environ.get("FIELD_LEDGER_URL", "http://127.0.0.1:8002")
    delegation_base = os.environ.get("FIELD_DELEGATION_URL", "http://127.0.0.1:8003")
    governor_base = os.environ.get("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006")

    events = _get(f"{ledger_base}/events?agent_id={agent_id}") or []
    event_types: dict[str, int] = {}
    for e in events:
        event_types[e["event_type"]] = event_types.get(e["event_type"], 0) + 1

    return EvidenceSources(
        registry_record=registry_record,
        ledger_verify=_get(f"{ledger_base}/verify"),
        ledger_event_types=event_types or None,
        tokens=_get(f"{delegation_base}/tokens?agent_id={agent_id}"),
        governor_cap=_get(f"{governor_base}/caps/{agent_id}"),
    )
