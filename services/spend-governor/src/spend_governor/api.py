"""FastAPI surface for spend-governor.

Threshold crossings create an escalation in the human queue and (best-effort)
a ledger event. Cap breaches flip status to BLOCK — the sentinel reads
/status and refuses the action. This service never blocks in-line; it is the
meter, the sentinel is the gate.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from field_core.authn import install as install_authn
from field_core.buildinfo import build_sha
from field_core.pricing import (
    load_price_book,
    normalize_model,
    units_to_cents,
    units_to_usd_str,
)
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
from spend_governor.usage import (
    ModelBreakdown,
    UsagePolicy,
    UsageRecord,
    UsageStatus,
    evaluate_rogue,
)


class SpendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    cents: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    actions: int = Field(default=0, ge=0)
    note: str | None = None


class UsageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1)
    model: str = Field(min_length=1, description="Model the agent used")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    note: str | None = None


class UsageResponse(BaseModel):
    record: UsageRecord
    rogue: list = Field(default_factory=list)
    status: SpendStatus


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(min_length=1, description="Human resolver")


class HealthResponse(BaseModel):
    ok: bool
    service: str = "spend-governor"
    version: str = __version__
    build_sha: str | None = None  # FIELD_BUILD_SHA; "unknown" when unset


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
    app.state.price_book = load_price_book()  # dated Anthropic list, or env override

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
        # Fold LLM token cost into the SAME cap: priced usage cost (exact
        # integer units) → whole cents added to the dollar spend; usage
        # tokens added to the token count. Token cost thus trips the existing
        # escalate-before-cap / block machinery.
        u_in, u_out, cost_units, _ = _store().usage_totals_since(agent_id, start)
        cents_total = cents + units_to_cents(cost_units)
        tokens_total = tokens + u_in + u_out
        open_escs = _store().open_escalations(agent_id)
        state, detail = evaluate(
            cap, cents_total, tokens_total, actions, len(open_escs)
        )
        return SpendStatus(
            agent_id=agent_id, state=state, period=cap.period, window_start=start,
            currency=cap.currency, spent_cents=cents_total, limit_cents=cap.limit_cents,
            spent_tokens=tokens_total, token_limit=cap.token_limit,
            spent_actions=actions, action_limit=cap.action_limit,
            open_escalations=len(open_escs), detail=detail,
            token_cost_units=cost_units,
            token_cost_display=units_to_usd_str(cost_units),
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, build_sha=build_sha())

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
            if kind in ("cents", "tokens", "actions"):
                spent, limit = {
                    "cents": (status.spent_cents, status.limit_cents),
                    "tokens": (status.spent_tokens, status.token_limit),
                    "actions": (status.spent_actions, status.action_limit),
                }[kind]
                # check-and-insert in one store call: concurrent crossings
                # open (and ledger) exactly one escalation per kind
                esc, opened = _store().add_escalation_if_none_open(
                    Escalation(
                        escalation_id=str(uuid.uuid4()), agent_id=req.agent_id,
                        ts=now.isoformat(), kind=kind, spent=spent, limit=limit,
                        pct=cap.escalate_at_pct,
                    )
                )
                if opened:
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

    @app.post(
        "/escalations/{escalation_id}/resolve",
        response_model=Escalation,
        responses={409: {
            "model": Escalation,
            "description": "Already resolved by another human; body is the "
            "stored row, first resolver unchanged",
        }},
    )
    def resolve(escalation_id: str, req: ResolveRequest):
        """First resolver wins. 200 with the row when this call resolved it
        (one ``spend.escalation_resolved`` note) or when the SAME human
        retries (idempotent, no second note); 409 with the unchanged row when
        a different human already resolved it."""
        try:
            esc, resolved_now = _store().resolve_escalation_once(
                escalation_id, req.resolved_by
            )
        except KeyError:
            raise HTTPException(404, f"escalation '{escalation_id}' not found")
        if resolved_now:
            _ledger_note(
                "spend.escalation_resolved",
                {"escalation_id": escalation_id, "resolved_by": req.resolved_by},
                esc.agent_id,
            )
        elif esc.resolved_by != req.resolved_by:
            return JSONResponse(status_code=409, content=esc.model_dump(mode="json"))
        return esc

    # ---- token-usage governance ----

    @app.put("/policies/{agent_id}", response_model=UsagePolicy)
    def set_policy(agent_id: str, policy: UsagePolicy) -> UsagePolicy:
        if policy.agent_id != agent_id:
            raise HTTPException(422, "agent_id in path and body must match")
        policy.allowed_models = [normalize_model(m) for m in policy.allowed_models]
        return _store().set_policy(policy)

    @app.get("/policies/{agent_id}", response_model=UsagePolicy)
    def get_policy(agent_id: str) -> UsagePolicy:
        policy = _store().get_policy(agent_id)
        if policy is None:
            raise HTTPException(404, f"no usage policy for '{agent_id}'")
        return policy

    @app.post("/usage", response_model=UsageResponse, status_code=201)
    def record_usage(req: UsageRequest) -> UsageResponse:
        now = datetime.now(timezone.utc)
        # Token usage is a governed cost: it must land against a cap, exactly
        # like /spend refuses ungoverned dollar spend.
        cap = _store().get_cap(req.agent_id)
        if cap is None:
            raise HTTPException(
                404,
                f"no spend cap configured for '{req.agent_id}' — refusing to "
                "meter ungoverned token usage",
            )
        canonical = normalize_model(req.model)
        book = app.state.price_book
        cost_units = book.cost_units(
            canonical, req.input_tokens, req.output_tokens, req.cache_read_tokens
        )
        priced = cost_units is not None

        record = _store().record_usage(UsageRecord(
            event_id=str(uuid.uuid4()), agent_id=req.agent_id, ts=now.isoformat(),
            model=canonical, input_tokens=req.input_tokens,
            output_tokens=req.output_tokens, cache_read_tokens=req.cache_read_tokens,
            cost_units=cost_units, priced=priced, note=req.note,
        ))
        _ledger_note(
            "usage.recorded",
            {"event_id": record.event_id, "model": canonical,
             "input_tokens": req.input_tokens, "output_tokens": req.output_tokens,
             "cost_units": cost_units, "price_book": book.book_id},
            req.agent_id,
        )

        # Rogue detection — deterministic, each finding is ledger + escalation.
        policy = _store().get_policy(req.agent_id)
        window_start_iso = (
            now - timedelta(seconds=policy.rate_window_seconds)
        ).isoformat() if policy else now.isoformat()
        window_after = _store().window_tokens(req.agent_id, window_start_iso)
        findings = evaluate_rogue(policy, canonical, priced, window_after)
        for f in findings:
            kind = f"usage:{f.kind.value}"
            esc, opened = _store().add_escalation_if_none_open(Escalation(
                escalation_id=str(uuid.uuid4()), agent_id=req.agent_id,
                ts=now.isoformat(), kind=kind,
                spent=window_after, limit=policy.token_rate_limit or 0
                if policy else 0, pct=cap.escalate_at_pct,
            ))
            if opened:
                _ledger_note(
                    f"usage.{f.kind.value}",
                    {"model": canonical, "detail": f.detail,
                     "escalation_id": esc.escalation_id},
                    req.agent_id,
                )

        status = _status(req.agent_id, now)
        if status.state is SpendState.BLOCK:
            _ledger_note("spend.cap_reached", {"detail": status.detail}, req.agent_id)
        return UsageResponse(
            record=record,
            rogue=[f.model_dump() for f in findings],
            status=status,
        )

    @app.get("/usage/{agent_id}", response_model=UsageStatus)
    def usage_status(agent_id: str) -> UsageStatus:
        now = datetime.now(timezone.utc)
        cap = _store().get_cap(agent_id)
        period = cap.period if cap else "total"
        start = window_start(period, now)
        u_in, u_out, cost_units, rows = _store().usage_totals_since(agent_id, start)
        policy = _store().get_policy(agent_id)
        allowed = policy.allowed_models if policy else []
        by_model = [
            ModelBreakdown(
                model=r["model"], input_tokens=r["i"], output_tokens=r["o"],
                cost_units=r["c"] if r["p"] else None, priced=bool(r["p"]),
                allowed=(not allowed) or (r["model"] in allowed),
            )
            for r in rows
        ]
        rogue_open = sum(
            1 for e in _store().open_escalations(agent_id)
            if e.kind.startswith("usage:")
        )
        return UsageStatus(
            agent_id=agent_id, window_seconds=0,
            total_input_tokens=u_in, total_output_tokens=u_out,
            total_cost_units=cost_units,
            total_cost_display=units_to_usd_str(cost_units),
            token_rate_limit=policy.token_rate_limit if policy else None,
            allowed_models=allowed, by_model=by_model,
            open_rogue_flags=rogue_open,
        )

    return app
