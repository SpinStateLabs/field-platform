"""FastAPI surface + CLI helpers for compliance-crosswalk."""

from __future__ import annotations

from field_core.authn import auth_headers

from typing import Any

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn
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


class PackRequest(BaseModel):
    """``POST /pack`` body — a thin adapter over ``crosswalk pack``.

    ``manifest`` is REQUIRED in Phase A: nothing in the platform can resolve
    an ``agent_id`` to a manifest until the shared resolver (B0) exists;
    optionality by ``agent_id`` lands in D4 after that.
    """

    model_config = ConfigDict(extra="forbid")

    signer: str = Field(description="Named human signer — no pack without one")
    manifest: dict[str, Any] = Field(description="FIELD manifest data")
    agent_id: str | None = Field(
        default=None, description="Collect live evidence for this agent"
    )
    sources: EvidenceSources | None = None


def create_app(stale_store: Any = None, fetcher: Any = None) -> FastAPI:
    """Build the app. ``stale_store`` (duck-typed ``active()``/``status()``)
    and ``fetcher`` are injection seams: ``None`` means the process-default
    ``StaleStore()`` at request time. ``fetcher`` is stored for the reg-watch
    fetch path (D4) and unused today."""
    app = FastAPI(
        title="compliance-crosswalk",
        version=__version__,
        description="Manifest fields → control-framework requirements, with "
        "evidence packs. Citations are source-grounded (reference + "
        "source_url + retrieved) or explicitly pending-text / "
        "pending-purchase — 16/40 cited; never invented (see README "
        "'The citation rule').",
    )
    install_authn(app)
    app.state.stale_store = stale_store
    app.state.fetcher = fetcher

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

    @app.get("/staleness")
    def staleness() -> dict:
        """Read-only reg-version staleness status (ADR 07): corpus version,
        active stale flags with their window lengths, review history."""
        from compliance_crosswalk.staleness import StaleStore

        store = app.state.stale_store
        return (store if store is not None else StaleStore()).status()

    @app.post("/pack")
    def pack(req: PackRequest) -> dict:
        """Evidence pack (ADR 07) over HTTP — a thin adapter over
        ``generate_pack`` mirroring the ``crosswalk pack`` CLI exactly; the
        CLI stays the canonical path. 422 on a blank/whitespace signer; 409
        when active stale flags block generation (no override exists)."""
        from compliance_crosswalk.evidence_pack import StalePackError, generate_pack
        from compliance_crosswalk.staleness import StaleStore

        sources = req.sources or (
            collect_evidence(req.agent_id) if req.agent_id else None
        )
        store = app.state.stale_store
        try:
            md, payload = generate_pack(
                req.manifest,
                signer=req.signer,
                stale_store=store if store is not None else StaleStore(),
                agent_id=req.agent_id,
                sources=sources,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except StalePackError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "flags": exc.flags,
                    "affected_controls": exc.affected,
                },
            )
        return {"markdown": md, "pack": payload}

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
            resp = httpx.get(url, timeout=5.0, headers=auth_headers())
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
