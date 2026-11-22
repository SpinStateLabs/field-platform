"""Backlog B9 (don.reviewer 1192 N1): ``PUT /caps/{agent_id}`` re-checks the same bounds as the other write paths.
The S2-2 text bounds (agent_id 128, labels 200) now apply to the cap body, and the numeric bounds of the cap model
still hold on this route. Boundary accepted, one over refused with a 422 that never repeats the text, and nothing is
stored on a refusal. Every value is made up."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import MAX_ID_LEN, MAX_LABEL_LEN, create_app
from spend_governor.core import MAX_AMOUNT, GovernorStore

AGENT = "invoicing-agent"


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def _cap(agent=AGENT, **over):
    return {"agent_id": agent, "limit_cents": 50_000, "period": "daily", "escalate_at_pct": 80, **over}


def test_the_bounds_are_the_s2_2_numbers():
    assert (MAX_ID_LEN, MAX_LABEL_LEN) == (128, 200)


def test_agent_id_at_its_limit_is_accepted_and_one_over_is_refused(client, store):
    ok = "a" * MAX_ID_LEN
    assert client.put(f"/caps/{ok}", json=_cap(ok)).status_code == 200
    over = "b" * (MAX_ID_LEN + 1)
    r = client.put(f"/caps/{over}", json=_cap(over))
    assert r.status_code == 422 and over not in r.text
    assert store.get_cap(over) is None


@pytest.mark.parametrize("field", ["currency", "on_breach"])
def test_a_label_at_its_limit_is_accepted_and_one_over_is_refused(client, store, field):
    r = client.put(f"/caps/{AGENT}", json=_cap(**{field: "a" * MAX_LABEL_LEN}))
    assert r.status_code == 200, r.text
    assert getattr(store.get_cap(AGENT), field) == "a" * MAX_LABEL_LEN
    over = "b" * (MAX_LABEL_LEN + 1)
    r = client.put(f"/caps/{AGENT}", json=_cap(**{field: over}))
    assert r.status_code == 422 and over not in r.text
    assert getattr(store.get_cap(AGENT), field) == "a" * MAX_LABEL_LEN     # the refused write changed nothing


@pytest.mark.parametrize("field,value", [
    ("limit_cents", 0), ("limit_cents", -1), ("limit_cents", MAX_AMOUNT + 1),
    ("token_limit", 0), ("token_limit", MAX_AMOUNT + 1),
    ("action_limit", 0), ("action_limit", MAX_AMOUNT + 1),
    ("escalate_at_pct", 0), ("escalate_at_pct", 101),
    ("period", "per-run"), ("period", "weekly"),
])
def test_the_numeric_and_period_bounds_still_hold_on_put(client, store, field, value):
    r = client.put(f"/caps/{AGENT}", json=_cap(**{field: value}))
    assert r.status_code == 422
    assert store.get_cap(AGENT) is None


def test_a_put_with_no_limit_is_refused(client, store):
    r = client.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "period": "daily"})
    assert r.status_code == 422 and store.get_cap(AGENT) is None


def test_the_limits_at_max_amount_are_accepted(client, store):
    r = client.put(f"/caps/{AGENT}", json=_cap(limit_cents=MAX_AMOUNT, token_limit=MAX_AMOUNT,
                                                action_limit=MAX_AMOUNT))
    assert r.status_code == 200, r.text
    assert store.get_cap(AGENT).limit_cents == MAX_AMOUNT


def test_an_unknown_field_is_still_refused(client, store):
    r = client.put(f"/caps/{AGENT}", json=_cap(surprise=1))
    assert r.status_code == 422 and store.get_cap(AGENT) is None


def test_get_caps_still_reads_a_row_stored_before_the_bound(client, store):
    """The bound is on the request only: an over-long row already in the store still reads back."""
    from spend_governor.core import SpendCapConfig
    long = "c" * (MAX_LABEL_LEN + 50)
    store.set_cap(SpendCapConfig(agent_id=AGENT, limit_cents=100, on_breach=long))
    r = client.get(f"/caps/{AGENT}")
    assert r.status_code == 200 and r.json()["on_breach"] == long
