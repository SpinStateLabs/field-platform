"""Pins the README row "carries the preset's FORCE block" to what the code does.

Roadmap audit (PR 1086, finding 3): the row said EVERY proxied call carries the
FORCE block, but calls forwarded in a bypass window and `x-force-passthrough:
judge` calls are forwarded uninstrumented BY DESIGN (ADR 10). The README now
says so; these tests fail if either the behaviour or the row drifts."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream

README = Path(__file__).resolve().parents[1] / "README.md"
BODY = {"model": "m", "max_tokens": 16, "system": "caller system prompt",
        "messages": [{"role": "user", "content": "ping"}]}
FORCE_HEAD = "# FORCE Runtime Protocol"


def _app(seen, **kw):
    def upstream(body, headers):
        seen.append(json.loads(json.dumps(body)))
        return mock_upstream(body, headers)
    return TestClient(create_app(upstream=upstream, latency_budget_ms=10_000.0, **kw))


def test_instrumented_call_carries_the_force_block():
    seen = []
    c = _app(seen)
    assert c.post("/v1/messages", json=BODY).status_code == 200
    assert seen[0]["system"].startswith(FORCE_HEAD)
    assert "caller system prompt" in seen[0]["system"]


def test_bypassed_call_carries_no_force_block_and_is_counted():
    seen = []
    c = _app(seen, bypass_cooldown=1)
    c.app.state.bypass_remaining = 1  # a bypass window is open
    assert c.post("/v1/messages", json=BODY).status_code == 200
    assert seen[0] == BODY  # byte-identical: no FORCE block
    assert c.get("/telemetry").json()["coverage"]["bypassed"] == 1


def test_judge_passthrough_carries_no_force_block_and_is_counted():
    seen = []
    c = _app(seen)
    r = c.post("/v1/messages", json=BODY, headers={"x-force-passthrough": "judge"})
    assert r.status_code == 200
    assert seen[0] == BODY
    assert c.get("/telemetry").json()["coverage"]["passthrough"] == 1


def _row():
    rows = [ln for ln in README.read_text(encoding="utf-8").splitlines()
            if ln.startswith("|") and "FORCE block" in ln and "Enforced in code" in ln]
    assert len(rows) == 1, rows
    return rows[0]


def test_readme_row_states_the_bypass_and_passthrough_exceptions():
    row = _row()
    assert "Every proxied call carries" not in row  # the unqualified claim
    assert "bypass" in row and "passthrough" in row
    assert "no FORCE block" in row
    assert "coverage.bypassed" in row and "coverage.passthrough" in row
