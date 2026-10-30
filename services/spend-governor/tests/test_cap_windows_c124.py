"""C-124 (reviewer R-08 F-R08-1, MEDIUM, a money limit): the cap WINDOW was not pinned at all. All six mutants
of ``window_start`` survived the 101-test suite, so a monthly or total cap could have started counting from
midnight (a fail-open on a spend limit) with every test green.

Pure: ``window_start`` for daily, monthly and total. End to end: a frozen clock and the real app show that spend
recorded in an earlier day counts against a monthly and a total cap but not against a daily one, and spend in an
earlier month counts only against a total cap."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore, window_start

UTC = timezone.utc
AGENT = "window-agent"


def _t(y, mo, d, h=12, mi=0):
    return datetime(y, mo, d, h, mi, 0, tzinfo=UTC)


@pytest.mark.parametrize("now,want", [
    (_t(2026, 10, 29, 0, 0), "2026-10-29T00:00:00+00:00"),            # exactly midnight
    (_t(2026, 10, 29, 23, 59), "2026-10-29T00:00:00+00:00"),
    (_t(2026, 1, 1, 5, 5), "2026-01-01T00:00:00+00:00"),
    (_t(2026, 12, 31, 23, 59), "2026-12-31T00:00:00+00:00"),
])
def test_daily_starts_at_midnight_of_the_same_utc_day(now, want):
    assert window_start("daily", now) == want


@pytest.mark.parametrize("now,want", [
    (_t(2026, 10, 1, 0, 0), "2026-10-01T00:00:00+00:00"),
    (_t(2026, 10, 29, 23, 59), "2026-10-01T00:00:00+00:00"),
    (_t(2026, 2, 28, 12), "2026-02-01T00:00:00+00:00"),
    (_t(2026, 12, 31, 23, 59), "2026-12-01T00:00:00+00:00"),
])
def test_monthly_starts_on_the_first_of_the_same_month(now, want):
    assert window_start("monthly", now) == want


@pytest.mark.parametrize("now", [_t(1971, 1, 1), _t(2026, 10, 29), _t(2099, 12, 31)])
def test_total_never_resets(now):
    assert window_start("total", now) == "1970-01-01T00:00:00+00:00"


def test_the_three_windows_are_distinct_on_an_ordinary_day():
    now = _t(2026, 10, 29, 15, 30)
    starts = {p: window_start(p, now) for p in ("daily", "monthly", "total")}
    assert len(set(starts.values())) == 3
    assert starts["total"] < starts["monthly"] < starts["daily"]


def test_an_unknown_period_falls_back_to_the_widest_window_never_a_narrower_one():
    """Documented fallthrough: anything that is not daily or monthly counts as total (fail toward counting more)."""
    assert window_start("weekly", _t(2026, 10, 29)) == window_start("total", _t(2026, 10, 29))


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture()
def world(tmp_path):
    clock = _Clock(_t(2026, 10, 10, 12))
    client = TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3"), clock=clock))

    def cap(period):
        body = {"agent_id": AGENT, "currency": "USD", "limit_cents": 100_000, "period": period,
                "escalate_at_pct": 80}
        assert client.put(f"/caps/{AGENT}", json=body).status_code == 200

    def spend(cents):
        r = client.post("/spend", json={"agent_id": AGENT, "cents": cents, "tokens": 0, "actions": 0})
        assert r.status_code in (200, 201), r.text

    def spent():
        return client.get(f"/status/{AGENT}").json()["spent_cents"]

    return clock, cap, spend, spent


def test_yesterdays_spend_does_not_count_against_a_daily_cap(world):
    clock, cap, spend, spent = world
    cap("daily")
    clock.now = _t(2026, 10, 9, 23, 59)
    spend(500)
    clock.now = _t(2026, 10, 10, 0, 1)
    assert spent() == 0
    spend(70)
    assert spent() == 70


def test_yesterdays_spend_still_counts_against_a_monthly_cap_but_last_months_does_not(world):
    clock, cap, spend, spent = world
    cap("monthly")
    clock.now = _t(2026, 9, 30, 23, 59)
    spend(900)                                          # last month
    clock.now = _t(2026, 10, 9, 23, 59)
    spend(500)                                          # earlier this month
    clock.now = _t(2026, 10, 10, 0, 1)
    assert spent() == 500                               # not 0 (a daily window), not 1400 (a total window)


def test_every_earlier_spend_counts_against_a_total_cap(world):
    clock, cap, spend, spent = world
    cap("total")
    clock.now = _t(2025, 1, 5)
    spend(300)
    clock.now = _t(2026, 9, 30, 23, 59)
    spend(900)
    clock.now = _t(2026, 10, 10, 0, 1)
    assert spent() == 1200


# --- reviewer R-08 LOW findings, behaviour already correct, never pinned ---------------------------------------

from pydantic import ValidationError  # noqa: E402

from spend_governor.core import Escalation, SpendCapConfig, SpendState, evaluate  # noqa: E402


def test_a_cap_with_no_limit_is_refused_at_the_model_and_over_http_and_nothing_is_stored(tmp_path):
    """F-R08-2: _at_least_one_limit. Probed: PUT /caps with an empty body answers 422, not an accepted cap
    that evaluate would call OK forever."""
    with pytest.raises(ValidationError):
        SpendCapConfig(agent_id=AGENT, period="daily")
    client = TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3")))
    for body in ({"agent_id": AGENT, "period": "daily"},
                 {"agent_id": AGENT, "limit_cents": None, "token_limit": None, "action_limit": None}):
        assert client.put(f"/caps/{AGENT}", json=body).status_code == 422
    assert client.get(f"/caps/{AGENT}").status_code == 404


def test_an_unresolved_escalation_keeps_the_state_at_escalate_below_every_threshold():
    """F-R08-3: evaluate's `if open_escalations`."""
    cap = SpendCapConfig(agent_id=AGENT, limit_cents=1000, period="daily", escalate_at_pct=80)
    assert evaluate(cap, 0, 0, 0, 0)[0] is SpendState.OK
    state, detail = evaluate(cap, 0, 0, 0, 2)
    assert state is SpendState.ESCALATE and "2 unresolved" in detail
    assert evaluate(cap, 1000, 0, 0, 2)[0] is SpendState.BLOCK        # a cap still beats an open escalation


def test_opening_an_escalation_that_is_already_resolved_is_refused(tmp_path):
    """F-R08-3: add_escalation_if_none_open raises on resolved=True (it opens, it does not record history)."""
    store = GovernorStore(tmp_path / "s.sqlite3")
    esc = Escalation(escalation_id="e1", agent_id=AGENT, ts="2026-10-29T00:00:00+00:00", kind="cents",
                     spent=900, limit=1000, pct=90, resolved=True, resolved_by="don")
    with pytest.raises(ValueError, match="resolved=True"):
        store.add_escalation_if_none_open(esc)


@pytest.mark.parametrize("route,body", [
    ("/caps/other-agent", {"agent_id": AGENT, "limit_cents": 100, "period": "daily"}),
    ("/policies/other-agent", {"agent_id": AGENT}),
])
def test_path_and_body_agent_ids_must_match(tmp_path, route, body):
    """F-R08-4: the 422 on PUT /caps/{id} and PUT /policies/{id}; a body naming another agent must not
    configure THAT agent through this agent's path."""
    client = TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3")))
    r = client.put(route, json=body)
    assert r.status_code == 422 and "must match" in r.text
    assert client.get(f"/caps/{AGENT}").status_code == 404           # nothing was written for the body's agent
