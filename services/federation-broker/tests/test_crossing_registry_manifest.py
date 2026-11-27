"""Outbound crossings under enforce are decided on the REGISTERED manifest, not on the one the caller sends."""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from federation_broker import registered_manifest as rm
from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core import operator_auth as oa
from field_core.clients import AgentNotRegisteredError, ManifestResolver

from test_federation_outbound import DATA_CLASS, HOME, OUR_AGENT, SCOPE, contract_body, our_manifest

KEY = "fok_all-key-0123456789abcdef"
PAIR = {oa.HEADER_OPERATOR: "all", oa.HEADER_KEY: KEY}


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload=None, agent_id=None, **_):
        self.rows.append((event_type, payload))


class Registry:
    def __init__(self, record=None, error=None):
        self.record, self.error, self.asked = record, error, []

    def get_agent(self, agent_id):
        self.asked.append(agent_id)
        if self.error:
            raise self.error
        return self.record


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIELD_ORG_NAME", HOME)


def arm(tmp_path, monkeypatch, require=True):
    p = tmp_path / "operators.json"
    p.write_text(json.dumps([{"operator_id": "all", "key_sha256": oa.key_sha256(KEY), "status": "active",
                              "scopes": ["*"]}]))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if require:
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def isolated():
    data = our_manifest()
    data["federated"] = {"isolated": True, "allowed_peers": [], "contracts": []}
    return data


def on_disk(tmp_path, data, name="agent.yaml"):
    folder = tmp_path / "manifests"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(yaml.safe_dump(data), encoding="utf-8")
    return folder


def record(ref="agent.yaml", status="active"):
    return {"agent_id": OUR_AGENT, "status": status, "manifest_ref": ref}


def stack(tmp_path, registry, folder=None):
    ledger = Ledger()
    app = create_app(BrokerEngine(store=ContractStore(tmp_path / "contracts.sqlite3"), ledger=ledger))
    app.state.registered = rm.RegisteredManifest(registry, ManifestResolver(folder or tmp_path / "manifests"))
    client = TestClient(app)
    assert client.put("/contracts/FED-2026-001", json=contract_body(), headers=PAIR).status_code == 200
    return client, ledger


def ask(client, manifest, direction="outbound"):
    body = {"direction": direction, "counterparty_org": contract_body()["counterparty_org"], "scope": SCOPE,
            "data_class": DATA_CLASS}
    if direction == "outbound":
        body.update(agent_id=OUR_AGENT, manifest=manifest)
    else:
        body.update(counterparty_agent_id="their-agent", counterparty_manifest=manifest)
    r = client.post("/crossing", json=body, headers=PAIR)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_flattering_manifest_in_the_request_does_not_cross(tmp_path, monkeypatch):
    arm(tmp_path, monkeypatch)
    registry = Registry(record())
    client, ledger = stack(tmp_path, registry, on_disk(tmp_path, isolated()))
    verdict = ask(client, our_manifest())
    assert (verdict["decision"], verdict["clause_id"]) == ("BLOCK", "F.isolated")
    assert registry.asked == [OUR_AGENT]
    assert [r[0] for r in ledger.rows if r[0] in ("federation.allow", "federation.block")] == ["federation.block"]


def test_the_registered_manifest_decides_when_the_request_sends_nothing_useful(tmp_path, monkeypatch):
    arm(tmp_path, monkeypatch)
    client, _ = stack(tmp_path, Registry(record()), on_disk(tmp_path, our_manifest()))
    assert ask(client, {})["decision"] == "ALLOW"


def test_an_absolute_ref_is_read_too(tmp_path, monkeypatch):
    arm(tmp_path, monkeypatch)
    folder = on_disk(tmp_path, our_manifest())
    client, _ = stack(tmp_path, Registry(record(str(folder / "agent.yaml"))), tmp_path / "elsewhere")
    assert ask(client, {})["decision"] == "ALLOW"


@pytest.mark.parametrize("registry,why", [
    (Registry(error=AgentNotRegisteredError(OUR_AGENT)), rm.NOT_REGISTERED),
    (Registry(error=RuntimeError("http://registry.internal said no")), rm.REGISTRY_UNREAD),
    (Registry(record(status="killed")), rm.NOT_ACTIVE),
    (Registry(record(ref=None)), rm.NO_REF),
    (Registry(record(ref="missing.yaml")), rm.UNREADABLE),
    (Registry(record(ref=".")), rm.UNREADABLE),
    (Registry(record(ref="broken.yaml")), rm.UNREADABLE),
    (Registry(record(ref="list.yaml")), rm.UNREADABLE),
])
def test_without_a_registered_manifest_nothing_crosses(tmp_path, monkeypatch, registry, why):
    arm(tmp_path, monkeypatch)
    folder = on_disk(tmp_path, our_manifest())
    (folder / "broken.yaml").write_text("a: [unclosed", encoding="utf-8")
    (folder / "list.yaml").write_text("- one\n- two\n", encoding="utf-8")
    client, ledger = stack(tmp_path, registry, folder)
    verdict = ask(client, our_manifest())
    assert (verdict["decision"], verdict["clause_id"], verdict["reasons"]) == ("BLOCK", "I.manifest", [why])
    said = json.dumps([verdict, ledger.rows], default=str)
    assert str(folder) not in said and "registry.internal" not in said


def test_inbound_does_not_read_the_registry(tmp_path, monkeypatch):
    arm(tmp_path, monkeypatch)
    registry = Registry(record())
    client, _ = stack(tmp_path, registry)
    ask(client, our_manifest(), direction="inbound")
    assert registry.asked == []


@pytest.mark.parametrize("registered,state", [(our_manifest, "same"), (isolated, "differs"), (None, "unreadable")])
def test_log_only_decides_on_the_callers_and_says_how_the_registry_compares(tmp_path, monkeypatch, registered, state):
    arm(tmp_path, monkeypatch, require=False)
    sent = our_manifest()
    folder = on_disk(tmp_path, sent if state == "same" else isolated()) if registered else tmp_path / "manifests"
    client, _ = stack(tmp_path, Registry(record()), folder)
    verdict = ask(client, sent)
    assert verdict["decision"] == "ALLOW"
    assert verdict["context"]["registry_manifest"] == state


def test_with_the_operator_layer_off_the_registry_is_not_asked(tmp_path):
    registry = Registry(record())
    client, _ = stack(tmp_path, registry)
    verdict = ask(client, our_manifest())
    assert verdict["decision"] == "ALLOW" and registry.asked == []
    assert "registry_manifest" not in verdict["context"]
