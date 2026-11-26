"""An agent id outside the registry's id rule is a 422 on spend, usage, caps, rate limits and policies: no store call,
no ledger row, no registry read."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

#: ids that still match the one-segment path routes once percent-encoded
OUTSIDE = ["Upper", "-a", ".a", "a b", "a?b", "a#b", "a" + chr(10) + "b", "a" + chr(0x202E), chr(0xE9), "a" * 129]


class Untouched:
    """Any use of the store is a test failure."""

    def __getattr__(self, name):
        raise AssertionError(f"store.{name} reached")


class Sink:
    def __init__(self):
        self.calls = []

    def append(self, *a, **k):
        self.calls.append(("append", a, k))

    def get_agent(self, agent_id):
        self.calls.append(("get_agent", agent_id))
        return {"agent_id": agent_id, "status": "active"}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE):
        monkeypatch.delenv(name, raising=False)
    ledger, registry = Sink(), Sink()
    store = GovernorStore(tmp_path / "g.sqlite3")
    app = create_app(store=store, ledger=ledger, registry=registry)
    app.state.store = Untouched()
    yield TestClient(app), ledger, registry
    store.close()


def send(client, method, path, body):
    return client.request(method, path, content=json.dumps(body, ensure_ascii=True),
                          headers={"content-type": "application/json"})


@pytest.mark.parametrize("agent", OUTSIDE)
@pytest.mark.parametrize("path,extra", [("/spend", {"cents": 1}), ("/usage", {"model": "m"})], ids=["spend", "usage"])
def test_metering_under_an_id_outside_the_rule_reaches_nothing(api, path, extra, agent):
    client, ledger, registry = api
    r = send(client, "POST", path, {"agent_id": agent, **extra})
    assert r.status_code == 422, r.text
    assert ledger.calls == [] and registry.calls == []


@pytest.mark.parametrize("agent", OUTSIDE)
@pytest.mark.parametrize("prefix,extra", [
    ("/caps", {"limit_cents": 100}),
    ("/rate-limits", {"rate_limits": [{"action": "act", "max": 1, "period": "session"}]}),
    ("/policies", {}),
], ids=["caps", "rate-limits", "policies"])
def test_configuration_under_an_id_outside_the_rule_reaches_nothing(api, prefix, extra, agent):
    client, ledger, registry = api
    r = send(client, "PUT", f"{prefix}/{quote(agent, safe='')}", {"agent_id": agent, **extra})
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], list), r.text        # the model refused it, not the path/body comparison
    assert ledger.calls == [] and registry.calls == []
