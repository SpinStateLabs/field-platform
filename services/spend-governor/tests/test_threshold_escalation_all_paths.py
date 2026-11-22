"""S12-9: the threshold escalation opens on every route that can cross it
(POST /spend and POST /usage) and once per crossed dimension, never twice."""

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import GovernorStore

AGENT = "esc-agent"


class RecordingLedger:
    def __init__(self):
        self.notes = []

    def append(self, event_type, payload=None, agent_id=None):
        self.notes.append((event_type, payload or {}, agent_id))

    def of(self, event_type):
        return [p for t, p, a in self.notes if t == event_type and a == AGENT]


@pytest.fixture()
def api(tmp_path):
    ledger = RecordingLedger()
    app = create_app(store=GovernorStore(tmp_path / "spend.sqlite3"), ledger=ledger)
    return TestClient(app), ledger


def put_cap(client, **limits):
    body = {"agent_id": AGENT, "period": "daily", "escalate_at_pct": 80, **limits}
    assert client.put(f"/caps/{AGENT}", json=body).status_code == 200


def open_kinds(client):
    rows = client.get("/escalations", params={"agent_id": AGENT}).json()
    return sorted(e["kind"] for e in rows if not e.get("resolved_at"))


def test_usage_only_crossing_opens_a_cents_escalation_once(api):
    client, ledger = api
    put_cap(client, limit_cents=1000)  # escalate at $8
    r = client.post("/usage", json={"agent_id": AGENT, "model": "claude-opus-4-8",
                                    "input_tokens": 0, "output_tokens": 340_000})
    assert r.json()["status"]["state"] == "ESCALATE"
    assert open_kinds(client) == ["cents"]
    assert len(ledger.of("spend.escalate")) == 1
    # a second usage row while still over the threshold opens nothing new
    client.post("/usage", json={"agent_id": AGENT, "model": "claude-opus-4-8",
                                "input_tokens": 0, "output_tokens": 1000})
    assert open_kinds(client) == ["cents"]
    assert len(ledger.of("spend.escalate")) == 1


def test_one_spend_crossing_two_limits_opens_one_escalation_each(api):
    client, ledger = api
    put_cap(client, limit_cents=1000, token_limit=1000)
    r = client.post("/spend", json={"agent_id": AGENT, "cents": 900, "tokens": 900})
    assert r.status_code in (200, 201)
    assert r.json()["state"] == "ESCALATE"
    assert open_kinds(client) == ["cents", "tokens"]
    assert sorted(p["kind"] for p in ledger.of("spend.escalate")) == ["cents", "tokens"]
    # a second call opens no duplicate
    client.post("/spend", json={"agent_id": AGENT, "cents": 1, "tokens": 1})
    assert open_kinds(client) == ["cents", "tokens"]
    assert len(ledger.of("spend.escalate")) == 2
