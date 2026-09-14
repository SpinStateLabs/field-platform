"""FastAPI surface for spend-governor.

Threshold crossings create an escalation in the human queue and (best-effort)
a ledger event. Cap breaches flip status to BLOCK — the sentinel reads
/status and refuses the action. An exhausted rate window flips status to
THROTTLED with ``retry_after_seconds`` (the sentinel maps it to BLOCK
``E.rate_limit``). This service never blocks in-line (no 429 anywhere); it is
the meter, the sentinel is the gate.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

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
    RateLimitSet,
    RateLimitsView,
    SpendCapConfig,
    SpendEvent,
    SpendState,
    SpendStatus,
    ThrottleInfo,
    action_totals,
    evaluate,
    window_action_rows,
    window_retry_after,
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
    # D1: which action this row is for (feeds that action's rate window) and
    # who counted it. ``sentinel`` is a LABEL any authenticated caller can
    # send, not an authenticated identity (README LIMITS).
    action: str | None = Field(default=None, min_length=1)
    source: Literal["self", "sentinel"] = "self"
    shadowed: bool = False  # sentinel: the ALLOW was a log-only shadow


class TotalsResponse(BaseModel):
    """Spend since an arbitrary instant (D1e: spend under a token since issue)."""

    agent_id: str
    since: str
    currency: str         # the cap's currency: spent_cents are in it
    spent_cents: int      # recorded cents + priced token cost, whole cents
    token_cost_units: int


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


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    store: GovernorStore | None = None,
    ledger=None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """ledger: optional LedgerClient-compatible object (append(...)).
    clock: zero-arg callable returning an aware datetime (tests freeze it)."""
    app = FastAPI(
        title="spend-governor",
        version=__version__,
        description="Deterministic spend metering vs. manifest caps (FIELD letter E).",
    )
    install_authn(app)
    app.state.store = store or GovernorStore(data_path())
    app.state.ledger = ledger
    app.state.price_book = load_price_book()  # dated Anthropic list, or env override
    app.state.clock = clock or _system_clock

    def _store() -> GovernorStore:
        return app.state.store

    def _now() -> datetime:
        now = app.state.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def _ledger_note(event_type: str, payload: dict, agent_id: str) -> None:
        if app.state.ledger is None:
            return
        try:
            app.state.ledger.append(event_type, payload=payload, agent_id=agent_id)
        except Exception:
            # Metering must not lose spend records because audit is down;
            # the gap is visible: ledger has no matching spend events.
            pass

    def _throttle(agent_id: str, now: datetime,
                  action: str | None) -> tuple[ThrottleInfo, int] | None:
        """The exhausted rolling window with the LONGEST wait and that wait
        in whole seconds, or None.

        Per-action limits apply only when ``action`` is given and equals the
        limit's action verbatim (``tool_call`` is not a wildcard). The usage
        policy's token window applies to every status read."""
        exhausted: list[tuple[int, ThrottleInfo]] = []
        if action is not None:
            for limit in _store().get_rate_limits(agent_id):
                if limit.action != action or limit.period_seconds is None:
                    continue  # declared-unenforced (session) never throttles
                after = (now - timedelta(seconds=limit.period_seconds)).isoformat()
                rows = window_action_rows(_store().action_rows_after(agent_id, action, after))
                count, retry = window_retry_after(rows, limit.max, limit.period_seconds, now)
                if retry is not None:
                    exhausted.append((retry, ThrottleInfo(
                        kind="action", action=action, count=count, max=limit.max,
                        period=limit.period, period_seconds=limit.period_seconds)))
        policy = _store().get_policy(agent_id)
        if policy is not None and policy.token_rate_limit is not None:
            window = policy.rate_window_seconds
            after = (now - timedelta(seconds=window)).isoformat()
            rows = _store().token_rows_after(agent_id, after)
            count, retry = window_retry_after(rows, policy.token_rate_limit, window, now)
            if retry is not None:
                exhausted.append((retry, ThrottleInfo(
                    kind="tokens", action=None, count=count,
                    max=policy.token_rate_limit, period=f"{window}s",
                    period_seconds=window)))
        if not exhausted:
            return None
        retry, info = max(exhausted, key=lambda pair: pair[0])
        return info, retry

    def _status_full(
        agent_id: str, now: datetime, action: str | None = None
    ) -> tuple[SpendStatus, SpendState, str]:
        """Status plus the CAP-only verdict (state, detail) under it.

        Precedence: BLOCK (cap) > THROTTLED > ESCALATE > OK. Escalation
        opening keys off the cap verdict, so a throttled spend that crosses
        the threshold still opens its escalation."""
        cap = _store().get_cap(agent_id)
        if cap is None:
            raise HTTPException(404, f"no spend cap configured for '{agent_id}'")
        start = window_start(cap.period, now)
        cents, tokens, _raw_actions = _store().totals_since(agent_id, start)
        # Fold LLM token cost into the SAME cap: priced usage cost (exact
        # integer units) → whole cents added to the dollar spend; usage
        # tokens added to the token count. Token cost thus trips the existing
        # escalate-before-cap / block machinery.
        u_in, u_out, cost_units, _ = _store().usage_totals_since(agent_id, start)
        cents_total = cents + units_to_cents(cost_units)
        tokens_total = tokens + u_in + u_out
        # Option A: an action both checked (sentinel-metered) and
        # self-reported counts once toward action_limit.
        actions_self, actions_metered, actions = action_totals(
            _store().action_counts_since(agent_id, start))
        open_escs = _store().open_escalations(agent_id)
        cap_state, cap_detail = evaluate(
            cap, cents_total, tokens_total, actions, len(open_escs)
        )
        state, detail = cap_state, cap_detail
        retry_after: int | None = None
        throttled: ThrottleInfo | None = None
        if cap_state is not SpendState.BLOCK:
            found = _throttle(agent_id, now, action)
            if found is not None:
                throttled, retry_after = found
                state = SpendState.THROTTLED
                what = (f"action '{throttled.action}'" if throttled.kind == "action"
                        else "token usage")
                detail = (f"rate limit: {what} {throttled.count}/{throttled.max} in "
                          f"{throttled.period} — retry after {retry_after}s")
        status = SpendStatus(
            agent_id=agent_id, state=state, period=cap.period, window_start=start,
            currency=cap.currency, spent_cents=cents_total, limit_cents=cap.limit_cents,
            spent_tokens=tokens_total, token_limit=cap.token_limit,
            spent_actions=actions, action_limit=cap.action_limit,
            open_escalations=len(open_escs), detail=detail,
            token_cost_units=cost_units,
            token_cost_display=units_to_usd_str(cost_units),
            spent_actions_self=actions_self, spent_actions_metered=actions_metered,
            retry_after_seconds=retry_after, throttled=throttled,
        )
        return status, cap_state, cap_detail

    def _status(agent_id: str, now: datetime, action: str | None = None) -> SpendStatus:
        return _status_full(agent_id, now, action)[0]

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

    @app.put("/rate-limits/{agent_id}", response_model=RateLimitsView)
    def set_rate_limits(agent_id: str, body: RateLimitSet) -> RateLimitsView:
        """Replace the agent's rate-limit set (from ``set-cap --from-manifest``).

        Unknown periods 422 (model validation). ``session`` entries are stored
        as declared-unenforced and ledgered, never mapped to a window."""
        if body.agent_id != agent_id:
            raise HTTPException(422, "agent_id in path and body must match")
        if _store().get_cap(agent_id) is None:
            raise HTTPException(
                404,
                f"no spend cap configured for '{agent_id}' — refusing to load rate "
                "limits for an ungoverned agent (set the cap first)",
            )
        _store().set_rate_limits(body)
        rows = _store().get_rate_limits(agent_id)  # the stored order GET returns
        unenforced = [r for r in rows if r.status == "declared_unenforced"]
        if unenforced:
            _ledger_note(
                "spend.rate_limit_declared_unenforced",
                {"entries": [{"action": r.action, "max": r.max, "period": r.period}
                             for r in unenforced],
                 "reason": "period has no server-side meaning; recorded, never "
                           "enforced by the governor (gate-only)"},
                agent_id,
            )
        return RateLimitsView(agent_id=agent_id, rate_limits=rows)

    @app.get("/rate-limits/{agent_id}", response_model=RateLimitsView)
    def get_rate_limits(agent_id: str) -> RateLimitsView:
        if _store().get_cap(agent_id) is None:
            raise HTTPException(404, f"no spend cap configured for '{agent_id}'")
        return RateLimitsView(agent_id=agent_id,
                              rate_limits=_store().get_rate_limits(agent_id))

    @app.post("/spend", response_model=SpendStatus, status_code=201)
    def record_spend(req: SpendRequest) -> SpendStatus:
        now = _now()
        cap = _store().get_cap(req.agent_id)
        if cap is None:
            raise HTTPException(
                404,
                f"no spend cap configured for '{req.agent_id}' — refusing to "
                "meter ungoverned spend",
            )
        if req.source == "sentinel" and req.action is None:
            raise HTTPException(422, "source 'sentinel' rows must name the action")
        if req.shadowed and req.source != "sentinel":
            raise HTTPException(422, "shadowed applies only to source 'sentinel' rows")
        note = req.note
        if req.source == "sentinel" and note is None:
            note = ("sentinel-metered ALLOW (log-only shadow)" if req.shadowed
                    else "sentinel-metered ALLOW")
        event: SpendEvent = _store().record(
            req.agent_id, req.cents, req.tokens, req.actions, note, now,
            action=req.action, source=req.source,
        )
        if req.source == "self":
            # A sentinel-metered row is NOT re-ledgered: the conformance.allow
            # (or shadow) verdict event that caused it is its ledger record,
            # so one check never writes two ledger events for one action.
            payload = {"event_id": event.event_id, "cents": event.cents,
                       "tokens": event.tokens, "actions": event.actions}
            if req.action is not None:
                payload["action"] = req.action
            _ledger_note("spend.recorded", payload, req.agent_id)

        status, cap_state, cap_detail = _status_full(req.agent_id, now, req.action)
        if cap_state is SpendState.ESCALATE:
            kind = cap_detail.split(" ", 1)[0]
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
    def get_status(agent_id: str, action: str | None = None) -> SpendStatus:
        """``?action=`` adds that action's rate windows (exact string)."""
        return _status(agent_id, _now(), action)

    @app.get("/totals/{agent_id}", response_model=TotalsResponse)
    def totals(agent_id: str, since: str) -> TotalsResponse:
        """Recorded cents + priced token cost since ``since`` (ISO 8601,
        inclusive), in the cap's ``currency``. Refuses an uncapped agent like
        ``/status``."""
        cap = _store().get_cap(agent_id)
        if cap is None:
            raise HTTPException(404, f"no spend cap configured for '{agent_id}'")
        try:
            instant = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(422, f"since {since!r} is not an ISO 8601 instant")
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        since_iso = instant.astimezone(timezone.utc).isoformat()
        cents, _tokens, _actions = _store().totals_since(agent_id, since_iso)
        _in, _out, cost_units, _ = _store().usage_totals_since(agent_id, since_iso)
        return TotalsResponse(
            agent_id=agent_id, since=since_iso, currency=cap.currency,
            spent_cents=cents + units_to_cents(cost_units),
            token_cost_units=cost_units,
        )

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
        now = _now()
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
        now = _now()
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
