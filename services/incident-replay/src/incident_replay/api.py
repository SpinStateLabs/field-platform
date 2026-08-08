"""FastAPI surface for incident-replay."""

from __future__ import annotations

from fastapi import FastAPI

from field_core.authn import install as install_authn
from fastapi.responses import PlainTextResponse

from field_core.clients import RegistryClient
from incident_replay import __version__
from incident_replay.engine import (
    LedgerQueryClient,
    PostMortem,
    ReplayEngine,
    ReplayRequest,
    TokenQueryClient,
    render_markdown,
)


def create_app(engine: ReplayEngine | None = None) -> FastAPI:
    app = FastAPI(
        title="incident-replay",
        version=__version__,
        description="Deterministic incident reconstruction (FIELD letter L).",
    )
    install_authn(app)
    app.state.engine = engine or ReplayEngine(
        ledger=LedgerQueryClient(),
        registry=RegistryClient(),
        delegation=TokenQueryClient(),
    )

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "incident-replay", "version": __version__}

    @app.post("/replay", response_model=PostMortem)
    def replay(req: ReplayRequest) -> PostMortem:
        return app.state.engine.replay(req)

    @app.post("/replay/markdown", response_class=PlainTextResponse)
    def replay_markdown(req: ReplayRequest) -> str:
        return render_markdown(app.state.engine.replay(req))

    return app
