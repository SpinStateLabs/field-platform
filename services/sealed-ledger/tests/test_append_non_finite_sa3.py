"""POST /events with NaN/Infinity in the payload must be a 422 and append nothing.
Before: 201, then GET /verify said "record was mutated" (scout S-A3)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

HDR = {"content-type": "application/json"}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_non_finite_payload_is_422_and_nothing_is_appended(client, token):
    body = '{"event_type":"x","payload":{"outer":{"v":%s}}}' % token
    r = client.post("/events", content=body, headers=HDR)
    assert r.status_code == 422, r.text
    assert "outer" not in r.text and token not in r.text
    assert client.get("/events").json() == []
    assert client.get("/verify").json()["ok"] is True


def test_a_finite_payload_still_appends_and_verifies(client):
    r = client.post("/events", content='{"event_type":"x","payload":{"v":1.5}}', headers=HDR)
    assert r.status_code == 201
    v = client.get("/verify").json()
    assert v["ok"] is True and v["length"] == 1
