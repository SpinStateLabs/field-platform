"""Phase G Stage 0 follow-up: an HTTP caller holding only the perimeter secret cannot
put ``operator_on_behalf_of`` on a ledger row (it is a RESERVED key now, like
``operator_id_authenticated``); the registry's own authenticated identity, holding
``ledger_attribute`` with the ``registry.`` prefix, still can.

Real sealed-ledger app over TestClient with FIELD_SHARED_SECRET set (a throwaway
test value) and the operator mode armed (LOG-ONLY and ENFORCE). Flags OFF the
ledger is unchanged from before Phase G (the README's stated limit)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

SECRET = "obo-ledger-test-perimeter-secret"
KEY_REG = "tkv-obo-ledger-reg-key-0123456789ab"
KEY_DON = "tkv-obo-ledger-don-key-0123456789ab"
OBO = "operator_on_behalf_of"
FORGED = {"from": "active", "to": "killed", OBO: "don", "operator_id_authenticated": "svc-killswitch",
          "nested": {OBO: "don"}}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)


@pytest.fixture()
def ledger(tmp_path):
    c = TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")))
    c.headers.update({"x-field-auth": SECRET})
    return c


def arm(monkeypatch, tmp_path, mode):
    rows = [
        {"operator_id": "svc-registry", "key_sha256": oa.key_sha256(KEY_REG), "status": "active",
         "scopes": ["ledger_attribute"], "event_prefixes": ["registry."]},
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def _stored(ledger, event_id):
    [ev] = [e for e in ledger.get("/events").json() if e["event_id"] == event_id]
    return ev["payload"]


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
@pytest.mark.parametrize("who", ["shared-secret only", "don (*)"])
def test_a_perimeter_caller_cannot_forge_on_behalf_of(ledger, tmp_path, monkeypatch, mode, who):
    arm(monkeypatch, tmp_path, mode)
    headers = {} if who == "shared-secret only" else {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON}
    r = ledger.post("/events", json={"event_type": "registry.status_changed", "agent_id": "a1",
                                     "payload": FORGED}, headers=headers)
    assert r.status_code == 201, r.text
    p = _stored(ledger, r.json()["event_id"])
    assert OBO not in p and OBO not in p["nested"] and "operator_id_authenticated" not in p, p
    assert (p["from"], p["to"]) == ("active", "killed")              # the rest of the row is kept


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_the_registry_identity_still_records_it_on_its_own_events(ledger, tmp_path, monkeypatch, mode):
    arm(monkeypatch, tmp_path, mode)
    reg = {oa.HEADER_OPERATOR: "svc-registry", oa.HEADER_KEY: KEY_REG}
    r = ledger.post("/events", json={"event_type": "registry.status_changed", "agent_id": "a1",
                                     "payload": FORGED}, headers=reg)
    assert r.status_code == 201, r.text
    p = _stored(ledger, r.json()["event_id"])
    assert p[OBO] == "don" and p["operator_id_authenticated"] == "svc-killswitch", p
    # outside its reach (not a registry.* type) it is stripped even for the registry
    r = ledger.post("/events", json={"event_type": "kill.agent", "agent_id": "a1", "payload": FORGED},
                    headers=reg)
    assert OBO not in _stored(ledger, r.json()["event_id"])


def test_flags_off_the_ledger_is_unchanged_the_stated_limit(ledger):
    r = ledger.post("/events", json={"event_type": "registry.status_changed", "agent_id": "a1",
                                     "payload": FORGED})
    assert r.status_code == 201
    assert _stored(ledger, r.json()["event_id"])[OBO] == "don"
