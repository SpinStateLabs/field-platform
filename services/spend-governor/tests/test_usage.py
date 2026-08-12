"""Token-usage governance tests: cost from model+tokens, cap folding, and
the three rogue signals."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3")))


AGENT = "invoicing-agent"


def cap(client, limit_cents=50_000):
    r = client.put(f"/caps/{AGENT}", json={
        "agent_id": AGENT, "limit_cents": limit_cents, "period": "daily",
        "escalate_at_pct": 80})
    assert r.status_code == 200


def usage(client, model="claude-opus-4-8", i=1000, o=1000, cache=0):
    return client.post("/usage", json={
        "agent_id": AGENT, "model": model, "input_tokens": i,
        "output_tokens": o, "cache_read_tokens": cache})


def test_cost_computed_from_model_and_tokens(client):
    cap(client)
    r = usage(client, "claude-opus-4-8", i=1000, o=1000)
    assert r.status_code == 201
    body = r.json()
    # 1000*50 + 1000*250 = 300000 units = $0.03.
    assert body["record"]["cost_units"] == 300_000
    assert body["status"]["token_cost_units"] == 300_000
    assert body["status"]["token_cost_display"] == "$0.03"
    assert body["rogue"] == []


def test_model_choice_changes_cost(client):
    cap(client)
    # same tokens, cheaper model → lower cost.
    usage(client, "claude-haiku-4-5", i=1000, o=1000)  # 1000*10+1000*50=60000
    s = client.get(f"/usage/{AGENT}").json()
    assert s["total_cost_units"] == 60_000
    assert s["by_model"][0]["model"] == "claude-haiku-4-5"


def test_token_cost_folds_into_dollar_cap(client):
    # $5 daily cap → 500 cents. Opus: reach it with input tokens.
    # cost cents = units//100000. Need >= 500 cents = 5e7 units.
    # 1e7 input tokens * 50 units = 5e8 units = $50 → far over $5 cap.
    cap(client, limit_cents=500)
    r = usage(client, "claude-opus-4-8", i=10_000_000, o=0)
    assert r.json()["status"]["state"] == "BLOCK"
    assert "cents cap reached" in r.json()["status"]["detail"]


def test_escalate_before_cap_on_token_cost(client):
    cap(client, limit_cents=1000)  # $10 cap, escalate at 80% = $8
    # $8.50 of Opus output: 8.5e6 tokens? output 250 units/tok → need
    # 850 cents = 8.5e7 units / 250 = 340000 output tokens.
    r = usage(client, "claude-opus-4-8", i=0, o=340_000)
    assert r.json()["status"]["state"] == "ESCALATE"


def test_rogue_model_flagged(client):
    cap(client)
    client.put(f"/policies/{AGENT}", json={
        "agent_id": AGENT, "allowed_models": ["claude-haiku-4-5"]})
    # agent supposed to use Haiku, burns Opus tokens → rogue_model
    r = usage(client, "claude-opus-4-8", i=1000, o=1000)
    kinds = [f["kind"] for f in r.json()["rogue"]]
    assert "rogue_model" in kinds
    escs = client.get("/escalations").json()
    assert any(e["kind"] == "usage:rogue_model" for e in escs)


def test_rogue_burst_flagged(client):
    cap(client)
    client.put(f"/policies/{AGENT}", json={
        "agent_id": AGENT, "allowed_models": [], "token_rate_limit": 5000,
        "rate_window_seconds": 3600})
    usage(client, "claude-haiku-4-5", i=2000, o=2000)  # 4000, under
    r = usage(client, "claude-haiku-4-5", i=1000, o=1000)  # 6000 total, over 5000
    kinds = [f["kind"] for f in r.json()["rogue"]]
    assert "rogue_burst" in kinds


def test_unpriced_model_flagged_not_guessed(client):
    cap(client)
    r = usage(client, "gpt-4o-mystery", i=1000, o=1000)
    body = r.json()
    assert body["record"]["priced"] is False
    assert body["record"]["cost_units"] is None
    assert "unpriced" in [f["kind"] for f in body["rogue"]]
    # unpriced usage contributes no dollar cost (can't fabricate it) …
    assert body["status"]["token_cost_units"] == 0
    # … but the tokens still count toward the token dimension.
    assert body["status"]["spent_tokens"] == 2000


def test_usage_without_cap_refused(client):
    r = client.post("/usage", json={
        "agent_id": "ghost", "model": "claude-opus-4-8",
        "input_tokens": 1, "output_tokens": 1})
    assert r.status_code == 404
    assert "ungoverned token usage" in r.json()["detail"]


def test_usage_breakdown_by_model(client):
    cap(client)
    usage(client, "claude-opus-4-8", i=1000, o=500)
    usage(client, "claude-haiku-4-5", i=2000, o=1000)
    s = client.get(f"/usage/{AGENT}").json()
    models = {m["model"]: m for m in s["by_model"]}
    assert set(models) == {"claude-opus-4-8", "claude-haiku-4-5"}
    assert models["claude-opus-4-8"]["input_tokens"] == 1000
    assert s["total_input_tokens"] == 3000
