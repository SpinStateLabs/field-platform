"""C-130 (reviewer R-11 F-R11-1, MEDIUM): the drill's own failure detection was not pinned. Forcing either
`if kill_confirmed is None:` (L809, the kill did not propagate) or `if not hb.killed:` (L813, the heartbeat
is still live) to False survived the whole suite, so a drill that never proved the halt could still return
a success report: the failure a drill exists to catch reported as a pass.

Fault injection: a registry client that delegates to the real one and misreports an agent's status, over the real
registry, ledger and kill-switch apps. The `finally` restore must still run in both failures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT = "invoicing-agent"
OP = {"operator": "Don Hagell", "reason": "drill failure detection (C-130)"}


class Flaky:
    """Delegates to the real RegistryClient; `mode` decides what get_agent REPORTS after the kill flip."""

    def __init__(self, real, mode):
        self.real, self.mode = real, mode
        self.flipped = False
        self.reads_after_flip = 0
        self.sets: list[str] = []

    def set_status(self, agent_id, status, *a, **k):
        self.sets.append(status)
        out = self.real.set_status(agent_id, status, *a, **k)
        self.flipped = status == "killed"
        if not self.flipped:
            self.reads_after_flip = 0
        return out

    def get_agent(self, agent_id):
        rec = dict(self.real.get_agent(agent_id))
        if self.flipped:
            self.reads_after_flip += 1
            if self.mode == "no_propagation":
                rec["status"] = "active"                       # the registry never shows the kill
            elif self.mode == "heartbeat_live":
                # the kill is visible to the propagation loop (first read), stale for the heartbeat read
                rec["status"] = "killed" if self.reads_after_flip == 1 else "active"
        return rec

    def __getattr__(self, name):
        return getattr(self.real, name)


@pytest.fixture()
def world(tmp_path):
    registry_client = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger_client = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    registry_client.post("/agents", json={"agent_id": AGENT, "name": AGENT, "owner": "Owner", "domain": "finance"})
    real = RegistryClient(client=registry_client, base_url="http://t")

    def build(mode):
        flaky = Flaky(real, mode)
        app = create_kill_app(registry=flaky, ledger=LedgerClient(client=ledger_client, base_url="http://t"))
        return TestClient(app), flaky

    return build, registry_client, ledger_client


def _types(ledger_client):
    return [e["event_type"] for e in ledger_client.get("/events").json()]


def test_a_kill_that_never_propagates_fails_the_drill_and_restores(world):
    build, registry_client, ledger_client = world
    kill_client, flaky = build("no_propagation")
    r = kill_client.post(f"/drill/{AGENT}", json=OP)
    assert r.status_code == 500 and "kill did not propagate" in r.text
    assert "kill.drill.complete" not in _types(ledger_client)           # no success record
    assert flaky.sets == ["killed", "active"]                           # the finally restore ran
    assert registry_client.get(f"/agents/{AGENT}").json()["status"] == "active"


def test_a_heartbeat_that_still_shows_the_agent_live_fails_the_drill_and_restores(world):
    build, registry_client, ledger_client = world
    kill_client, flaky = build("heartbeat_live")
    r = kill_client.post(f"/drill/{AGENT}", json=OP)
    assert r.status_code == 500 and "heartbeat still live" in r.text
    assert "kill.drill.complete" not in _types(ledger_client)
    assert flaky.sets == ["killed", "active"]
    assert registry_client.get(f"/agents/{AGENT}").json()["status"] == "active"


def test_the_healthy_path_is_unchanged_by_the_fault_wrapper(world):
    """Control: the wrapper with no fault behaves like the real client, so the two failures above are the faults."""
    build, registry_client, ledger_client = world
    kill_client, flaky = build("healthy")
    r = kill_client.post(f"/drill/{AGENT}", json=OP)
    assert r.status_code == 200 and r.json()["restored"] is True
    assert "kill.drill.complete" in _types(ledger_client)
    assert flaky.sets == ["killed", "active"]
