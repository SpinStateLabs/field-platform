"""Phase G Stage 0, guards slice, C-12 (design 2.2.1, RT1-3), registry side: a status
PATCH carrying ``x-field-operator-on-behalf-of`` records the named operator as
``operator_on_behalf_of`` on its ledger event ONLY when the caller authenticates
with ``bypass_operator_list`` (the kill-switch acting for the human it already
checked). From any other caller, an unauthenticated one, flags OFF, or with a
malformed value, nothing is recorded and the payload is exactly what it was.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry import api as registry_api
from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

KEY_DON = "tkv-c12don-key-0123456789abcdef"
KEY_KS = "tkv-c12ks-key-0123456789abcdef"
KEY_KILLER = "tkv-c12killer-key-0123456789abcdef"
OBO = "x-field-operator-on-behalf-of"


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


class Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload, agent_id=None):
        self.events.append((event_type, payload, agent_id))

    def of(self, event_type):
        return [p for t, p, _ in self.events if t == event_type]


@pytest.fixture()
def ops_file(tmp_path):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
         "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KS), "status": "active",
         "scopes": ["kill", "revive", "bypass_operator_list"]},
        {"operator_id": "killer", "key_sha256": oa.key_sha256(KEY_KILLER), "status": "active",
         "scopes": ["kill", "revive"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


@pytest.fixture()
def env(tmp_path):
    ledger = Ledger()
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=ledger))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    return c, ledger


def hdr(op, key, on_behalf=None):
    h = {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}
    if on_behalf is not None:
        h[OBO] = on_behalf
    return h


def arm(monkeypatch, ops_file, mode):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def test_the_header_name_is_the_one_the_kill_switch_sends():
    from kill_switch import api as ks_api
    assert registry_api.ON_BEHALF_HEADER == ks_api.ON_BEHALF_HEADER == OBO


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_a_bypass_caller_on_behalf_of_a_human_is_recorded_on_the_status_change(
        env, ops_file, monkeypatch, mode):
    c, ledger = env
    arm(monkeypatch, ops_file, mode)
    r = c.patch("/agents/a1", json={"status": "killed"}, headers=hdr("svc-killswitch", KEY_KS, "don"))
    assert r.status_code == 200
    [ev] = ledger.of("registry.status_changed")
    assert ev["operator_on_behalf_of"] == "don"
    assert ev["operator_id_authenticated"] == "svc-killswitch"
    assert (ev["from"], ev["to"]) == ("active", "killed")


def test_an_idempotent_status_patch_records_it_on_registry_updated(env, ops_file, monkeypatch):
    c, ledger = env
    arm(monkeypatch, ops_file, "enforce")
    for _ in range(2):
        assert c.patch("/agents/a1", json={"status": "killed"},
                       headers=hdr("svc-killswitch", KEY_KS, "don")).status_code == 200
    [upd] = ledger.of("registry.updated")
    assert upd["operator_on_behalf_of"] == "don" and upd["fields"] == ["status"]


@pytest.mark.parametrize("who,key", [("don", KEY_DON), ("killer", KEY_KILLER)])
def test_a_caller_without_the_bypass_scope_cannot_name_someone_else(env, ops_file, monkeypatch, who, key):
    """``*`` does not imply bypass_operator_list; a plain ``kill`` holder neither."""
    c, ledger = env
    arm(monkeypatch, ops_file, "enforce")
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers=hdr(who, key, "someone-else")).status_code == 200
    [ev] = ledger.of("registry.status_changed")
    assert "operator_on_behalf_of" not in ev
    assert ev["operator_id_authenticated"] == who


def test_an_unauthenticated_log_only_caller_cannot_name_anyone(env, ops_file, monkeypatch):
    c, ledger = env
    arm(monkeypatch, ops_file, "log-only")
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers={OBO: "don"}).status_code == 200
    assert c.patch("/agents/a1", json={"status": "active"},
                   headers=hdr("svc-killswitch", "tkv-wrong-key-0123456789", "don")).status_code == 200
    for ev in ledger.of("registry.status_changed"):
        assert "operator_on_behalf_of" not in ev
        assert ev["operator_id_authenticated"] is None


def test_flags_off_the_header_changes_nothing(env):
    c, ledger = env
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers=hdr("svc-killswitch", KEY_KS, "don")).status_code == 200
    [ev] = ledger.of("registry.status_changed")
    assert ev == {"from": "active", "to": "killed"}


@pytest.mark.parametrize("value", ["fok_" + "a" * 40, "don hagell", "", "x" * 65, "a,b",
                                   "d" + "o" * 45])
def test_a_malformed_on_behalf_value_is_never_recorded(env, ops_file, monkeypatch, value):
    c, ledger = env
    arm(monkeypatch, ops_file, "log-only")
    c.patch("/agents/a1", json={"status": "killed"}, headers=hdr("svc-killswitch", KEY_KS, value))
    for ev in ledger.of("registry.status_changed"):
        assert "operator_on_behalf_of" not in ev
    assert "fok_" not in json.dumps(ledger.events)


def test_a_duplicated_on_behalf_header_is_never_recorded(env, ops_file, monkeypatch):
    c, ledger = env
    arm(monkeypatch, ops_file, "log-only")
    h = [(oa.HEADER_OPERATOR, "svc-killswitch"), (oa.HEADER_KEY, KEY_KS), (OBO, "don"), (OBO, "eve")]
    assert c.patch("/agents/a1", json={"status": "killed"}, headers=h).status_code == 200
    [ev] = ledger.of("registry.status_changed")
    assert "operator_on_behalf_of" not in ev


def test_a_non_status_edit_never_records_it(env, ops_file, monkeypatch):
    c, ledger = env
    arm(monkeypatch, ops_file, "enforce")
    assert c.patch("/agents/a1", json={"name": "renamed"},
                   headers=hdr("svc-killswitch", KEY_KS, "don")).status_code == 200
    [upd] = ledger.of("registry.updated")
    assert "operator_on_behalf_of" not in upd
