"""FastAPI surface for force-gateway.

Reverse proxy for the Anthropic Messages API shape (`POST /v1/messages`):
1. inject the FORCE preset system block (preset from `x-force-preset`
   header, default `analysis`) WITHOUT dropping the caller's own system
   prompt;
2. forward to the upstream (real Anthropic API, or the built-in
   deterministic mock when FORCE_GATEWAY_MOCK=1 — demos run without keys);
3. record hygiene telemetry (regex heuristics, labeled) + token usage into the
   persistent GatewayStore (v1.2 D2c) — per-route rates over `all` and
   `last_N` windows, per-(route, dimension) drift (D2a/D2b);
4. best-effort: report token spend to spend-governor when
   `x-field-agent-id` is present and a governor is configured.

Platform judge traffic (`x-force-passthrough: judge`, D2e) is forwarded
UNINSTRUMENTED — no injection, no telemetry, no sampling — and counted in
`coverage.passthrough`. It is NOT exempt from metering: a passthrough that
names an agent (`x-field-agent-id`) is still reported to the governor, so the
header cannot switch off an agent's token metering (the platform judges send
no agent id). With FIELD_SHARED_SECRET set the header is honoured only
alongside a valid `x-field-auth`; on a secretless estate it is honoured and
every passthrough is ledgered `gateway.passthrough{client_host, agent_id}`.

The upstream API key comes ONLY from the environment — never from the repo.
"""

from __future__ import annotations

import hmac
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Request

from field_core.authn import install as install_authn, shared_secret
from field_core.buildinfo import build_sha
from pydantic import BaseModel

from force_gateway import __version__
from force_gateway.drift import DIMENSIONS, DriftTracker
from force_gateway.hygiene_judge import resolve_hygiene_judge, resolve_sample_every
from force_gateway.presets import PRESETS, preset_block
from force_gateway.self_manifest import SELF_AGENT_ID
from force_gateway.store import GatewayStore, data_path
from force_gateway.telemetry import METHOD_LABEL, HygieneReport, analyze

Upstream = Callable[[dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]

#: the only `x-force-passthrough` value the gateway honours (field_core.llm)
PASSTHROUGH_JUDGE = "judge"
DEFAULT_TELEMETRY_WINDOW = 50
ALL_ROUTES = "_all"


def mock_upstream(body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """Deterministic canned response in Anthropic Messages shape.

    Exercises the telemetry paths (confidence tags, CoT structure, one
    correction, zero flattery). Clearly a mock: model id says so.
    """
    text = (
        "Correction: the premise is flawed — two of the five inputs are "
        "unsourced.\n\n"
        "ASSUMPTIONS:\n1. The timesheet CSV is authoritative. [HIGH]\n"
        "2. Rates are current. [MEDIUM]\n\n"
        "REASONING:\n1. 12 billable hours × $150 = $1,800. [HIGH]\n"
        "2. Rounding to invoice lines follows the contract's Appendix B. "
        "[LOW] — not in source.\n\n"
        "CONCLUSION:\nDraft invoice total $1,800; Appendix B treatment needs "
        "a human check."
    )
    return 200, {
        "id": "msg_mock_deterministic",
        "type": "message",
        "role": "assistant",
        "model": "force-gateway-mock (no upstream call made)",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 240, "output_tokens": 118},
    }


def real_upstream(body: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    import httpx

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            502,
            "ANTHROPIC_API_KEY not set — set it in the environment, or run "
            "the gateway with FORCE_GATEWAY_MOCK=1",
        )
    # Deliberately NOT field_core.llm.anthropic_base_url(): FORCE_GATEWAY_URL
    # names THIS service, and the gateway's own upstream must never be itself.
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    resp = httpx.post(
        f"{base}/v1/messages",
        json=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": headers.get("anthropic-version", "2023-06-01"),
            "content-type": "application/json",
        },
        timeout=120.0,
    )
    return resp.status_code, resp.json()


def resolve_upstream(upstream: Upstream | None = None) -> Upstream:
    """Injected upstream > `FORCE_GATEWAY_MOCK` exactly "1" > the real API.
    Any other value ("true", "yes", " 1") is the REAL upstream: a mock must
    be asked for precisely, never enabled by a near-miss."""
    if upstream is not None:
        return upstream
    if os.environ.get("FORCE_GATEWAY_MOCK") == "1":
        return mock_upstream
    return real_upstream


