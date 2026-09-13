"""FastAPI surface for the sealed ledger."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from field_core.authn import install as install_authn
from pydantic import BaseModel, Field

from field_core.ledger import ChainVerification, LedgerEvent
from sealed_ledger import __version__
from sealed_ledger.store import ExportSummary, InvalidTimeBound, LedgerStore


class AppendRequest(BaseModel):
    event_type: str = Field(min_length=1)
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    ok: bool
    service: str = "sealed-ledger"
    version: str = __version__
    event_count: int
    head_hash: str


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "ledger" / "events.jsonl"


def create_app(store: LedgerStore | None = None) -> FastAPI:
    app = FastAPI(
        title="sealed-ledger",
        version=__version__,
        description="Append-only, sha-256 hash-chained event ledger (FIELD letter L).",
    )
    install_authn(app)
    app.state.store = store or LedgerStore(data_path())

    def _store() -> LedgerStore:
        return app.state.store

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        s = _store()
        return HealthResponse(
            ok=True,
            event_count=sum(1 for _ in s.iter_events()),
            head_hash=s.head_hash,
        )

    @app.post("/events", response_model=LedgerEvent, status_code=201)
    def append_event(req: AppendRequest) -> LedgerEvent:
        return _store().append(
            event_type=req.event_type, payload=req.payload, agent_id=req.agent_id
        )

    @app.get("/events", response_model=list[LedgerEvent])
    def list_events(
        agent_id: str | None = None,
        event_type: str | None = None,
        since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
        until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
        limit: int | None = Query(None, ge=1, le=10_000),
    ) -> list[LedgerEvent]:
        try:
            return _store().events(
                agent_id=agent_id,
                event_type=event_type,
                since=since,
                until=until,
                limit=limit,
            )
        except InvalidTimeBound as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/verify", response_model=ChainVerification)
    def verify() -> ChainVerification:
        return _store().verify()

    @app.post("/export", response_model=ExportSummary)
    def export(
        out_dir: str | None = Query(
            None,
            description="Server-side directory; the bundle lands in out_dir/<stamp>/ "
            "on the LEDGER HOST (default <ledger dir>/exports).",
        ),
        since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
        until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
        agent_id: str | None = None,
        event_type: str | None = None,
    ) -> ExportSummary:
        """Write an auditor export bundle. The served export is never signed
        (`signed: false`); signing is `ledger export --sign-key` only."""
        s = _store()
        target = Path(out_dir) if out_dir else s.path.parent / "exports"
        try:
            return s.export(
                target,
                since=since,
                until=until,
                agent_id=agent_id,
                event_type=event_type,
            )
        except InvalidTimeBound as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
