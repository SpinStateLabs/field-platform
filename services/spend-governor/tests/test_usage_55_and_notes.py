"""Governor side of P30: the 5.5 generation is priced at /usage (no
``usage:unpriced``), an absent model still fails closed, and the caller's
note is on the ``usage.recorded`` / ``spend.recorded`` ledger row."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "approver-metered-agent"


class FakeLedger:
    def __init__(self):
        self.events: list[tuple[str, dict, str]] = []

    def append(self, event_type, payload=None, agent_id=None, **_):
        self.events.append((event_type, dict(payload or {}), agent_id))

    def of(self, event_type):
        return [p for t, p, _ in self.events if t == event_type]


@pytest.fixture()
def ledger():
    return FakeLedger()


@pytest.fixture()
def client(tmp_path, ledger):
    c = TestClient(create_app(store=GovernorStore(tmp_path / "spend.sqlite3"), ledger=ledger))
    r = c.put(f"/caps/{AGENT}", json={"agent_id": AGENT, "limit_cents": 50_000,
                                      "period": "daily", "escalate_at_pct": 80})
    assert r.status_code == 200
    return c


def _usage(client, model, i, o, cache=0, note=None):
    body = {"agent_id": AGENT, "model": model, "input_tokens": i,
            "output_tokens": o, "cache_read_tokens": cache}
    if note is not None:
        body["note"] = note
    r = client.post("/usage", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("model, expected_units", [
    # 1,000 input + 1,000 output + 1,000 cache-read tokens, exact units
    ("claude-opus-5-5", 1_000 * 40 + 1_000 * 200 + 1_000 * 2),
    ("claude-sonnet-5-5", 1_000 * 20 + 1_000 * 100 + 1_000 * 1),
    ("claude-haiku-5-5", 1_000 * 5 + 1_000 * 25 + 1_000 * 1),
    ("claude-fable-5-1", 1_000 * 100 + 1_000 * 500 + 1_000 * 3),
    ("claude-mythos-5-1", 1_000 * 100 + 1_000 * 500 + 1_000 * 3),
    ("claude-sonnet-5-5-20261001", 121_000),   # dated id prices as its base
])
def test_5_5_generation_is_priced_with_no_unpriced_signal(client, ledger, model, expected_units):
    body = _usage(client, model, 1_000, 1_000, 1_000)
    assert body["record"]["priced"] is True
    assert body["record"]["cost_units"] == expected_units
    assert body["rogue"] == []
    assert ledger.of("usage.unpriced") == []
    (row,) = ledger.of("usage.recorded")
    assert row["cost_units"] == expected_units
    assert row["price_book"] == "anthropic-list-2026-10-27"
    esc = client.get("/escalations")
    assert esc.status_code == 200
    assert [e["kind"] for e in esc.json() if e["kind"].startswith("usage:")] == []


def test_a_model_absent_from_the_book_still_opens_usage_unpriced(client, ledger):
    body = _usage(client, "claude-sonnet-9-9", 1_000, 1_000)
    assert body["record"]["priced"] is False
    assert body["record"]["cost_units"] is None
    assert [f["kind"] for f in body["rogue"]] == ["unpriced"]
    (flag,) = ledger.of("usage.unpriced")
    assert flag["model"] == "claude-sonnet-9-9"
    kinds = [e["kind"] for e in client.get("/escalations").json()]
    assert kinds == ["usage:unpriced"]
    assert ledger.of("usage.recorded")[0]["cost_units"] is None


def test_the_approver_note_is_on_the_usage_ledger_row(client, ledger):
    _usage(client, "claude-sonnet-5-5", 10, 10,
           note="console session sesn_01LYJ1mZ5RtNnD7hmAoyVY6V")
    (row,) = ledger.of("usage.recorded")
    assert row["note"] == "console session sesn_01LYJ1mZ5RtNnD7hmAoyVY6V"


def test_the_usage_note_is_cleaned_and_absent_when_not_sent(client, ledger):
    _usage(client, "claude-opus-5-5", 1, 1, note="  a\nb  " + "z" * 400)
    _usage(client, "claude-opus-5-5", 1, 1)
    _usage(client, "claude-opus-5-5", 1, 1, note="   ")
    first, second, third = ledger.of("usage.recorded")
    assert first["note"] == ("a b " + "z" * 400)[:300]
    assert "note" not in second
    assert "note" not in third


def test_a_self_reported_spend_note_is_on_the_spend_ledger_row(client, ledger):
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 5, "note": "console session sesn_9"})
    assert r.status_code == 201, r.text
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 5})
    assert r.status_code == 201, r.text
    with_note, without = ledger.of("spend.recorded")
    assert with_note["note"] == "console session sesn_9"
    assert "note" not in without