def resolve_telemetry_window(default: int = DEFAULT_TELEMETRY_WINDOW) -> int:
    """`FORCE_TELEMETRY_WINDOW`: the count-based `last_N` window (>= 1)."""
    try:
        return max(1, int(os.environ.get("FORCE_TELEMETRY_WINDOW", "")))
    except ValueError:
        return default


def passthrough_honoured(value: str | None, presented_auth: str | None) -> bool:
    """`x-force-passthrough: judge` exempts a call from instrumentation only
    when the estate's perimeter is satisfied: with a shared secret configured
    the caller must present it (checked HERE too, not only by the authn
    middleware, so a route opened to agents later cannot widen the
    exemption); secretless, it is honoured and the caller ledgers it."""
    if value != PASSTHROUGH_JUDGE:
        return False
    secret = shared_secret()
    if secret is None:
        return True
    return presented_auth is not None and hmac.compare_digest(
        presented_auth.encode("utf-8"), secret.encode("utf-8"))


class TelemetryRecord(BaseModel):
    ts: str
    preset: str
    model: str
    agent_id: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: float
    hygiene: HygieneReport
    # Set only on sampled requests the hygiene judge actually scored.
    judgment: dict[str, Any] | None = None


class RouteRates(BaseModel):
    """Share of responses carrying each surface marker. `None` — not 0.0 —
    when the window holds no requests: no data is not a bad score."""
    method: str = METHOD_LABEL
    window_size: int | None  # None for `all`; N for `last_N`
    requests: int
    confidence_tag_rate: float | None
    flattery_free_rate: float | None
    cot_structure_rate: float | None


class TelemetrySummary(BaseModel):
    method: str = METHOD_LABEL
    total_requests: int
    by_preset: dict[str, int]
    responses_with_confidence_tags: int
    responses_clean_of_flattery: int
    responses_with_cot_structure: int
    total_corrections: int
    total_input_tokens: int
    total_output_tokens: int
    # {route | "_all": {"all" | "last_N": RouteRates}}
    rates: dict[str, dict[str, RouteRates]]
    # ADR 10: bypass windows are visible here, never silent.
    coverage: dict[str, Any]
    # {route: {dimension: state}}
    hygiene_trend: dict[str, Any]
    # [{route, dimension}]
    active_alerts: list[dict[str, str]]
    recent: list[TelemetryRecord]


class _StoreFault(RuntimeError):
    """The telemetry store is unavailable (bypass reason `store_fault`)."""


def _rates(requests: int, confidence: int, clean: int, cot: int,
           window_size: int | None) -> RouteRates:
    def rate(n: int) -> float | None:
        return round(n / requests, 4) if requests else None

    return RouteRates(window_size=window_size, requests=requests,
                      confidence_tag_rate=rate(confidence),
                      flattery_free_rate=rate(clean), cot_structure_rate=rate(cot))


def _window_rates(rows: list[dict[str, Any]], window_size: int) -> RouteRates:
    hyg = [r["hygiene"] for r in rows]
    return _rates(len(hyg),
                  sum(1 for h in hyg if h["has_confidence_tags"]),
                  sum(1 for h in hyg if h["clean_of_flattery"]),
                  sum(1 for h in hyg if h["cot_structure"]),
                  window_size)


def inject_force_block(body: dict[str, Any], preset: str) -> dict[str, Any]:
    """Prepend the FORCE block, preserving any caller system prompt."""
    block = preset_block(preset)
    body = dict(body)
    system = body.get("system")
    if system is None:
        body["system"] = block
    elif isinstance(system, str):
        body["system"] = f"{block}\n\n---\n\n{system}"
    elif isinstance(system, list):
        body["system"] = [{"type": "text", "text": block}, *system]
    else:
        raise HTTPException(422, "unsupported system field shape")
    return body


def _bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _count(app: FastAPI, name: str, reason: str | None = None,
           pending: dict[str, int] | None = None) -> None:
    """Bump a coverage counter and its persisted twin. With `pending`, the
    store write joins the request's single commit and the in-memory bump waits
    for it (`_apply_committed`), so memory never runs ahead of what a restart
    would load; without, both happen now, the store write best-effort — these
    are the fault/bypass/passthrough paths, which must never fail traffic."""
    key = f"coverage.{name}" if reason is None else f"coverage.{name}.{reason}"
    if pending is not None:
        pending[key] = pending.get(key, 0) + 1
        return
    cov = app.state.coverage
    if reason is None:
        cov[name] += 1
    else:
        _bump(cov[name], reason)
    store = app.state.store
    if store is None:
        return
    try:
        store.incr(key)
    except Exception as exc:
        app.state.store_error = f"{type(exc).__name__}: {exc}"


