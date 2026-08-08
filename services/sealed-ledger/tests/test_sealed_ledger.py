"""sealed-ledger tests, incl. the adversarial on-disk tamper case."""

import json

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore


@pytest.fixture()
def store(tmp_path):
    return LedgerStore(tmp_path / "events.jsonl")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def test_append_links_chain(store):
    e1 = store.append("action", {"n": 1}, agent_id="a1")
    e2 = store.append("action", {"n": 2}, agent_id="a1")
    assert e2.prev_hash == e1.hash
    assert store.verify().ok


def test_head_recovered_after_reopen(store, tmp_path):
    store.append("action", {"n": 1})
    last = store.append("action", {"n": 2})
    reopened = LedgerStore(tmp_path / "events.jsonl")
    assert reopened.head_hash == last.hash
    next_event = reopened.append("action", {"n": 3})
    assert next_event.prev_hash == last.hash
    assert reopened.verify().ok


def test_api_append_list_verify(client):
    r = client.post(
        "/events",
        json={"event_type": "token.mint", "agent_id": "a1", "payload": {"scope": ["x"]}},
    )
    assert r.status_code == 201
    client.post("/events", json={"event_type": "action", "agent_id": "a2"})

    both = client.get("/events").json()
    assert len(both) == 2
    only_a1 = client.get("/events", params={"agent_id": "a1"}).json()
    assert [e["event_type"] for e in only_a1] == ["token.mint"]

    verify = client.get("/verify").json()
    assert verify["ok"] is True
    assert verify["length"] == 2

    health = client.get("/health").json()
    assert health["ok"] and health["event_count"] == 2


def test_adversarial_on_disk_mutation_detected(store, tmp_path):
    """Adversarial case from the spec: mutate a middle record, prove detection."""
    for i in range(5):
        store.append("spend", {"amount": 100 + i}, agent_id="fin-agent")
    ledger_file = tmp_path / "events.jsonl"
    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[2])
    record["payload"]["amount"] = 1  # the quiet $1 edit an auditor fears
    lines[2] = json.dumps(record)
    ledger_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = LedgerStore(ledger_file).verify()
    assert not result.ok
    assert result.first_break_index == 2
    assert "mutated" in result.reason


def test_adversarial_deleted_line_detected(store, tmp_path):
    """Deleting a middle record breaks the next link."""
    for i in range(4):
        store.append("action", {"n": i})
    ledger_file = tmp_path / "events.jsonl"
    lines = ledger_file.read_text(encoding="utf-8").splitlines()
    del lines[1]
    ledger_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = LedgerStore(ledger_file).verify()
    assert not result.ok
    assert result.first_break_index == 1
    assert "link break" in result.reason


def test_export_summary_counts(client, store, tmp_path):
    client.post("/events", json={"event_type": "action", "agent_id": "a1"})
    client.post("/events", json={"event_type": "action", "agent_id": "a1"})
    client.post("/events", json={"event_type": "block", "agent_id": "a2"})

    r = client.post("/export", params={"out_dir": str(tmp_path / "exports")})
    assert r.status_code == 200
    summary = r.json()
    assert summary["event_count"] == 3
    assert summary["event_types"] == {"action": 2, "block": 1}
    assert summary["agents"] == {"a1": 2, "a2": 1}
    assert summary["verification"]["ok"] is True

    exported = (tmp_path / "exports" / summary["path"].split("\\")[-1].split("/")[-1])
    assert exported.exists()
    assert len(exported.read_text(encoding="utf-8").splitlines()) == 3
