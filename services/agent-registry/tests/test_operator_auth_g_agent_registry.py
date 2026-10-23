"""Phase G: POST /agents/{id}/attest needs an authenticated operator."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
         "status": "active", "scopes": ["*"]},
        {"operator_id": "svc", "key_sha256": oa.key_sha256(KEY_SVC),
         "status": "active", "scopes": ["kill"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


class Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload, agent_id=None):
        self.events.append((event_type, payload))


@pytest.fixture()
def env(tmp_path):
    ledger = Ledger()
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=ledger))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    return c, ledger


ATT = {"attested_by": "Don Hagell"}


def attested(c):
    return c.get("/agents/a1").json()["attested_at"]


def test_off_by_default(env):
    c, _ = env
    assert c.post("/agents/a1/attest", json=ATT).status_code == 200


def test_attest_refusals_leave_the_clock_untouched(env, enforce):
    c, ledger = env
    before = attested(c)
    assert c.post("/agents/a1/attest", json=ATT).status_code == 401
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", "fok_wrong")).status_code == 403
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_SVC)).status_code == 403
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("svc", KEY_SVC)).status_code == 403
    assert attested(c) == before
    assert [e for e in ledger.events if e[0] == "registry.attested"] == []


def test_attest_with_key_records_the_authenticated_id(env, enforce):
    c, ledger = env
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_DON)).status_code == 200
    payload = [p for t, p in ledger.events if t == "registry.attested"][0]
    assert payload["operator_id_authenticated"] == "don"
    assert payload["attested_by"] == "don" and payload["operator_body_claimed"] == "Don Hagell"


# --- review finding: PATCH status was an unguarded kill / revive / retire -------

KEYS = {"killer": "fok_killer_0123456789abcdef", "reviver": "fok_reviver_0123456789abcdef",
        "decom": "fok_decom_0123456789abcdef"}


@pytest.fixture()
def enforce_scoped(tmp_path, monkeypatch):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
             "status": "active", "scopes": ["*"]}]
    for name, scope in (("killer", "kill"), ("reviver", "revive"), ("decom", "decommission")):
        rows.append({"operator_id": name, "key_sha256": oa.key_sha256(KEYS[name]),
                     "status": "active", "scopes": [scope]})
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def status_of(c):
    return c.get("/agents/a1").json()["status"]


@pytest.mark.parametrize("target", ["killed", "retired", "active"])
def test_status_patch_without_credentials_is_401_and_changes_nothing(env, enforce_scoped, target):
    c, _ = env
    if target == "active":
        c.patch("/agents/a1", json={"status": "killed"}, headers=hdr("don", KEY_DON))
    before = status_of(c)
    assert c.patch("/agents/a1", json={"status": target}).status_code == 401
    assert c.patch("/agents/a1", json={"status": target},
                   headers=hdr("don", "fok_wrong")).status_code == 403
    assert status_of(c) == before


def test_each_status_transition_needs_its_own_scope(env, enforce_scoped):
    c, _ = env
    # kill needs "kill"
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers=hdr("reviver", KEYS["reviver"])).status_code == 403
    assert status_of(c) == "active"
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers=hdr("killer", KEYS["killer"])).status_code == 200
    # revive (killed -> active) needs "revive"
    assert c.patch("/agents/a1", json={"status": "active"},
                   headers=hdr("killer", KEYS["killer"])).status_code == 403
    assert status_of(c) == "killed"
    assert c.patch("/agents/a1", json={"status": "active"},
                   headers=hdr("reviver", KEYS["reviver"])).status_code == 200
    # retire needs "decommission"
    assert c.patch("/agents/a1", json={"status": "retired"},
                   headers=hdr("killer", KEYS["killer"])).status_code == 403
    assert status_of(c) == "active"
    assert c.patch("/agents/a1", json={"status": "retired"},
                   headers=hdr("decom", KEYS["decom"])).status_code == 200


def test_status_change_ledger_event_carries_the_authenticated_id(env, enforce_scoped):
    c, ledger = env
    c.patch("/agents/a1", json={"status": "killed"}, headers=hdr("don", KEY_DON))
    p = [p for t, p in ledger.events if t == "registry.status_changed"][0]
    assert p["operator_id_authenticated"] == "don"


def test_non_status_patch_is_not_guarded(env, enforce_scoped):
    c, _ = env
    assert c.patch("/agents/a1", json={"name": "renamed"}).status_code == 200


def test_log_only_status_patch_is_allowed_and_ledgers_unauthenticated(env, enforce_scoped, monkeypatch):
    c, ledger = env
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert c.patch("/agents/a1", json={"status": "killed"}).status_code == 200
    assert [p for t, p in ledger.events if t == "operator.unauthenticated"][0]["action"] == "kill"


def test_attest_body_name_is_replaced_by_the_authenticated_id(env, enforce):
    c, ledger = env
    c.post("/agents/a1/attest", json={"attested_by": "CEO Jane"}, headers=hdr("don", KEY_DON))
    assert c.get("/agents/a1").json()["attested_by"] == "don"
    p = [p for t, p in ledger.events if t == "registry.attested"][0]
    assert p["operator_body_claimed"] == "CEO Jane"


def test_unguarded_registration_is_declared(env, enforce):
    """DECLARED: POST /agents only creates an identity record (status active);
    it cannot kill, revive or retire. Pinned so a change to that is deliberate."""
    c, _ = env
    assert c.post("/agents", json={"agent_id": "a2", "name": "a2", "owner": "O",
                                   "domain": "finance"}).status_code == 201
