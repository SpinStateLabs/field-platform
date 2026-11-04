"""S7-16 — the readers agree with /status: an empty agent_id filters to nothing, /usage
carries the real window and answers 404 for an uncapped agent."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import Escalation, GovernorStore

NOW = datetime(2026, 3, 15, 12, 30, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store, clock=lambda: NOW))


def _cap(c, agent, period="daily"):
    body = {"agent_id": agent, "currency": "USD", "limit_cents": 100, "period": period,
            "escalate_at_pct": 80}
    assert c.put(f"/caps/{agent}", json=body).status_code == 200


def _esc(store, agent, n):
    store.add_escalation(Escalation(escalation_id=f"e-{agent}-{n}", agent_id=agent,
                                    ts=NOW.isoformat(), kind="cents", spent=90, limit=100, pct=90))


def test_empty_agent_id_lists_nothing_not_everything(store, client):
    _esc(store, "a1", 1)
    _esc(store, "a2", 1)
    assert len(client.get("/escalations").json()) == 2
    assert [e["agent_id"] for e in client.get("/escalations", params={"agent_id": "a1"}).json()] == ["a1"]
    r = client.get("/escalations", params={"agent_id": ""})
    assert r.status_code == 200 and r.json() == []
    assert store.open_escalations("") == []


@pytest.mark.parametrize("period, seconds", [
    ("daily", 12 * 3600 + 30 * 60),
    ("monthly", 14 * 86400 + 12 * 3600 + 30 * 60),
])
def test_usage_window_seconds_is_the_period_span(client, period, seconds):
    _cap(client, "a1", period)
    client.post("/usage", json={"agent_id": "a1", "model": "claude-opus-4-8",
                                "input_tokens": 5, "output_tokens": 5})
    r = client.get("/usage/a1")
    assert r.status_code == 200
    assert r.json()["window_seconds"] == seconds


def test_usage_window_seconds_with_a_policy(client):
    _cap(client, "a1", "daily")
    assert client.put("/policies/a1", json={"agent_id": "a1", "token_rate_limit": 100}).status_code == 200
    assert client.get("/usage/a1").json()["window_seconds"] == 12 * 3600 + 30 * 60


def test_total_period_counts_from_the_epoch(client):
    _cap(client, "a1", "total")
    assert client.get("/usage/a1").json()["window_seconds"] == int(NOW.timestamp())


def test_usage_for_an_uncapped_agent_is_404_like_status(client):
    for path in ("/usage/ghost", "/status/ghost"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert "no spend cap configured for 'ghost'" in r.json()["detail"]
    _cap(client, "a1")
    assert client.get("/usage/a1").status_code == 200
