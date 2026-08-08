"""FastAPI surface for spend-governor.

Threshold crossings create an escalation in the human queue and (best-effort)
a ledger event. Cap breaches flip status to BLOCK — the sentinel reads
/status and refuses the action. This service never blocks in-line; it is the
meter, the sentinel is the gate.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from field_core.authn import install as install_authn
from pydantic import BaseModel, ConfigDict, Field

from spend_governor import __version__
from spend_governor.core import (
    Escalation,
    GovernorStore,
    SpendCapConfig,
    SpendEvent,
    SpendState,
    SpendStatus,
    evaluate,
    window_start,
)


class SpendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    cents: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    actions: int = Field(default=0, ge=0)
    note: str | None = None


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(min_length=1, description="Human resolver")


class HealthResponse(BaseModel):
    ok: bool
    service: str = "spend-governor"
    version: str = __version__


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "governor" / "spend.sqlite3"


def create_app(store: GovernorStore | None = None, ledger=None) -> FastAPI:
    """ledger: optional LedgerClient-compatible object (append(...))."""
    app = FastAPI(
        title="spend-governor",
        version=__version__,
        description="Deterministic spend metering vs. manifest caps (FIELD letter E).",
    )
    install_authn(app)
    app.state.store = store or GovernorStore(data_path())
    app.state.ledger = ledger

    def _store() -> GovernorStore:
        return app.state.store

    def _ledger_note(event_type: str, payload: dict, agent_id: str) -> None:
        if app.state.ledger is None:
            return
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            # Metering must not lose spend records because audit is down;
            # the gap is visible: ledger has no matching spend events.
            pass

    def _status(agent_id: str, now: datetime) -> SpendStatus:
        cap = _store().get_cap(agent_id)
        if cap is None:
            raise HTTPException(404, f"no spend cap configured for '{agent_id}'")
        start = window_start(cap.period, now)
        cents, tokens, actions = _store().totals_since(agent_id, start)
        open_escs = _store().open_escalations(agent_id)
        state, detail = evaluate(cap, cents, tokens, actions, len(open_escs))
        return SpendStatus(
            agent_id=agent_id, state=state, period=cap.period, window_start=start,
            currency=cap.currency, spent_cents=cents, limit_cents=cap.limit_cents,
            spent_tokens=tokens, token_limit=cap.token_limit,
            spent_actions=actions, action_limit=cap.action_limit,
            open_escalations=len(open_escs), detail=detail,
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True)

    @app.put("/caps/{agent_id}", response_model=SpendCapConfig)
    def set_cap(agent_id: str, cap: SpendCapConfig) -> SpendCapConfig:
        if cap.agent_id != agent_id:
            raise HTTPException(422, "agent_id in path and body must match")
        return _store().set_cap(cap)

    @app.get("/caps/{agent_id}", response_model=SpendCapConfig)
    def get_cap(agent_id: str) -> SpendCapConfig:
        cap = _store().get_cap(agent_id)
        if cap is None:
            raise HTTPException(404, f"no spend cap configured for '{agent_id}'")
        return cap

    @app.post("/spend", response_model=SpendStatus, status_code=201)
    def record_spend(req: SpendRequest) -> SpendStatus:
        now = datetime.now(timezone.utc)
        cap = _store().get_cap(req.agent_id)
        if cap is None:
            raise HTTPException(
                404,
                f"no spend cap configured for '{req.agent_id}' — refusing to "
                "meter ungoverned spend",
            )
        event: SpendEvent = _store().record(
            req.agent_id, req.cents, req.tokens, req.actions, req.note, now
        )
        _ledger_note(
            "spend.recorded",
            {"event_id": event.event_id, "cents": event.cents,
             "tokens": event.tokens, "actions": event.actions},
            req.agent_id,
        )

        status = _status(req.agent_id, now)
        if status.state is SpendState.ESCALATE:
            kind = status.detail.split(" ", 1)[0]
            if kind in ("cents", "tokens", "actions") and not _store().has_open_escalation(
                req.agent_id, kind
            ):
                spent, limit = {
                    "cents": (status.spent_cents, status.limit_cents),
                    "tokens": (status.spent_tokens, status.token_limit),
                    "actions": (status.spent_actions, status.action_limit),
                }[kind]
                esc = _store().add_escalation(
                    Escalation(
                        escalation_id=str(uuid.uuid4()), agent_id=req.agent_id,
                        ts=now.isoformat(), kind=kind, spent=spent, limit=limit,
                        pct=cap.escalate_at_pct,
                    )
                )
                _ledger_note(
                    "spend.escalate",
                    {"escalation_id": esc.escalation_id, "kind": kind,
                     "spent": spent, "limit": limit},
                    req.agent_id,
                )
        elif status.state is SpendState.BLOCK:
            _ledger_note(
                "spend.cap_reached",
                {"detail": status.detail},
                req.agent_id,
            )
        return status

    @app.get("/status/{agent_id}", response_model=SpendStatus)
    def get_status(agent_id: str) -> SpendStatus:
        return _status(agent_id, datetime.now(timezone.utc))

    @app.get("/escalations", response_model=list[Escalation])
    def list_escalations(agent_id: str | None = None) -> list[Escalation]:
        return _store().open_escalations(agent_id)

    @app.post("/escalations/{escalation_id}/resolve", response_model=Escalation)
    def resolve(escalation_id: str, req: ResolveRequest) -> Escalation:
        try:
            esc = _store().resolve_escalation(escalation_id, req.resolved_by)
        except KeyError:
            raise HTTPException(404, f"escalation '{escalation_id}' not found")
        _ledger_note(
            "spend.escalation_resolved",
            {"escalation_id": escalation_id, "resolved_by": req.resolved_by},
            esc.agent_id,
        )
        return esc

    return app
