"""C-246 (reviewer C-230): amount bounds, an overflow-safe window sum, the three side-path gaps
(F-C230 gaps: `/status` of an uncapped agent, the sentinel default note, the `spend.cap_reached` row at
BLOCK) and the dropped-audit counter (F-C230-2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import MAX_AMOUNT, GovernorStore
from spend_governor.usage import UsageRecord

AGENT = "invoicing-agent"
INT64_MAX = 2**63 - 1


class Ledger:
    def __init__(self, fail=False):
        self.fail = fail
        self.notes = []

    def append(self, event_type, payload=None, agent_id=None):
        if self.fail:
            raise ConnectionError("ledger down")
        self.notes.append((event_type, payload or {}, agent_id))

    def of(self, event_type):
        return [p for t, p, _ in self.notes if t == event_type]


@pytest.fixture()
def store(tmp_path):
    return GovernorStore(tmp_path / "spend.sqlite3")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def set_cap(c, **over):
    body = {"agent_id": AGENT, "currency": "USD", "limit_cents": 100, "period": "daily",
            "escalate_at_pct": 80}
    body.update(over)
    assert c.put(f"/caps/{AGENT}", json=body).status_code == 200


def post(c, **body):
    return c.post("/spend", json={"agent_id": AGENT, **body})


# --- F-C230-1: bounds --------------------------------------------------------------------


@pytest.mark.parametrize("field", ["cents", "tokens", "actions"])
def test_the_maximum_is_accepted_and_one_above_it_is_422(client, field):
    set_cap(client, limit_cents=None, token_limit=MAX_AMOUNT, action_limit=MAX_AMOUNT) \
        if field != "cents" else set_cap(client, limit_cents=MAX_AMOUNT)
    assert post(client, **{field: MAX_AMOUNT}).status_code == 201
    assert post(client, **{field: MAX_AMOUNT + 1}).status_code == 422


@pytest.mark.parametrize("value", [INT64_MAX, 2**63, 10**19, 2**64])
def test_the_reviewers_probe_inputs_never_answer_500(client, value):
    set_cap(client)
    assert post(client, cents=value).status_code == 422
    assert post(client, tokens=value).status_code == 422
    assert post(client, actions=value).status_code == 422
    assert client.get(f"/status/{AGENT}").status_code == 200   # nothing was recorded


def test_a_negative_amount_is_422(client):
    set_cap(client)
    assert post(client, cents=-1).status_code == 422


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cache_read_tokens"])
def test_a_usage_post_above_the_maximum_is_422(client, field):
    set_cap(client)
    body = {"agent_id": AGENT, "model": "claude-opus-4-8", field: MAX_AMOUNT + 1}
    assert client.post("/usage", json=body).status_code == 422


@pytest.mark.parametrize("field", ["limit_cents", "token_limit", "action_limit"])
def test_a_cap_limit_above_the_maximum_is_422(client, field):
    body = {"agent_id": AGENT, field: MAX_AMOUNT + 1}
    assert client.put(f"/caps/{AGENT}", json=body).status_code == 422
    assert client.put(f"/caps/{AGENT}", json={**body, field: MAX_AMOUNT}).status_code == 200


# --- F-C230-1: the window sum does not overflow ------------------------------------------


def test_two_near_maximal_rows_do_not_break_status(store, client):
    """Rows already in the store (before the bound existed, or written by a caller of the store)
    must not make /status answer 500: the sum is exact in Python ints, not a SQLite int64 SUM."""
    set_cap(client)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for _ in range(2):
        store.record(AGENT, INT64_MAX, INT64_MAX, INT64_MAX, None, now)
    r = client.get(f"/status/{AGENT}")
    assert r.status_code == 200
    body = r.json()
    assert body["spent_cents"] == 2 * INT64_MAX
    assert body["spent_tokens"] == 2 * INT64_MAX
    assert body["spent_actions"] == 2 * INT64_MAX
    assert body["state"] == "BLOCK"
    assert store.totals_since(AGENT, "1970-01-01T00:00:00+00:00") == (2 * INT64_MAX,) * 3


def test_usage_totals_are_exact_across_large_rows(store):
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    for i in range(2):
        store.record_usage(UsageRecord(
            event_id=f"u{i}", agent_id=AGENT, ts=ts, model="claude-opus-4-8",
            input_tokens=INT64_MAX, output_tokens=INT64_MAX, cost_units=INT64_MAX, priced=True))
    t_in, t_out, cost, rows = store.usage_totals_since(AGENT, "1970-01-01T00:00:00+00:00")
    assert (t_in, t_out, cost) == (2 * INT64_MAX,) * 3
    assert rows[0]["i"] == rows[0]["o"] == rows[0]["c"] == 2 * INT64_MAX


def test_action_counts_are_exact_across_large_rows(store):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for _ in range(2):
        store.record(AGENT, 0, 0, INT64_MAX, None, now, action="x", source="self")
    assert store.action_counts_since(AGENT, "1970-01-01T00:00:00+00:00") == [
        ("x", "self", 2 * INT64_MAX)]


# --- the three side-path gaps ------------------------------------------------------------


def test_status_of_an_uncapped_agent_is_404_with_its_text(client):
    r = client.get("/status/nobody")
    assert r.status_code == 404
    assert r.json()["detail"] == "no spend cap configured for 'nobody'"


@pytest.mark.parametrize(("shadowed", "note"), [
    (False, "sentinel-metered ALLOW"), (True, "sentinel-metered ALLOW (log-only shadow)")])
def test_a_sentinel_row_without_a_note_gets_the_default_text(store, client, shadowed, note):
    set_cap(client)
    assert post(client, actions=1, action="draft", source="sentinel", shadowed=shadowed
                ).status_code == 201
    [row] = store._conn.execute("SELECT note FROM spend").fetchall()
    assert row["note"] == note


def test_a_caller_note_on_a_sentinel_row_is_kept(store, client):
    set_cap(client)
    assert post(client, actions=1, action="draft", source="sentinel", note="mine").status_code == 201
    assert store._conn.execute("SELECT note FROM spend").fetchone()["note"] == "mine"


def test_block_writes_cap_reached_and_opens_no_escalation(tmp_path):
    ledger = Ledger()
    c = TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3"), ledger=ledger))
    set_cap(c)
    assert post(c, cents=80).json()["state"] == "ESCALATE"        # the 80% crossing
    assert post(c, cents=40).json()["state"] == "BLOCK"
    [reached] = ledger.of("spend.cap_reached")
    assert reached["detail"].startswith("cents cap reached")
    assert len(ledger.of("spend.escalate")) == 1                  # only the 80% crossing
    assert len(c.get("/escalations").json()) == 1


# --- F-C230-2: dropped audit appends are counted -----------------------------------------


def test_health_counts_ledger_appends_that_failed(tmp_path, caplog):
    ledger = Ledger(fail=True)
    c = TestClient(create_app(store=GovernorStore(tmp_path / "s.sqlite3"), ledger=ledger))
    set_cap(c)
    assert c.get("/health").json()["ledger_appends_dropped"] == 0
    with caplog.at_level("WARNING"):
        assert post(c, cents=10).status_code == 201               # the spend is kept
    assert c.get("/health").json()["ledger_appends_dropped"] == 1  # spend.recorded
    assert c.get(f"/status/{AGENT}").json()["spent_cents"] == 10
    assert "ledger append spend.recorded dropped (ConnectionError)" in caplog.text
    assert post(c, cents=100).status_code == 201                  # recorded + escalate/cap_reached
    assert c.get("/health").json()["ledger_appends_dropped"] >= 3


def test_health_counter_is_zero_without_a_ledger_and_when_appends_succeed(tmp_path, client):
    set_cap(client)
    post(client, cents=10)
    assert client.get("/health").json()["ledger_appends_dropped"] == 0
    ok = TestClient(create_app(store=GovernorStore(tmp_path / "t.sqlite3"), ledger=Ledger()))
    set_cap(ok)
    post(ok, cents=10)
    assert ok.get("/health").json()["ledger_appends_dropped"] == 0