def _apply_committed(app: FastAPI, pending: dict[str, int]) -> None:
    """Mirror a committed request's coverage counters into memory — only once
    the store holds them. (`request_count` is not here: its stride slot was
    reserved before the commit and is released if the commit fails.)"""
    cov = app.state.coverage
    for key, value in pending.items():
        parts = key.split(".", 2)
        if parts[0] != "coverage":
            continue
        if len(parts) == 2:
            cov[parts[1]] += value
        else:
            cov[parts[1]][parts[2]] = cov[parts[1]].get(parts[2], 0) + value


def _meter_usage(app: FastAPI, agent_id: str | None, model: str,
                 input_tokens: int, output_tokens: int, note: str) -> None:
    """Best-effort token report for a call that names an agent. Cost-aware
    `/usage` (model + input/output tokens, so the governor prices it and runs
    rogue detection); raw-token `/spend` for older governors (404 on /usage).
    Never raises: metering must not fail traffic (the sentinel gates actions)."""
    gov = app.state.governor
    if gov is None or not agent_id:
        return
    try:
        resp = gov.post("/usage", json={
            "agent_id": agent_id, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "note": note,
        })
        if getattr(resp, "status_code", 201) == 404:
            gov.post("/spend", json={
                "agent_id": agent_id, "tokens": input_tokens + output_tokens,
                "note": note,
            })
    except Exception:
        pass


def _ledger_event(app: FastAPI, event_type: str, payload: dict) -> None:
    """Owner notification is best-effort (the Gateway is an observer — a
    notification failure must never affect traffic)."""
    if app.state.ledger is None:
        return
    try:
        app.state.ledger.append(event_type, payload=payload,
                                agent_id=SELF_AGENT_ID)
    except Exception:
        pass


def _enter_bypass(app: FastAPI, reason: str) -> None:
    """ADR 10 §4: fault or latency over budget drops the Gateway to bypass —
    traffic flows uninstrumented for a cooldown, the gap lands in the
    coverage metric, and the owner is notified. Never silent."""
    _count(app, "bypass_entries")
    _count(app, "bypass_reasons", reason)
    app.state.bypass_remaining = app.state.bypass_cooldown
    _ledger_event(app, "gateway.bypass", {
        "reason": reason, "cooldown_requests": app.state.bypass_cooldown})


def _maybe_judge(app: FastAPI, preset: str, text: str,
                 record: TelemetryRecord, pending: dict[str, int], stride: int):
    """Deterministic 1-in-N sampled hygiene judgment on this request's
    reserved `stride` slot — every skip is counted (fail-open: no path here
    may fail the proxied call). Returns the judgment; the caller persists its
    scores BEFORE feeding the tracker."""
    judge = app.state.hygiene_judge
    if judge is None or app.state.sample_every <= 0:
        return None
    if stride % app.state.sample_every != 0:
        return None
    gov = app.state.governor
    # Spend gate: the judge runs on the Gateway's OWN cap (self-manifest).
    if gov is None:
        _count(app, "judge_bypassed", "no_governor", pending)
        return None
    try:
        resp = gov.get(f"/status/{SELF_AGENT_ID}")
    except Exception:
        _count(app, "judge_bypassed", "governor_unreachable", pending)
        return None
    if resp.status_code == 404:
        _count(app, "judge_bypassed", "no_cap", pending)
        return None
    if resp.status_code != 200:
        _count(app, "judge_bypassed", "governor_error", pending)
        return None
    if resp.json().get("state") == "BLOCK":
        _count(app, "judge_bypassed", "budget", pending)
        return None
    try:
        j = judge.judge(text, preset)
    except Exception:
        _count(app, "judge_bypassed", "error", pending)
        return None
    _count(app, "judged_samples", pending=pending)
    record.judgment = {
        "overall": j.overall, "sycophancy": j.sycophancy,
        "premise_rigor": j.premise_rigor, "model": j.model,
        "rubric_version": j.rubric_version,
    }
    try:
        gov.post("/usage", json={
            "agent_id": SELF_AGENT_ID, "model": j.model,
            "input_tokens": j.input_tokens, "output_tokens": j.output_tokens,
            "note": "gateway hygiene judgment",
        })
    except Exception:
        pass  # metering is best-effort here; the spend GATE is above
    return j


