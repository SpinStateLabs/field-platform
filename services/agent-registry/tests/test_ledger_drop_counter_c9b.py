"""A refused or lost registry.* ledger append is counted and logged, never silent.

The registry change itself still stands (best-effort audit); the gap shows in
/health as `ledger_appends_dropped` and in the log as the exception TYPE only.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

CANARY = "CANARY-https://secret.example/path"


class _Boom:
    def append(self, event_type, payload=None, agent_id=None):
        raise RuntimeError(CANARY)


class _Ok:
    def __init__(self):
        self.seen = []

    def append(self, event_type, payload=None, agent_id=None):
        self.seen.append(event_type)


def _register(client, agent_id="a-1"):
    return client.post("/agents", json={
        "agent_id": agent_id, "name": "A", "owner": "Owner", "domain": "finance"})


def test_a_failing_ledger_is_counted_and_the_change_stands(tmp_path, caplog):
    client = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"),
                                   ledger=_Boom()))
    assert client.get("/health").json()["ledger_appends_dropped"] == 0
    with caplog.at_level(logging.WARNING, logger="agent_registry.api"):
        assert _register(client).status_code in (200, 201)
        client.patch("/agents/a-1", json={"owner": "New Owner"})
    assert client.get("/agents/a-1").json()["owner"] == "New Owner"
    assert client.get("/health").json()["ledger_appends_dropped"] == 2
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in text and "registry.registered" in text
    assert CANARY not in text and "secret.example" not in text


def test_a_working_ledger_counts_zero(tmp_path):
    ledger = _Ok()
    client = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"),
                                   ledger=ledger))
    _register(client)
    assert ledger.seen and client.get("/health").json()["ledger_appends_dropped"] == 0


def test_no_ledger_wired_counts_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    client = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    _register(client)
    assert client.get("/health").json()["ledger_appends_dropped"] == 0
