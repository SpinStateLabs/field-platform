"""Phase G Stage 0 follow-up, registry side of the reserved ``operator_on_behalf_of``:
with the REAL ledger behind it, the registry still records the human a
``bypass_operator_list`` caller names (it now goes through field-core's
authenticated path, ``bind_on_behalf_of``, because a payload key of that name is
stripped like every reserved key), and a shared-secret caller that goes straight
to the ledger cannot write it.

Real registry + sealed-ledger apps over TestClient; the registry's ledger client
presents ``svc-registry`` (``ledger_attribute``, prefix ``registry.``), as on the
estate (design 2.2.1). Test key values are throwaway constants."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

KEY_KSVC = "tkv-oboreg-ksvc-key-0123456789abcd"
KEY_REG = "tkv-oboreg-reg-key-0123456789abcde"
KEY_DON = "tkv-oboreg-don-key-0123456789abcde"
OBO_HEADER = "x-field-operator-on-behalf-of"


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def stack(tmp_path):
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    reg_ledger = TestClient(ledger.app)
    reg_ledger.headers.update(hdr("svc-registry", KEY_REG))
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3"),
                                              ledger=LedgerClient(client=reg_ledger, base_url="http://t")))
    assert registry.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                          "domain": "finance"}).status_code == 201
    return registry, ledger


def arm(monkeypatch, tmp_path, mode):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KSVC), "status": "active",
         "scopes": ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"],
         "event_prefixes": ["kill."]},
        {"operator_id": "svc-registry", "key_sha256": oa.key_sha256(KEY_REG), "status": "active",
         "scopes": ["ledger_attribute"], "event_prefixes": ["registry."]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def changes(ledger):
    return [e["payload"] for e in ledger.get("/events", params={"event_type": "registry.status_changed"}).json()]


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_the_kill_switch_identity_naming_don_is_recorded_on_the_real_ledger(stack, tmp_path, monkeypatch, mode):
    registry, ledger = stack
    arm(monkeypatch, tmp_path, mode)
    r = registry.patch("/agents/a1", json={"status": "killed"},
                       headers={**hdr("svc-killswitch", KEY_KSVC), OBO_HEADER: "don"})
    assert r.status_code == 200, r.text
    [p] = changes(ledger)
    assert (p["to"], p["operator_on_behalf_of"], p["operator_id_authenticated"]) == ("killed", "don",
                                                                                    "svc-killswitch"), p


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_a_human_caller_naming_someone_else_records_nothing_on_behalf(stack, tmp_path, monkeypatch, mode):
    registry, ledger = stack
    arm(monkeypatch, tmp_path, mode)
    r = registry.patch("/agents/a1", json={"status": "killed"},
                       headers={**hdr("don", KEY_DON), OBO_HEADER: "mallory"})
    assert r.status_code == 200, r.text
    [p] = changes(ledger)
    assert "operator_on_behalf_of" not in p and p["operator_id_authenticated"] == "don", p


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_a_shared_secret_caller_writing_straight_to_the_ledger_cannot_name_anyone(stack, tmp_path, monkeypatch,
                                                                                  mode):
    _, ledger = stack
    arm(monkeypatch, tmp_path, mode)
    r = ledger.post("/events", json={"event_type": "registry.status_changed", "agent_id": "a1",
                                     "payload": {"from": "active", "to": "killed", "operator_on_behalf_of": "don"}})
    assert r.status_code == 201, r.text
    [p] = changes(ledger)
    assert "operator_on_behalf_of" not in p and p["to"] == "killed", p
