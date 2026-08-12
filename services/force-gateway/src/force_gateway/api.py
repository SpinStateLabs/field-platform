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
from force_gateway.presets import PRESETS, preset_block
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


def create_app(upstream: Upstream | None = None, governor_client=None) -> FastAPI:
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
    app.state.records: list[TelemetryRecord] = []

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "force-gateway", "version": __version__,
                "mock": app.state.upstream is mock_upstream}

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

        return response

    @app.get("/telemetry", response_model=TelemetrySummary)
    def telemetry(limit: int = 20) -> TelemetrySummary:
        records = app.state.records
        by_preset: dict[str, int] = {}
        for r in records:
            by_preset[r.preset] = by_preset.get(r.preset, 0) + 1
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
            recent=records[-limit:],
        )

    return app
