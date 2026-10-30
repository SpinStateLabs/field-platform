"""C-315 (reviewer C-302): the integer inputs C-246 left unbounded. `PUT /rate-limits` `max`,
`PUT /policies` `token_rate_limit` and `rate_window_seconds` above the bound answer 422 with nothing
written; at the bound they are stored and a spend still answers (a window is subtracted from now)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import MAX_AMOUNT, MAX_RATE_PERIOD_SECONDS, GovernorStore

AGENT = "invoicing-agent"
OVER = [2**63 - 1, 2**63, 2**64, 10**19]


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store))
    cap = {"agent_id": AGENT, "currency": "USD", "limit_cents": 100, "period": "daily",
           "escalate_at_pct": 80}
    assert c.put(f"/caps/{AGENT}", json=cap).status_code == 200
    return c


def put_limits(c, max_):
    return c.put(f"/rate-limits/{AGENT}", json={
        "agent_id": AGENT, "rate_limits": [{"action": "send", "max": max_, "period": "hourly"}]})


def put_policy(c, **over):
    return c.put(f"/policies/{AGENT}", json={"agent_id": AGENT, **over})


def spend(c):
    return c.post("/spend", json={"agent_id": AGENT, "cents": 1, "action": "send"})


def test_a_rate_limit_max_at_the_bound_is_stored_and_a_spend_answers(client):
    assert put_limits(client, MAX_AMOUNT).status_code == 200
    assert client.get(f"/rate-limits/{AGENT}").json()["rate_limits"][0]["max"] == MAX_AMOUNT
    assert spend(client).status_code == 201


@pytest.mark.parametrize("value", [MAX_AMOUNT + 1, *OVER])
def test_a_rate_limit_max_above_the_bound_is_422_and_writes_nothing(client, value):
    assert put_limits(client, 5).status_code == 200
    assert put_limits(client, value).status_code == 422
    assert [r["max"] for r in client.get(f"/rate-limits/{AGENT}").json()["rate_limits"]] == [5]


def test_a_token_rate_limit_at_the_bound_is_stored(client):
    assert put_policy(client, token_rate_limit=MAX_AMOUNT).status_code == 200
    assert client.get(f"/policies/{AGENT}").json()["token_rate_limit"] == MAX_AMOUNT


@pytest.mark.parametrize("value", [MAX_AMOUNT + 1, *OVER])
def test_a_token_rate_limit_above_the_bound_is_422_and_writes_nothing(client, value):
    assert put_policy(client, token_rate_limit=7).status_code == 200
    assert put_policy(client, token_rate_limit=value).status_code == 422
    assert client.get(f"/policies/{AGENT}").json()["token_rate_limit"] == 7


def test_a_window_at_the_bound_is_stored_and_a_spend_and_usage_post_answer(client):
    assert put_policy(client, token_rate_limit=10, rate_window_seconds=MAX_RATE_PERIOD_SECONDS
                      ).status_code == 200
    assert spend(client).status_code == 201
    assert client.post("/usage", json={"agent_id": AGENT, "model": "claude-sonnet-4-5",
                                       "input_tokens": 1}).status_code in (200, 201)


@pytest.mark.parametrize("value", [MAX_RATE_PERIOD_SECONDS + 1, *OVER])
def test_a_window_above_the_bound_is_422_and_writes_nothing(client, value):
    assert put_policy(client, token_rate_limit=7, rate_window_seconds=60).status_code == 200
    assert put_policy(client, token_rate_limit=9, rate_window_seconds=value).status_code == 422
    stored = client.get(f"/policies/{AGENT}").json()
    assert (stored["token_rate_limit"], stored["rate_window_seconds"]) == (7, 60)


@pytest.mark.parametrize("body", [{"token_rate_limit": 0}, {"token_rate_limit": -1},
                                  {"rate_window_seconds": 0}, {"rate_window_seconds": -1}])
def test_the_existing_lower_bounds_still_hold(client, body):
    assert put_policy(client, **body).status_code == 422
