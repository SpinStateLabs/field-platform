"""C-316 (reviewer C-302): a cap row stored before the C-246 bound. `SpendCapConfig` now refuses a limit above
MAX_AMOUNT, so reading such a row used to raise a validation error: every status and spend of that agent
answered 500. The row is served clamped to the bound, said in the log (field names only) and counted in
`/health` `caps_over_bound`; writing a cap above the bound is still 422."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from spend_governor import core
from spend_governor.api import create_app
from spend_governor.core import MAX_AMOUNT, GovernorStore

AGENT = "legacy-agent"
INT64_MAX = 2**63 - 1


@pytest.fixture(autouse=True)
def _fresh_warning_memory(monkeypatch):
    monkeypatch.setattr(core, "_cap_row_warned", core._WarnOnce())


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def legacy_row(store: GovernorStore, agent: str = AGENT, limit_cents=None, token_limit=None,
               action_limit=None) -> None:
    """A row as an older governor wrote it: straight into the table, past the model."""
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO caps (agent_id, currency, limit_cents, token_limit, action_limit, period,"
            " escalate_at_pct, on_breach) VALUES (?, 'USD', ?, ?, ?, 'daily', 80, 'halt')",
            (agent, limit_cents, token_limit, action_limit))


@pytest.mark.parametrize("stored", [MAX_AMOUNT + 1, 5 * 10**12, INT64_MAX])
@pytest.mark.parametrize("field", ["limit_cents", "token_limit", "action_limit"])
def test_a_legacy_row_is_served_clamped_not_refused(store, client, field, stored):
    legacy_row(store, **{field: stored})
    got = client.get(f"/caps/{AGENT}")
    assert got.status_code == 200
    assert got.json()[field] == MAX_AMOUNT <= stored


def test_status_and_spend_of_a_legacy_agent_answer_not_500(store, client):
    legacy_row(store, limit_cents=INT64_MAX)
    assert client.get(f"/status/{AGENT}").status_code == 200
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 5})
    assert r.status_code == 201
    assert client.get(f"/status/{AGENT}").status_code == 200


def test_only_the_over_bound_fields_are_clamped(store, client):
    legacy_row(store, limit_cents=INT64_MAX, token_limit=1234, action_limit=MAX_AMOUNT)
    cap = client.get(f"/caps/{AGENT}").json()
    assert (cap["limit_cents"], cap["token_limit"], cap["action_limit"]) == (MAX_AMOUNT, 1234, MAX_AMOUNT)


def test_a_row_at_the_bound_is_untouched_and_not_logged_or_counted(store, client, caplog):
    legacy_row(store, limit_cents=MAX_AMOUNT)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        assert client.get(f"/caps/{AGENT}").json()["limit_cents"] == MAX_AMOUNT
    assert not [r for r in caplog.records if "above the bound" in r.getMessage()]
    assert client.get("/health").json()["caps_over_bound"] == 0


def test_the_read_says_which_fields_and_never_the_value(store, client, caplog):
    legacy_row(store, limit_cents=5 * 10**12, token_limit=7 * 10**12)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        client.get(f"/caps/{AGENT}")
    msgs = [r.getMessage() for r in caplog.records if "above the bound" in r.getMessage()]
    assert len(msgs) == 1
    assert AGENT in msgs[0] and "limit_cents" in msgs[0] and "token_limit" in msgs[0]
    assert "action_limit" not in msgs[0]
    assert str(5 * 10**12) not in msgs[0] and str(7 * 10**12) not in msgs[0]


def test_health_counts_rows_not_fields(store, client):
    assert client.get("/health").json()["caps_over_bound"] == 0
    legacy_row(store, "a", limit_cents=INT64_MAX, token_limit=INT64_MAX)          # one row, two fields
    legacy_row(store, "b", action_limit=MAX_AMOUNT + 1)
    legacy_row(store, "c", limit_cents=100)                                       # in bounds
    legacy_row(store, "d", limit_cents=MAX_AMOUNT)                                # at the bound
    assert client.get("/health").json()["caps_over_bound"] == 2


def test_health_counts_a_row_that_only_the_last_column_exceeds(store, client):
    legacy_row(store, limit_cents=1, token_limit=1, action_limit=MAX_AMOUNT + 1)
    assert client.get("/health").json()["caps_over_bound"] == 1


def test_writing_a_cap_above_the_bound_is_still_422_and_not_counted(client):
    body = {"agent_id": AGENT, "currency": "USD", "limit_cents": MAX_AMOUNT + 1, "period": "daily",
            "escalate_at_pct": 80}
    assert client.put(f"/caps/{AGENT}", json=body).status_code == 422
    assert client.get(f"/caps/{AGENT}").status_code == 404
    assert client.get("/health").json()["caps_over_bound"] == 0


def test_an_in_bounds_row_is_served_as_stored(store, client):
    legacy_row(store, limit_cents=4242, token_limit=77)
    cap = client.get(f"/caps/{AGENT}").json()
    assert (cap["limit_cents"], cap["token_limit"], cap["action_limit"]) == (4242, 77, None)


# --- C-364 (reviewer C-359 F-C359-1): the warning comes once per stored row and process --------------------


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if "above the bound" in r.getMessage()]


def test_the_warning_comes_once_across_many_reads(store, client, caplog):
    legacy_row(store, limit_cents=INT64_MAX)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        for _ in range(5):
            client.get(f"/caps/{AGENT}")
            client.get(f"/status/{AGENT}")
    assert len(_warnings(caplog)) == 1


def test_the_gauge_keeps_counting_while_the_warning_is_silent(store, client, caplog):
    legacy_row(store, limit_cents=INT64_MAX)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        for _ in range(3):
            client.get(f"/caps/{AGENT}")
            assert client.get("/health").json()["caps_over_bound"] == 1
    assert len(_warnings(caplog)) == 1


def test_a_row_rewritten_with_other_values_warns_again(store, client, caplog):
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        legacy_row(store, limit_cents=INT64_MAX)
        client.get(f"/caps/{AGENT}")
        legacy_row(store, limit_cents=INT64_MAX - 1)
        client.get(f"/caps/{AGENT}")
        client.get(f"/caps/{AGENT}")
    assert len(_warnings(caplog)) == 2


def test_each_legacy_agent_warns_once(store, client, caplog):
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        for agent in ("a", "b", "c"):
            legacy_row(store, agent, limit_cents=INT64_MAX)
        for _ in range(2):
            for agent in ("a", "b", "c"):
                client.get(f"/caps/{agent}")
    msgs = _warnings(caplog)
    assert len(msgs) == 3
    assert {m.split("'")[1] for m in msgs} == {"a", "b", "c"}


def test_a_change_in_any_one_limit_column_warns_again(store, client, caplog):
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        legacy_row(store, limit_cents=1, token_limit=INT64_MAX, action_limit=2)
        client.get(f"/caps/{AGENT}")
        legacy_row(store, limit_cents=1, token_limit=INT64_MAX - 1, action_limit=2)
        client.get(f"/caps/{AGENT}")
        legacy_row(store, limit_cents=1, token_limit=INT64_MAX - 1, action_limit=3)
        client.get(f"/caps/{AGENT}")
    assert len(_warnings(caplog)) == 3        # each rewrite changed one column of the row, so each warns again