def _feed_drift(app: FastAPI, scores: list[tuple[str, str, float, str, str]]) -> None:
    for route, dimension, score, model, rubric in scores:
        alert = app.state.drift.record(route, dimension, score, model, rubric)
        if alert is not None:
            _ledger_event(app, "gateway.drift_alert", {
                "route": alert.route, "dimension": alert.dimension,
                "baseline_mean": alert.baseline_mean,
                "band": alert.band, "window_means": list(alert.window_means),
                "model": alert.model, "rubric_version": alert.rubric_version,
            })


def _fresh_coverage(sample_every: int) -> dict[str, Any]:
    return {
        "instrumented": 0, "bypassed": 0, "bypass_entries": 0,
        "bypass_reasons": {}, "judged_samples": 0, "judge_bypassed": {},
        "passthrough": 0, "sample_every": sample_every,
    }


def _load_state(app: FastAPI) -> None:
    """Resume the stride, coverage counters and drift state from the store.
    Everything is read before anything is applied: an unreadable store leaves
    a fresh state and a store fault (never a half-replayed tracker)."""
    store = app.state.store
    if store is None:
        return
    try:
        counters = store.counters()
        scores = store.drift_scores()
    except Exception as exc:
        app.state.store = None
        app.state.store_error = f"{type(exc).__name__}: {exc}"
        return
    cov = app.state.coverage
    app.state.request_count = counters.get("request_count", 0)
    for name, value in counters.items():
        if not name.startswith("coverage."):
            continue
        parts = name.split(".", 2)
        if len(parts) == 2 and isinstance(cov.get(parts[1]), int):
            cov[parts[1]] = value
        elif len(parts) == 3 and isinstance(cov.get(parts[1]), dict):
            cov[parts[1]][parts[2]] = value
    # Replay only: a replayed alert was ledgered when it first fired.
    for route, dimension, score, model, rubric in scores:
        app.state.drift.record(route, dimension, score, model, rubric)


