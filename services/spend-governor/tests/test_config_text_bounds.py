"""S7-17 — the PUT bodies (/caps, /policies, /rate-limits) bound their text: ids 128,
actions 200, currency ^[A-Z]{3}$, on_breach halt|escalate. The READ side stays lax, so a row
stored before the bound still loads (the C-316 / C-363 pattern)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

A = "invoicing-agent"


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def cap(agent=A, **over):
    return {"agent_id": agent, "currency": "USD", "limit_cents": 100, "period": "daily",
            "escalate_at_pct": 80, **over}


def put_cap(c, agent=A, **over):
    return c.put(f"/caps/{agent}", json=cap(agent, **over))


def test_valid_shapes_still_200(client):
    assert put_cap(client).status_code == 200
    assert put_cap(client, currency="CAD", on_breach="escalate").status_code == 200
    assert client.put(f"/policies/{A}", json={"agent_id": A, "token_rate_limit": 5}).status_code == 200
    assert client.put(f"/rate-limits/{A}", json={"agent_id": A, "rate_limits": [
        {"action": "send_email", "max": 5, "period": "hourly"}]}).status_code == 200


def test_agent_id_128_ok_129_refused_on_all_three(client):
    ok, over = "a" * 128, "b" * 129
    assert put_cap(client, ok).status_code == 200
    assert client.put(f"/policies/{ok}", json={"agent_id": ok}).status_code == 200
    assert client.put(f"/rate-limits/{ok}", json={"agent_id": ok, "rate_limits": []}).status_code == 200
    for r in (put_cap(client, over),
              client.put(f"/policies/{over}", json={"agent_id": over}),
              client.put(f"/rate-limits/{over}", json={"agent_id": over, "rate_limits": []})):
        assert r.status_code == 422 and over not in r.text


@pytest.mark.parametrize("agent", ["", "   "])
def test_blank_agent_id_refused(client, agent):
    assert put_cap(client, "x", agent_id=agent).status_code == 422


def test_action_200_ok_201_and_blank_refused(client):
    put_cap(client)

    def rl(action):
        return client.put(f"/rate-limits/{A}", json={"agent_id": A, "rate_limits": [
            {"action": action, "max": 1, "period": "hourly"}]})
    assert rl("a" * 200).status_code == 200
    r = rl("b" * 201)
    assert r.status_code == 422 and "b" * 201 not in r.text
    assert rl("   ").status_code == 422


@pytest.mark.parametrize("currency", ["usd", "US", "USDX", "", "12$", "U D"])
def test_currency_must_be_three_capitals(client, currency):
    assert put_cap(client, currency=currency).status_code == 422


@pytest.mark.parametrize("value", ["ignore", "HALT", "", "halt, escalate"])
def test_on_breach_limited_to_the_documented_values(client, value):
    assert put_cap(client, on_breach=value).status_code == 422


def test_on_breach_default_is_halt(client):
    body = cap()
    r = client.put(f"/caps/{A}", json=body)
    assert r.status_code == 200 and r.json()["on_breach"] == "halt"


def test_legacy_rows_with_free_text_still_read(store, client):
    long_id, ancient = "L" * 300, "legacy"
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO caps (agent_id, currency, limit_cents, token_limit, action_limit, period,"
            " escalate_at_pct, on_breach) VALUES (?, 'usd', 100, NULL, NULL, 'daily', 80, 'ignore')",
            (long_id,))
        store._conn.execute(
            "INSERT INTO caps (agent_id, currency, limit_cents, token_limit, action_limit, period,"
            " escalate_at_pct, on_breach) VALUES (?, 'US dollars', 100, NULL, NULL, 'daily', 80, 'ignore')",
            (ancient,))
    for agent in (long_id, ancient):
        r = client.get(f"/caps/{agent}")
        assert r.status_code == 200, r.text
        assert client.get(f"/status/{agent}").status_code == 200
    assert client.get(f"/caps/{ancient}").json()["on_breach"] == "ignore"
    assert store.get_cap(long_id).currency == "usd"
