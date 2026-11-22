"""An unreachable registry on /heartbeat and /drill is 502 (like /kill and /revive), never an unhandled 500 (S2-1).

The 502 is a choice: an outage is NOT turned into killed=true or killed=false; the caller decides."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient, RegistryUnreachableError
from kill_switch.api import create_app as create_kill_app
from kill_switch.store import HeartbeatStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO", "reason": "s2-1"}


class Flaky:
    """Registry client whose reads, or its first write to `killed`, fail as an outage would."""

    def __init__(self, inner, *, reads_down=False, first_kill_write_down=False):
        self.inner, self.reads_down, self.kill_down = inner, reads_down, first_kill_write_down

    def get_agent(self, agent_id):
        if self.reads_down:
            raise RegistryUnreachableError("registry down")
        return self.inner.get_agent(agent_id)

    def list_agents(self, **kw):
        return self.inner.list_agents(**kw)

    def set_status(self, agent_id, status):
        if status == "killed" and self.kill_down:
            self.kill_down = False
            raise RegistryUnreachableError("registry down")
        return self.inner.set_status(agent_id, status)


class Rig:
    def __init__(self, tmp_path, **flaky):
        self.registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3")))
        assert self.registry.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                                   "domain": "finance"}).status_code == 201
        self.hb = HeartbeatStore(tmp_path / "hb.sqlite3")
        self.flaky = Flaky(RegistryClient(client=self.registry, base_url="http://t"), **flaky)
        self.kill = TestClient(create_kill_app(
            registry=self.flaky, heartbeats=self.hb,
            ledger=LedgerClient(client=TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl"))),
                                base_url="http://t")))

    def status(self):
        return self.registry.get("/agents/a1").json()["status"]


@pytest.mark.parametrize("method", ["get", "post"])
def test_heartbeat_with_the_registry_down_is_502(tmp_path, method):
    rig = Rig(tmp_path, reads_down=True)
    r = getattr(rig.kill, method)("/heartbeat/a1")
    assert r.status_code == 502 and "registry unreachable" in r.json()["detail"]
    assert rig.hb.get("a1") is None, "a failed check-in records no row"


def test_drill_with_the_registry_down_is_502(tmp_path):
    rig = Rig(tmp_path, reads_down=True)
    r = rig.kill.post("/drill/a1", json=OP)
    assert r.status_code == 502 and "registry unreachable" in r.json()["detail"]


def test_a_drill_whose_kill_write_fails_is_502_and_the_agent_stays_active(tmp_path):
    rig = Rig(tmp_path, first_kill_write_down=True)
    r = rig.kill.post("/drill/a1", json=OP)
    assert r.status_code == 502 and "registry unreachable" in r.json()["detail"]
    assert rig.status() == "active"


def test_the_healthy_path_is_unchanged(tmp_path):
    rig = Rig(tmp_path)
    assert rig.kill.get("/heartbeat/a1").json()["killed"] is False
    assert rig.kill.post("/heartbeat/a1").status_code == 200 and rig.hb.get("a1")["checkins"] == 1
    assert rig.kill.post("/drill/a1", json=OP).status_code == 200 and rig.status() == "active"
