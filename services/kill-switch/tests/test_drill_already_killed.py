"""S12-13: a drill on an agent that is already killed is refused 409 before any note, write or signal (it would
otherwise report a confirmed kill/restore although nothing was proven); an active agent's drill is unchanged."""

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

BODY = {"operator": "Don", "reason": "drill"}


class _Counting:
    """Wraps the registry TestClient and counts PATCH calls."""

    def __init__(self, inner):
        self._inner = inner
        self.patches = 0

    def get(self, *a, **k):
        return self._inner.get(*a, **k)

    def post(self, *a, **k):
        return self._inner.post(*a, **k)

    def patch(self, *a, **k):
        self.patches += 1
        return self._inner.patch(*a, **k)


@pytest.fixture()
def stack(tmp_path):
    reg = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    led = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    counting = _Counting(reg)
    kill = TestClient(create_kill_app(registry=RegistryClient(client=counting, base_url="http://t"),
                                      ledger=LedgerClient(client=led, base_url="http://t")))
    assert reg.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "Owner", "domain": "d"}).status_code == 201
    return kill, reg, led, counting


def _kinds(led):
    return [e["event_type"] for e in led.get("/events").json()]


def test_a_drill_on_a_killed_agent_is_409_and_does_nothing(stack):
    kill, reg, led, counting = stack
    assert kill.post("/kill/a1", json=BODY).status_code == 200
    before_patches, before_events = counting.patches, _kinds(led)
    r = kill.post("/drill/a1", json=BODY)
    assert r.status_code == 409
    assert "already killed" in r.json()["detail"]
    assert counting.patches == before_patches                 # no registry write
    assert _kinds(led) == before_events                       # no kill.drill.* note, no signal ledger row
    assert reg.get("/agents/a1").json()["status"] == "killed"


def test_an_active_agents_drill_is_unchanged(stack):
    kill, reg, led, counting = stack
    r = kill.post("/drill/a1", json=BODY)
    assert r.status_code == 200
    assert r.json()["restored"] is True and r.json()["restored_status"] == "active"
    assert "kill.drill.start" in _kinds(led)
