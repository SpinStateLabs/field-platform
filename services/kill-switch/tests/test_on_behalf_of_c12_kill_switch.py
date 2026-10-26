"""Phase G Stage 0, guards slice, C-12 (design 2.2.1, RT1-3), kill-switch side: every
registry status write the kill-switch makes for an authenticated caller (kill,
domain kill, revive, the drill's kill and restore) carries
``x-field-operator-on-behalf-of: <that caller's authenticated id>``, so the
registry can record the human behind the kill-switch's own identity. Flags OFF,
or an unauthenticated (LOG-ONLY) caller: no header, the PATCH exactly as before.

Real kill-switch + registry + sealed-ledger apps over TestClient; the registry
TestClient carries the kill-switch's service identity as default headers (as in
test_operator_auth_g_kill_switch.py). Test key values are throwaway constants."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

BODY = {"operator": "Don Hagell", "reason": "c12"}
KEY_DON = "tkv-c12k-don-key-0123456789abcdef"
KEY_KSVC = "tkv-c12k-ksvc-key-0123456789abcdef"
OBO = "x-field-operator-on-behalf-of"


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def ops_file(tmp_path):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
         "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KSVC), "status": "active",
         "scopes": ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"],
         "event_prefixes": ["kill.", "registry."]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


class Spy:
    """Wraps the registry TestClient; records the headers of every PATCH."""

    def __init__(self, inner):
        self.inner = inner
        self.patches: list[dict] = []

    def get(self, *a, **kw):
        return self.inner.get(*a, **kw)

    def patch(self, url, json=None, headers=None, **kw):  # noqa: A002
        self.patches.append({"url": url, "status": (json or {}).get("status"),
                             "headers": {k.lower(): v for k, v in (headers or {}).items()}})
        return self.inner.patch(url, json=json, headers=headers, **kw)


class Stack:
    def __init__(self, tmp_path):
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
        self.registry = TestClient(create_registry_app(
            store=RegistryStore(tmp_path / "a.sqlite3"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))
        svc = hdr("svc-killswitch", KEY_KSVC)
        self.registry.headers.update(svc)
        self.ledger.headers.update(svc)
        self.spy = Spy(self.registry)
        self.kill = TestClient(create_kill_app(
            registry=RegistryClient(client=self.spy, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))
        assert self.registry.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                                   "domain": "finance"}).status_code == 201

    def events(self, event_type):
        return self.ledger.get("/events", params={"event_type": event_type}).json()

    def obo(self):
        return [p["headers"].get(OBO) for p in self.spy.patches]


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)


def arm(monkeypatch, ops_file, mode):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


@pytest.mark.parametrize("mode", ["log-only", "enforce"])
def test_kill_and_revive_send_the_authenticated_caller_as_on_behalf_of(stack, ops_file, monkeypatch, mode):
    arm(monkeypatch, ops_file, mode)
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.kill.post("/revive/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.obo() == ["don", "don"]
    changes = stack.events("registry.status_changed")
    assert [(e["payload"]["to"], e["payload"]["operator_on_behalf_of"]) for e in changes] == [
        ("killed", "don"), ("active", "don")]
    assert all(e["payload"]["operator_id_authenticated"] == "svc-killswitch" for e in changes)
    # the pairing the gate checks: each status change has a kill.* row by the same human
    assert stack.events("kill.agent")[0]["payload"]["operator_id_authenticated"] == "don"
    assert stack.events("kill.revive")[0]["payload"]["operator_id_authenticated"] == "don"


def test_a_domain_kill_sends_it_on_every_agent(stack, ops_file, monkeypatch):
    assert stack.registry.post("/agents", json={"agent_id": "a2", "name": "a2", "owner": "O",
                                                "domain": "finance"}).status_code == 201
    arm(monkeypatch, ops_file, "enforce")
    assert stack.kill.post("/kill/domain/finance", json=BODY,
                           headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.obo() == ["don", "don"]


def test_the_drill_sends_it_on_the_kill_and_on_the_restore(stack, ops_file, monkeypatch):
    arm(monkeypatch, ops_file, "enforce")
    r = stack.kill.post("/drill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 200 and r.json()["restored"] is True
    assert [(p["status"], p["headers"].get(OBO)) for p in stack.spy.patches] == [
        ("killed", "don"), ("active", "don")]


def test_the_on_behalf_of_value_is_the_authenticated_id_not_the_body_or_the_claim(
        stack, ops_file, monkeypatch):
    arm(monkeypatch, ops_file, "enforce")
    body = {"operator": "someone-else", "reason": "c12"}
    assert stack.kill.post("/kill/a1", json=body, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.obo() == ["don"]


def test_flags_off_no_header_and_the_patch_is_unchanged(stack):
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.obo() == [None]
    [ev] = stack.events("registry.status_changed")
    assert "operator_on_behalf_of" not in ev["payload"]


def test_an_unauthenticated_log_only_caller_sends_no_header(stack, ops_file, monkeypatch):
    arm(monkeypatch, ops_file, "log-only")
    assert stack.kill.post("/kill/a1", json=BODY).status_code == 200
    assert stack.kill.post("/revive/a1", json=BODY,
                           headers=hdr("don", "tkv-not-the-key-0123456789")).status_code == 200
    assert stack.obo() == [None, None]


def test_a_registry_double_that_overrides_set_status_is_called_as_before(tmp_path, ops_file, monkeypatch):
    """Test doubles and wrappers keep their own set_status (no header, no new argument)."""
    calls = []

    class Double(RegistryClient):
        def set_status(self, agent_id, status):
            calls.append((agent_id, status))
            return super().set_status(agent_id, status)

    s = Stack(tmp_path)
    s.kill.app.state.registry = Double(client=s.spy, base_url="http://t")
    arm(monkeypatch, ops_file, "log-only")
    assert s.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert calls == [("a1", "killed")] and s.obo() == [None]


def test_a_registry_answer_is_mapped_as_set_status_maps_it(stack, ops_file, monkeypatch):
    """404 -> not registered (404); any other non-200 -> registry unreachable (502)."""
    arm(monkeypatch, ops_file, "enforce")

    class Answer:
        def __init__(self, code):
            self.status_code, self.text = code, "simulated"

        def json(self):
            return {}

    real_patch = stack.spy.patch
    stack.spy.patch = lambda *a, **kw: (real_patch(*a, **kw), Answer(500))[1]
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 502 and "registry returned 500" in r.json()["detail"]
    stack.spy.patch = lambda *a, **kw: (real_patch(*a, **kw), Answer(404))[1]
    r = stack.kill.post("/revive/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 404


def test_the_key_never_travels_in_the_on_behalf_header(stack, ops_file, monkeypatch):
    arm(monkeypatch, ops_file, "enforce")
    stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    for p in stack.spy.patches:
        assert KEY_DON not in json.dumps(p) and oa.key_sha256(KEY_DON) not in json.dumps(p)