def create_app(upstream: Upstream | None = None, governor_client=None,
               ledger_client=None, hygiene_judge=None,
               sample_every: int | None = None, drift: DriftTracker | None = None,
               latency_budget_ms: float | None = None,
               bypass_cooldown: int | None = None,
               store: GatewayStore | None = None,
               telemetry_window: int | None = None) -> FastAPI:
    owns_store = store is None

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        try:
            yield
        finally:
            if owns_store and app.state.store is not None:
                try:
                    app.state.store.close()
                except Exception:
                    pass

    app = FastAPI(
        title="force-gateway",
        version=__version__,
        description="FORCE preset injection + hygiene telemetry for the "
        "Anthropic Messages API shape.",
        lifespan=_lifespan,
    )
    install_authn(app)
    app.state.upstream = resolve_upstream(upstream)
    app.state.governor = governor_client
    app.state.ledger = ledger_client
    app.state.hygiene_judge = (hygiene_judge if hygiene_judge is not None
                               else resolve_hygiene_judge())
    app.state.sample_every = (sample_every if sample_every is not None
                              else resolve_sample_every())
    app.state.drift = drift or DriftTracker(
        window_size=int(os.environ.get("FORCE_HYGIENE_WINDOW", "5")),
        band=float(os.environ.get("FORCE_HYGIENE_BAND", "0.15")),
        baseline_windows=int(os.environ.get("FORCE_HYGIENE_BASELINE_WINDOWS", "2")),
    )
    app.state.latency_budget_ms = (
        latency_budget_ms if latency_budget_ms is not None
        else float(os.environ.get("FORCE_GATEWAY_LATENCY_BUDGET_MS", "250")))
    app.state.bypass_cooldown = (
        bypass_cooldown if bypass_cooldown is not None
        else int(os.environ.get("FORCE_GATEWAY_BYPASS_COOLDOWN", "10")))
    app.state.telemetry_window = (
        max(1, telemetry_window) if telemetry_window is not None
        else resolve_telemetry_window())
    app.state.request_count = 0
    app.state.bypass_remaining = 0
    app.state.coverage = _fresh_coverage(app.state.sample_every)
    app.state.store_error = None
    if store is None:
        try:
            store = GatewayStore(data_path())
        except Exception as exc:
            # A store that cannot open is an instrumentation fault like any
            # other: traffic still flows (every instrumented attempt bypasses).
            store = None
            app.state.store_error = f"{type(exc).__name__}: {exc}"
    app.state.store = store
    _load_state(app)

    @app.get("/health")
    def health() -> dict:
        judge = app.state.hygiene_judge
        return {"ok": True, "service": "force-gateway", "version": __version__,
                "mock": app.state.upstream is mock_upstream,
                "judge": (getattr(judge, "name", "custom")
                          if judge is not None else "off"),
                "sample_every": app.state.sample_every,
                "bypass_remaining": app.state.bypass_remaining,
                "telemetry_store": ("unavailable" if app.state.store is None
                                    else "error" if app.state.store_error
                                    else "ok"),
                "build_sha": build_sha()}

    @app.get("/presets")
    def presets() -> dict[str, str]:
        return PRESETS

    @app.get("/presets/{name}")
    def preset_text(name: str) -> dict[str, str]:
        try:
            return {"preset": name, "system_block": preset_block(name)}
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @app.post("/v1/messages")
    def messages(
        body: dict[str, Any],
        request: Request,
        x_force_preset: str = Header(default="analysis"),
        x_field_agent_id: str | None = Header(default=None),
        anthropic_version: str = Header(default="2023-06-01"),
        x_force_passthrough: str | None = Header(default=None),
        x_field_auth: str | None = Header(default=None),
    ) -> dict[str, Any]:
        # Platform judge traffic (D2e): forwarded untouched — no injection,
        # no telemetry, no sampling (a judged sample's own judge call must
        # not be judged) — and counted. It does not consume a bypass window.
        if passthrough_honoured(x_force_passthrough, x_field_auth):
            _count(app, "passthrough")
            if shared_secret() is None:
                _ledger_event(app, "gateway.passthrough", {
                    "client_host": request.client.host if request.client else None,
                    "agent_id": x_field_agent_id})
            status, response = app.state.upstream(
                body, {"anthropic-version": anthropic_version}
            )
            if status != 200:
                raise HTTPException(status, response)
            # NOT exempt from metering: a passthrough naming an agent is
            # reported like any call, so the header cannot switch off an
            # agent's token metering. The platform judges send no agent id
            # (field_core.llm), so their spend — metered on each caller's own
            # cap — is never counted twice.
            if x_field_agent_id and app.state.governor is not None:
                try:
                    usage = response.get("usage") or {}
                    model = str(response.get("model", "?"))
                    tokens = (int(usage.get("input_tokens", 0)),
                              int(usage.get("output_tokens", 0)))
                except Exception:
                    pass  # an unparseable upstream usage block: nothing to report
                else:
                    _meter_usage(app, x_field_agent_id, model, *tokens,
                                 note="force-gateway LLM call (passthrough)")
            return response

        # Bypass mode (ADR 10 §4): the Gateway's own trouble must never block
        # production traffic — forward the ORIGINAL body uninstrumented (no
        # injection, no telemetry) and count the coverage gap.
        if app.state.bypass_remaining > 0:
            app.state.bypass_remaining -= 1
            _count(app, "bypassed")
            status, response = app.state.upstream(
                body, {"anthropic-version": anthropic_version}
            )
            if status != 200:
                raise HTTPException(status, response)
            return response

        if x_force_preset not in PRESETS:
            raise HTTPException(
                422, f"unknown preset '{x_force_preset}'; use {', '.join(PRESETS)}"
            )
        injected = inject_force_block(body, x_force_preset)
        t0 = time.perf_counter()
        status, response = app.state.upstream(
            injected, {"anthropic-version": anthropic_version}
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        if status != 200:
            raise HTTPException(status, response)

        # Everything below is instrumentation: fail-open. An exception here
        # returns the response anyway and drops the Gateway to bypass.
        i0 = time.perf_counter()
        committed = reserved = False
        try:
            text = "".join(
                part.get("text", "")
                for part in response.get("content", [])
                if isinstance(part, dict) and part.get("type") == "text"
            )
            usage = response.get("usage") or {}
            record = TelemetryRecord(
                ts=datetime.now(timezone.utc).isoformat(),
                preset=x_force_preset,
                model=str(response.get("model", "?")),
                agent_id=x_field_agent_id,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                latency_ms=round(latency_ms, 2),
                hygiene=analyze(text),
            )

            _meter_usage(app, x_field_agent_id, record.model, record.input_tokens,
                         record.output_tokens, note="force-gateway LLM call")

            store = app.state.store
            if store is None:
                raise _StoreFault(app.state.store_error or "telemetry store unavailable")
            # Reserve this request's stride slot up front (concurrent requests
            # get distinct slots); it is released below if nothing commits,
            # so the in-memory stride always equals the persisted one.
            app.state.request_count += 1
            stride, reserved = app.state.request_count, True
            pending: dict[str, int] = {"request_count": 1, "coverage.instrumented": 1}
            judgment = _maybe_judge(app, x_force_preset, text, record, pending, stride)
            scores = ([(x_force_preset, dim, float(getattr(judgment, dim)),
                        judgment.model, judgment.rubric_version)
                       for dim in DIMENSIONS] if judgment is not None else [])
            h = record.hygiene
            store.commit_request(
                x_force_preset, record.model_dump(),
                agg={"requests": 1,
                     "confidence_tags": int(h.has_confidence_tags),
                     "clean_of_flattery": int(h.clean_of_flattery),
                     "cot_structure": int(h.cot_structure),
                     "corrections": h.corrections,
                     "input_tokens": record.input_tokens,
                     "output_tokens": record.output_tokens},
                counters=pending, drift_scores=scores, ts=record.ts,
                keep_at_least=app.state.telemetry_window)
            committed = True
            app.state.store_error = None  # a commit succeeded: the store works
            _apply_committed(app, pending)
            _feed_drift(app, scores)
        except (_StoreFault, sqlite3.Error) as exc:
            if not isinstance(exc, _StoreFault):
                app.state.store_error = f"{type(exc).__name__}: {exc}"
            _enter_bypass(app, "store_fault")
        except Exception:
            _enter_bypass(app, "instrumentation_fault")
        else:
            overhead_ms = (time.perf_counter() - i0) * 1000
            if overhead_ms > app.state.latency_budget_ms:
                _enter_bypass(app, "latency_budget")
        if not committed:
            if reserved:
                app.state.request_count -= 1  # the slot was never persisted
            _count(app, "instrumented")
        return response

    def _coverage_view() -> dict[str, Any]:
        cov = {k: (dict(v) if isinstance(v, dict) else v)
               for k, v in list(app.state.coverage.items())}
        cov["bypass_remaining"] = app.state.bypass_remaining
        return cov

    def _store_unavailable(detail: str) -> HTTPException:
        return HTTPException(503, {"error": "telemetry store unavailable",
                                   "store_error": detail,
                                   "coverage": _coverage_view()})

    @app.get("/telemetry", response_model=TelemetrySummary)
    def telemetry(limit: int = 20) -> TelemetrySummary:
        store = app.state.store
        if store is None:
            raise _store_unavailable(app.state.store_error or "not open")
        n = app.state.telemetry_window
        try:
            counters = store.counters()
            agg: dict[str, dict[str, int]] = {}
            for name, value in counters.items():
                if name.startswith("agg."):
                    route, fld = name[len("agg."):].rsplit(".", 1)
                    agg.setdefault(route, {})[fld] = value
            routes = sorted(r for r, a in agg.items() if a.get("requests", 0) > 0)
            last_n = {route: store.records(limit=n, route=route) for route in routes}
            last_n_all = store.records(limit=n)
            recent = store.records(limit=max(0, limit))
        except sqlite3.Error as exc:
            app.state.store_error = f"{type(exc).__name__}: {exc}"
            raise _store_unavailable(app.state.store_error)

        def total(fld: str, routes_: list[str] = routes) -> int:
            return sum(agg[r].get(fld, 0) for r in routes_)

        rates: dict[str, dict[str, RouteRates]] = {}
        for route in routes:
            a = agg[route]
            rates[route] = {
                "all": _rates(a.get("requests", 0), a.get("confidence_tags", 0),
                              a.get("clean_of_flattery", 0),
                              a.get("cot_structure", 0), None),
                "last_N": _window_rates(last_n[route], n),
            }
        rates[ALL_ROUTES] = {
            "all": _rates(total("requests"), total("confidence_tags"),
                          total("clean_of_flattery"), total("cot_structure"), None),
            "last_N": _window_rates(last_n_all, n),
        }
        drift: DriftTracker = app.state.drift
        return TelemetrySummary(
            total_requests=total("requests"),
            by_preset={r: agg[r]["requests"] for r in routes},
            responses_with_confidence_tags=total("confidence_tags"),
            responses_clean_of_flattery=total("clean_of_flattery"),
            responses_with_cot_structure=total("cot_structure"),
            total_corrections=total("corrections"),
            total_input_tokens=total("input_tokens"),
            total_output_tokens=total("output_tokens"),
            rates=rates,
            coverage=_coverage_view(),
            hygiene_trend=drift.status(),
            active_alerts=drift.active_alerts(),
            recent=[TelemetryRecord(**r) for r in recent],
        )

    return app
