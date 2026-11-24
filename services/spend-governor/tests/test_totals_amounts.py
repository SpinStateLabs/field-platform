"""S3-8: GET /totals/{agent}?since= amounts and the inclusive boundary, pinned. The only earlier /totals tests
(test_reaudit_c616.py) check status codes and the UTC form of `since`, never a number.

Rows are written through the store with explicit timestamps (no clock dependence). `since` is inclusive (`ts >= since`):
a row exactly at it counts, one microsecond earlier does not. spent_cents = recorded cents + floor(priced cost units
/ 100_000), floored once on the SUM (not per row); unpriced usage contributes nothing; /status agrees for the same
window start."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore
from spend_governor.usage import UsageRecord

AGENT = "totals-agent"
NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
S = NOW                                     # the `since` instant
JUST_BEFORE = S - timedelta(microseconds=1)
CENT = 100_000                              # cost units per cent


@pytest.fixture()
def store(tmp_path):
    s = GovernorStore(tmp_path / "spend.sqlite3")
    yield s
    s.close()


@pytest.fixture()
def client(store):
    c = TestClient(create_app(store=store, clock=lambda: NOW + timedelta(hours=1)))
    r = c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 1_000_000, "period": "daily",
                                      "escalate_at_pct": 80, "currency": "EUR"})
    assert r.status_code == 200, r.text
    return c


def spend(store, cents, ts):
    store.record(AGENT, cents, 0, 0, None, ts)


def usage(store, ts, cost_units, model="m-priced"):
    store.record_usage(UsageRecord(
        event_id=str(uuid.uuid4()), agent_id=AGENT, ts=ts.isoformat(), model=model,
        input_tokens=10, output_tokens=5, cost_units=cost_units, priced=cost_units is not None))


def totals(client, since):
    r = client.get(f"/totals/{AGENT}", params={"since": since})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_amounts_are_recorded_cents_plus_the_priced_token_cost(store, client):
    spend(store, 100, S)
    spend(store, 20, S + timedelta(minutes=5))
    usage(store, S + timedelta(minutes=1), 250_000)
    body = totals(client, S.isoformat())
    assert body["token_cost_units"] == 250_000
    assert body["spent_cents"] == 120 + 2          # floor(250_000 / 100_000) = 2


def test_cost_units_are_floored_once_on_the_sum_not_per_row(store, client):
    usage(store, S, 60_000)
    usage(store, S + timedelta(seconds=1), 60_000)
    body = totals(client, S.isoformat())
    assert body["token_cost_units"] == 120_000
    assert body["spent_cents"] == 1                # per-row flooring would give 0


def test_a_row_exactly_at_since_is_included_and_one_microsecond_earlier_is_not(store, client):
    spend(store, 100, S)
    spend(store, 7, JUST_BEFORE)
    usage(store, S, 3 * CENT)
    usage(store, JUST_BEFORE, 40 * CENT)
    body = totals(client, S.isoformat())
    assert (body["spent_cents"], body["token_cost_units"]) == (100 + 3, 3 * CENT)
    wider = totals(client, JUST_BEFORE.isoformat())
    assert (wider["spent_cents"], wider["token_cost_units"]) == (107 + 43, 43 * CENT)


@pytest.mark.parametrize("since", ["2026-10-30T17:00:00+05:00", "2026-10-30T07:00:00-05:00",
                                   "2026-10-30T12:00:00", "2026-10-30T12:00:00Z"])
def test_an_offset_since_selects_the_same_rows_as_its_utc_equivalent(store, client, since):
    spend(store, 100, S)
    spend(store, 7, JUST_BEFORE)
    body = totals(client, since)
    assert body["since"] == S.isoformat()
    assert body["spent_cents"] == 100


def test_unpriced_usage_contributes_nothing(store, client):
    spend(store, 5, S)
    usage(store, S, None, model="m-unpriced")
    body = totals(client, S.isoformat())
    assert (body["spent_cents"], body["token_cost_units"]) == (5, 0)


def test_currency_echoes_the_caps_currency(client):
    assert totals(client, S.isoformat())["currency"] == "EUR"


def test_an_empty_window_is_zero(client):
    body = totals(client, S.isoformat())
    assert (body["spent_cents"], body["token_cost_units"]) == (0, 0)


def test_totals_and_status_give_one_answer_for_the_same_window_start(store, client):
    day_start = datetime(2026, 10, 30, 0, 0, 0, tzinfo=timezone.utc)   # the daily window /status uses at NOW+1h
    spend(store, 100, day_start)
    spend(store, 9, day_start - timedelta(microseconds=1))             # yesterday: in neither
    usage(store, day_start + timedelta(hours=3), 450_000)
    usage(store, day_start - timedelta(hours=3), 900_000)
    t = totals(client, day_start.isoformat())
    st = client.get(f"/status/{AGENT}").json()
    assert t["spent_cents"] == st["spent_cents"] == 100 + 4
