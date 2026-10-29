"""C-363 (reviewer C-356 F-C356-1, C-365 F-C365-1): a usage-policy row stored before the C-315 bounds.

Validating it at read answered 500 on five endpoints, `POST /spend` among them after the spend was written. The
row is now served without re-validation, never written back, logged once per row without its values and counted
in `/health` `policies_over_bound`. It is never served so that it enforces LESS than the stored row: a token
limit above the bound is lowered to it (a smaller limit fires earlier); the window is never shortened (a shorter
window counts fewer tokens), and the window arithmetic saturates instead of overflowing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from spend_governor import core
from spend_governor.api import create_app
from spend_governor.core import MAX_AMOUNT, MAX_RATE_PERIOD_SECONDS, GovernorStore

AGENT = "legacy-agent"
INT64_MAX = 2**63 - 1
TWO_YEARS = 2 * 366 * 86400

#: the four shapes of the C-365 probe: a limit above the bound; a window above 366 days (valid on main); a window
#: no timedelta can hold; both.
SHAPES = {
    "limit": (5 * 10**12, 3600),
    "window": (100, TWO_YEARS),
    "huge_window": (100, 10**12),
    "both": (INT64_MAX, INT64_MAX),
}


@pytest.fixture(autouse=True)
def _fresh_warning_memory(monkeypatch):
    monkeypatch.setattr(core, "_policy_row_warned", set())


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store))
    cap = {"agent_id": AGENT, "currency": "USD", "limit_cents": 100000, "period": "daily", "escalate_at_pct": 80}
    assert c.put(f"/caps/{AGENT}", json=cap).status_code == 200
    return c


def legacy_policy(store, rate, window, agent=AGENT):
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO usage_policies (agent_id, allowed_models, token_rate_limit,"
            " rate_window_seconds) VALUES (?, '[]', ?, ?)", (agent, rate, window))


def usage_row(store, tokens, age: timedelta, agent=AGENT):
    ts = (datetime.now(timezone.utc) - age).isoformat()
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO usage VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"e-{ts}-{tokens}", agent, ts, "claude-opus-4-8", tokens, 0, 0, 0, 1, None))


def stored(store, agent=AGENT):
    with store._lock:
        r = store._conn.execute("SELECT token_rate_limit, rate_window_seconds FROM usage_policies "
                                "WHERE agent_id=?", (agent,)).fetchone()
    return None if r is None else (r["token_rate_limit"], r["rate_window_seconds"])


def five_endpoints(c):
    return {
        "GET /policies": c.get(f"/policies/{AGENT}"),
        "POST /spend": c.post("/spend", json={"agent_id": AGENT, "cents": 1}),
        "GET /status": c.get(f"/status/{AGENT}"),
        "POST /usage": c.post("/usage", json={"agent_id": AGENT, "model": "claude-opus-4-8",
                                              "input_tokens": 1, "output_tokens": 1}),
        "GET /usage": c.get(f"/usage/{AGENT}"),
    }


@pytest.mark.parametrize("shape", SHAPES)
def test_every_legacy_shape_answers_2xx_on_all_five_endpoints(store, client, shape):
    legacy_policy(store, *SHAPES[shape])
    got = {k: v.status_code for k, v in five_endpoints(client).items()}
    assert all(200 <= s < 300 for s in got.values()), got


@pytest.mark.parametrize("shape", SHAPES)
def test_the_row_is_never_written_back(store, client, shape):
    legacy_policy(store, *SHAPES[shape])
    five_endpoints(client)
    assert stored(store) == SHAPES[shape]


@pytest.mark.parametrize("shape", SHAPES)
def test_the_served_limit_is_never_above_and_the_window_never_below_the_stored_row(store, client, shape):
    rate, window = SHAPES[shape]
    legacy_policy(store, rate, window)
    got = client.get(f"/policies/{AGENT}").json()
    assert got["token_rate_limit"] <= rate
    assert got["rate_window_seconds"] >= window


def test_a_limit_above_the_bound_is_lowered_to_it_and_nothing_else(store, client):
    legacy_policy(store, INT64_MAX, 3600)
    got = client.get(f"/policies/{AGENT}").json()
    assert (got["token_rate_limit"], got["rate_window_seconds"]) == (MAX_AMOUNT, 3600)


def test_a_window_above_the_bound_is_served_as_stored_never_shortened(store, client):
    legacy_policy(store, 100, INT64_MAX)
    assert client.get(f"/policies/{AGENT}").json()["rate_window_seconds"] == INT64_MAX


def test_a_lowered_limit_fires_where_the_stored_one_would_not(store, client):
    """The clamped limit enforces at least as much: 10**12 tokens in the window throttle under the served limit,
    and would not under the stored 5 * 10**12."""
    legacy_policy(store, 5 * 10**12, 3600)
    usage_row(store, MAX_AMOUNT, timedelta(minutes=5))
    st = client.get(f"/status/{AGENT}").json()
    assert st["state"] == "THROTTLED"


@pytest.mark.parametrize("window", [TWO_YEARS, 10**12, INT64_MAX])
def test_a_row_older_than_the_old_bound_still_counts_in_a_longer_window(store, client, window):
    """What a clamp of the window to 366 days would loosen: a 400-day-old row, inside the stored window, is
    counted, so the limit of 100 is exhausted."""
    legacy_policy(store, 100, window)
    usage_row(store, 100, timedelta(days=400))
    st = client.get(f"/status/{AGENT}").json()
    assert st["state"] == "THROTTLED"
    assert st["retry_after_seconds"] >= 1


@pytest.mark.parametrize("shape", SHAPES)
def test_the_log_comes_once_per_row_without_values(store, client, caplog, shape):
    legacy_policy(store, *SHAPES[shape])
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        for _ in range(3):
            five_endpoints(client)
    msgs = [r.getMessage() for r in caplog.records if "usage policy row" in r.getMessage()]
    assert len(msgs) == 1
    assert AGENT in msgs[0]
    rate, window = SHAPES[shape]
    for value in (rate, window):
        assert str(value) not in msgs[0]
    assert ("token_rate_limit" in msgs[0]) == (rate > MAX_AMOUNT)
    assert ("rate_window_seconds" in msgs[0]) == (window > MAX_RATE_PERIOD_SECONDS)


def test_a_row_rewritten_with_other_values_warns_again(store, client, caplog):
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        legacy_policy(store, 100, TWO_YEARS)
        client.get(f"/policies/{AGENT}")
        legacy_policy(store, 100, TWO_YEARS + 1)
        client.get(f"/policies/{AGENT}")
    assert len([r for r in caplog.records if "usage policy row" in r.getMessage()]) == 2


@pytest.mark.parametrize("rate,window", [(100, 3600), (MAX_AMOUNT, MAX_RATE_PERIOD_SECONDS), (None, 60)])
def test_an_in_bounds_row_is_served_as_stored_with_no_log_and_no_count(store, client, caplog, rate, window):
    legacy_policy(store, rate, window)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        got = client.get(f"/policies/{AGENT}").json()
    assert (got["token_rate_limit"], got["rate_window_seconds"]) == (rate, window)
    assert not [r for r in caplog.records if "usage policy row" in r.getMessage()]
    assert client.get("/health").json()["policies_over_bound"] == 0


def test_health_counts_rows_over_either_bound(store, client):
    assert client.get("/health").json()["policies_over_bound"] == 0
    legacy_policy(store, INT64_MAX, INT64_MAX, "a")        # one row, two fields
    legacy_policy(store, 100, TWO_YEARS, "b")
    legacy_policy(store, 5 * 10**12, 60, "c")
    legacy_policy(store, 100, 3600, "d")                   # in bounds
    legacy_policy(store, MAX_AMOUNT, MAX_RATE_PERIOD_SECONDS, "e")   # at the bounds
    assert client.get("/health").json()["policies_over_bound"] == 3


def test_a_put_above_a_bound_is_still_422(client):
    r = client.put(f"/policies/{AGENT}", json={"agent_id": AGENT, "rate_window_seconds": TWO_YEARS})
    assert r.status_code == 422
    assert client.get(f"/policies/{AGENT}").status_code == 404


def test_rolling_window_start_saturates_instead_of_overflowing():
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    assert core.rolling_window_start(now, 3600) == now - timedelta(hours=1)
    for seconds in (10**12, INT64_MAX):
        got = core.rolling_window_start(now, seconds)
        assert got == datetime.min.replace(tzinfo=timezone.utc)
