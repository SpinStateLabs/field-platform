"""FastAPI surface + CLI helpers for compliance-crosswalk."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from field_core.authn import auth_headers

from typing import Any

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
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

    ``manifest`` is REQUIRED. The shared resolver landed in v1.2 B0
    (``field_core.clients.resolve_manifest``) and the registry record carries
    the ``manifest_ref`` it needs, but this service does not yet make that
    registry-lookup-then-resolve call — so an ``agent_id`` alone still
    resolves to nothing here. Optionality by ``agent_id`` is NOT built. It
    is a plan-assigned D4 deliverable (A3: "optionality lands in D4 after
    the resolver exists"; plan Decisions §2) that D4 shipped without — open,
    and put to the plan owner to build or to move.
    """

    model_config = ConfigDict(extra="forbid")

    signer: str = Field(description="Named human signer — no pack without one")
    manifest: dict[str, Any] = Field(description="FIELD manifest data")
    agent_id: str | None = Field(
        default=None, description="Collect live evidence for this agent"
    )
    sources: EvidenceSources | None = None


log = logging.getLogger("compliance_crosswalk.api")


def create_app(stale_store: Any = None, fetcher: Any = None, every: int = 0) -> FastAPI:
    """Build the app. ``stale_store`` and ``fetcher`` are injection seams:
    ``stale_store=None`` means the process-default ``StaleStore()`` at
    request time (a regwatch check needs the real store's ``transaction``;
    pack/staleness need only ``active()``/``status()``); ``fetcher=None``
    means ``regwatch.default_fetcher`` (live https). ``every`` > 0 arms the
    regwatch scheduler on a daemon thread for the app's lifetime (first
    tick after the interval). It is never read from the environment here —
    ``crosswalk serve --every`` / ``FIELD_CROSSWALK_EVERY`` passes it."""
    every = int(every or 0)
    if every < 0:
        log.warning("crosswalk: negative --every %d treated as 0 (scheduler off)", every)
        every = 0

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if app.state.every > 0:
            from compliance_crosswalk.regwatch import run_every, scheduled_check

            app.state.scheduler_thread = threading.Thread(
                target=run_every,
                args=(lambda: scheduled_check(_store, app.state.fetcher),
                      app.state.every, app.state.scheduler_stop),
                name="crosswalk-regwatch-scheduler",
                daemon=True,
            )
            app.state.scheduler_thread.start()
            log.info("crosswalk regwatch scheduler armed: every %d s (first tick "
                     "after the interval)", app.state.every)
        try:
            yield
        finally:
            app.state.scheduler_stop.set()

    app = FastAPI(
        title="compliance-crosswalk",
        version=__version__,
        description="Manifest fields → control-framework requirements, with "
        "evidence packs. Citations are source-grounded (reference + "
        "source_url + retrieved) or explicitly pending-text / "
        "pending-purchase — 16/40 cited; never invented (see README "
        "'The citation rule'). The cited source pages are watched for "
        "content change (normalised text, not semantics): a change flags "
        "the framework stale; only a named CLI re-review clears it.",
        lifespan=_lifespan,
    )
    install_authn(app)
    app.state.stale_store = stale_store
    app.state.fetcher = fetcher
    app.state.every = every
    app.state.scheduler_stop = threading.Event()
    app.state.scheduler_thread = None

    def _store() -> Any:
        from compliance_crosswalk.staleness import StaleStore

        store = app.state.stale_store
        return store if store is not None else StaleStore()

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "compliance-crosswalk", "version": __version__,
                "every": app.state.every, "build_sha": build_sha()}

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
        active stale flags with their window lengths, review history, and
        ``last_check`` (when the cited sources were last read; null = never)."""
        return _store().status()

    @app.post("/regwatch/check")
    def regwatch_check() -> dict:
        """Read every cited source now and compare with the stored hashes
        (D4). Always 200 with per-framework/per-source statuses — baseline,
        unchanged, changed, unreachable, no-source; ``exit_code`` mirrors
        the CLI (0/3/2). A change SETS a stale flag. Any request body is
        ignored: there is no parameter, here or on any route, that clears
        or unmarks a flag — only ``crosswalk regwatch clear --reviewed-by``."""
        from compliance_crosswalk.regwatch import run_check

        return run_check(_store(), app.state.fetcher, trigger="http")

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
