"""FastAPI surface for force-gateway.

Reverse proxy for the Anthropic Messages API shape (`POST /v1/messages`):
1. inject the FORCE preset system block (preset from `x-force-preset`
   header, default `analysis`) WITHOUT dropping the caller's own system
   prompt;
2. forward to the upstream (real Anthropic API, or the built-in
   deterministic mock when FORCE_GATEWAY_MOCK=1 — demos run without keys);
3. record hygiene telemetry (regex heuristics, labeled) + token usage;
4. best-effort: report token spend to spend-governor when
   `x-field-agent-id` is present and a governor is configured.

The upstream API key comes ONLY from the environment — never from the repo.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException

from field_core.authn import install as install_authn
from pydantic import BaseModel

from force_gateway import __version__
from force_gateway.drift import DriftTracker
from force_gateway.hygiene_judge import resolve_hygiene_judge, resolve_sample_every
from force_gateway.presets import PRESETS, preset_block
from force_gateway.self_manifest import SELF_AGENT_ID
from force_gateway.telemetry import METHOD_LABEL, HygieneReport, analyze

Upstream = Callable[[dict[str, Any], dict[str, str]], tuple[int, dict[str, Any]]]


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
    # ADR 10: bypass windows are visible here, never silent.
    coverage: dict[str, Any]
    hygiene_trend: dict[str, Any]
    active_alerts: list[str]
    recent: list[TelemetryRecord]


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
    cov = app.state.coverage
    cov["bypass_entries"] += 1
    _bump(cov["bypass_reasons"], reason)
    app.state.bypass_remaining = app.state.bypass_cooldown
    _ledger_event(app, "gateway.bypass", {
        "reason": reason, "cooldown_requests": app.state.bypass_cooldown})


def _maybe_judge(app: FastAPI, preset: str, text: str,
                 record: TelemetryRecord) -> None:
    """Deterministic 1-in-N sampled hygiene judgment — every skip is counted
    (fail-open: no path here may fail the proxied call)."""
    judge = app.state.hygiene_judge
    if judge is None or app.state.sample_every <= 0:
        return
    if app.state.request_count % app.state.sample_every != 0:
        return
    cov = app.state.coverage
    gov = app.state.governor
    # Spend gate: the judge runs on the Gateway's OWN cap (self-manifest).
    if gov is None:
        _bump(cov["judge_bypassed"], "no_governor")
        return
    try:
        resp = gov.get(f"/status/{SELF_AGENT_ID}")
    except Exception:
        _bump(cov["judge_bypassed"], "governor_unreachable")
        return
    if resp.status_code == 404:
        _bump(cov["judge_bypassed"], "no_cap")
        return
    if resp.status_code != 200:
        _bump(cov["judge_bypassed"], "governor_error")
        return
    if resp.json().get("state") == "BLOCK":
        _bump(cov["judge_bypassed"], "budget")
        return
    try:
        j = judge.judge(text, preset)
    except Exception:
        _bump(cov["judge_bypassed"], "error")
        return
    cov["judged_samples"] += 1
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
    alert = app.state.drift.record(preset, j.overall, j.model, j.rubric_version)
    if alert is not None:
        _ledger_event(app, "gateway.drift_alert", {
            "route": alert.route, "baseline_mean": alert.baseline_mean,
            "band": alert.band, "window_means": list(alert.window_means),
            "model": alert.model, "rubric_version": alert.rubric_version,
        })


def create_app(upstream: Upstream | None = None, governor_client=None,
               ledger_client=None, hygiene_judge=None,
               sample_every: int | None = None, drift: DriftTracker | None = None,
               latency_budget_ms: float | None = None,
               bypass_cooldown: int | None = None) -> FastAPI:
    app = FastAPI(
        title="force-gateway",
        version=__version__,
        description="FORCE preset injection + hygiene telemetry for the "
        "Anthropic Messages API shape.",
    )
    install_authn(app)
    if upstream is not None:
        app.state.upstream = upstream
    elif os.environ.get("FORCE_GATEWAY_MOCK") == "1":
        app.state.upstream = mock_upstream
    else:
        app.state.upstream = real_upstream
    app.state.governor = governor_client
    app.state.ledger = ledger_client
    app.state.records: list[TelemetryRecord] = []
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
    app.state.request_count = 0
    app.state.bypass_remaining = 0
    app.state.coverage = {
        "instrumented": 0, "bypassed": 0, "bypass_entries": 0,
        "bypass_reasons": {}, "judged_samples": 0, "judge_bypassed": {},
        "sample_every": app.state.sample_every,
    }

    @app.get("/health")
    def health() -> dict:
        judge = app.state.hygiene_judge
        return {"ok": True, "service": "force-gateway", "version": __version__,
                "mock": app.state.upstream is mock_upstream,
                "judge": (getattr(judge, "name", "custom")
                          if judge is not None else "off"),
                "sample_every": app.state.sample_every,
                "bypass_remaining": app.state.bypass_remaining}

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
        x_force_preset: str = Header(default="analysis"),
        x_field_agent_id: str | None = Header(default=None),
        anthropic_version: str = Header(default="2023-06-01"),
    ) -> dict[str, Any]:
        # Bypass mode (ADR 10 §4): the Gateway's own trouble must never block
        # production traffic — forward the ORIGINAL body uninstrumented (no
        # injection, no telemetry) and count the coverage gap.
        if app.state.bypass_remaining > 0:
            app.state.bypass_remaining -= 1
            app.state.coverage["bypassed"] += 1
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
            app.state.records.append(record)

            if app.state.governor is not None and x_field_agent_id:
                try:
                    # Cost-aware report: model + input/output tokens so the
                    # governor prices it and runs rogue detection. Falls back to
                    # the raw-token /spend path for older governors (404 on /usage).
                    resp = app.state.governor.post(
                        "/usage",
                        json={
                            "agent_id": x_field_agent_id,
                            "model": record.model,
                            "input_tokens": record.input_tokens,
                            "output_tokens": record.output_tokens,
                            "note": "force-gateway LLM call",
                        },
                    )
                    if getattr(resp, "status_code", 201) == 404:
                        app.state.governor.post(
                            "/spend",
                            json={
                                "agent_id": x_field_agent_id,
                                "tokens": record.input_tokens + record.output_tokens,
                                "note": "force-gateway LLM call",
                            },
                        )
                except Exception:
                    pass  # metering is best-effort; the sentinel gates actions

            app.state.request_count += 1
            _maybe_judge(app, x_force_preset, text, record)
        except Exception:
            _enter_bypass(app, "instrumentation_fault")
        else:
            overhead_ms = (time.perf_counter() - i0) * 1000
            if overhead_ms > app.state.latency_budget_ms:
                _enter_bypass(app, "latency_budget")
        app.state.coverage["instrumented"] += 1
        return response

    @app.get("/telemetry", response_model=TelemetrySummary)
    def telemetry(limit: int = 20) -> TelemetrySummary:
        records = app.state.records
        by_preset: dict[str, int] = {}
        for r in records:
            by_preset[r.preset] = by_preset.get(r.preset, 0) + 1
        trend = app.state.drift.status()
        return TelemetrySummary(
            total_requests=len(records),
            by_preset=by_preset,
            responses_with_confidence_tags=sum(
                1 for r in records if r.hygiene.has_confidence_tags
            ),
            responses_clean_of_flattery=sum(
                1 for r in records if r.hygiene.clean_of_flattery
            ),
            responses_with_cot_structure=sum(
                1 for r in records if r.hygiene.cot_structure
            ),
            total_corrections=sum(r.hygiene.corrections for r in records),
            total_input_tokens=sum(r.input_tokens for r in records),
            total_output_tokens=sum(r.output_tokens for r in records),
            coverage=dict(app.state.coverage,
                          bypass_remaining=app.state.bypass_remaining),
            hygiene_trend=trend,
            active_alerts=[route for route, st in trend.items()
                           if st["alert_active"]],
            recent=records[-limit:],
        )

    return app
