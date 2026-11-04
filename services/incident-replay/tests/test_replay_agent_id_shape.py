"""S5-15: ``ReplayRequest.agent_id`` is one printable line of at most 200 characters, and an id the registry could never
hold is not put into the registry's URL path. A ledger-only id (the federation broker's 'Org/agent') still replays."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_core.clients import LedgerClient, RegistryClient
from incident_replay.api import create_app
from incident_replay.engine import AGENT_ID_MAX, LedgerQueryClient, ReplayEngine, TokenQueryClient
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore

MARK = "MADE-UP-MARKER-0123456789"
WINDOW = {"since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}


class SpyRegistry(RegistryClient):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ids: list[str] = []

    def get_agent(self, agent_id):
        self.ids.append(agent_id)
        return super().get_agent(agent_id)


@pytest.fixture()
def rig(tmp_path):
    store = LedgerStore(tmp_path / "events.jsonl")
    ledger = TestClient(create_ledger_app(store=store))
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "t.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")))
    spy = SpyRegistry(client=registry, base_url="http://t")
    client = TestClient(create_app(engine=ReplayEngine(
        ledger=LedgerQueryClient(client=ledger, base_url="http://t"), registry=spy,
        delegation=TokenQueryClient(client=delegation, base_url="http://t"))))
    return client, spy, ledger


def replay(client, agent_id, path="/replay"):
    return client.post(path, json={"agent_id": agent_id, **WINDOW})


@pytest.mark.parametrize("bad", ["x/../../health", "a?b=1", "a/b", "a#f", "A", "é", " a", "a b", "a%2Fb"])
def test_ids_the_registry_cannot_hold_never_reach_its_url_path(rig, bad):
    client, spy, _ = rig
    r = replay(client, bad)
    assert r.status_code == 200, r.text
    assert spy.ids == []
    assert r.json()["agent_record"] is None


def test_a_ledger_only_id_still_replays_its_trail(rig):
    client, spy, ledger = rig
    ledger.post("/events", json={"event_type": "federation.block", "agent_id": "Acme Corp/billing-agent",
                                 "payload": {"clause_id": "F.peer"}})
    pm = replay(client, "Acme Corp/billing-agent").json()
    assert [t["event_type"] for t in pm["timeline"]] == ["federation.block"]
    assert spy.ids == []


@pytest.mark.parametrize("path", ["/replay", "/replay/markdown"])
@pytest.mark.parametrize("bad", ["", "   ", "\t", MARK + "\n# injected heading", MARK + "\x00", MARK + " x",
                                 MARK + "\x7f", MARK + "‮"])
def test_blank_or_control_ids_are_422_without_echo(rig, path, bad):
    r = replay(rig[0], bad, path)
    assert r.status_code == 422 and MARK not in r.text


@pytest.mark.parametrize("path", ["/replay", "/replay/markdown"])
def test_over_limit_is_422_without_echo(rig, path):
    r = replay(rig[0], MARK + "a" * AGENT_ID_MAX, path)
    assert r.status_code == 422 and MARK not in r.text


def test_the_markdown_heading_cannot_be_split(rig):
    client, _, _ = rig
    r = replay(client, "a b", "/replay/markdown")
    assert r.status_code == 200 and r.text.splitlines()[0] == "# Post-mortem — a b"


def test_a_normal_and_a_200_char_id_still_replay_and_a_registry_shaped_id_is_asked(rig):
    client, spy, _ = rig
    assert replay(client, "invoicing-agent").status_code == 200
    assert replay(client, "a" * AGENT_ID_MAX).status_code == 200
    assert spy.ids == ["invoicing-agent", "a" * AGENT_ID_MAX]
