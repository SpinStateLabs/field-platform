"""S2-4 / red-team R-1: the kill-switch's own identity is revoked or unreadable under REQUIRE.

Every kill and revive then answers 502 "registry unreachable" (the registry refuses the kill-switch's PATCH with 401
or 403), the agent's status does not change (fail closed, never an unreviewed 200), and the break-glass identity
`don-breakglass` is the only path: it flips the registry record directly (runbook B-7 / B-4) and the ledger row names
it. OFF and LOG-ONLY are unchanged. Cited as the nearest existing tests, which do NOT cover this: C-12 on-behalf-of
(test_on_behalf_of_c12_kill_switch.py) and the unreadable OPERATORS FILE (test_operator_auth_g_kill_switch.py:240).
Real kill-switch + registry + sealed-ledger apps over TestClient; REQUIRE is set inside the tests only; every key is
a throwaway constant."""

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

BODY = {"operator": "Don Hagell", "reason": "s2-4"}
KEY_DON = "tkv-s24-don-key-0123456789abcdef"
KEY_KSVC = "tkv-s24-ksvc-key-0123456789abcdef"
KEY_BG = "tkv-s24-bg-key-0123456789abcdef"
KEY_REG = "tkv-s24-reg-key-0123456789abcdef"


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


EXPIRY = "2027-01-09T01:15:00Z"
_GEN = [100]


def rows(ks_status="active"):
    """A format-2 operators file (the sealed break-glass row needs it); generation rises on every call."""
    _GEN[0] += 1
    base = {"created_at": "2026-10-26T01:15:00Z", "names": []}
    return {
        "format": 2, "generation": _GEN[0], "issued_at": "2026-11-05T03:12:09Z", "issued_by": "svc-rotator-gb10",
        "operators": [
            {**base, "operator_id": "don", "status": "active", "scopes": ["*"], "names": ["Don Hagell"],
             "rotation": "auto", "key_sha256": oa.key_sha256(KEY_DON), "key_created_at": "2026-10-26T01:15:00Z",
             "key_not_after": EXPIRY},
            {**base, "operator_id": "svc-killswitch", "status": ks_status,
             "scopes": ["kill", "revive", "drill", "bypass_operator_list", "ledger_attribute"],
             "event_prefixes": ["kill.", "registry."], "rotation": "auto", "key_sha256": oa.key_sha256(KEY_KSVC),
             "key_created_at": "2026-10-26T01:15:00Z", "key_not_after": EXPIRY},
            {**base, "operator_id": "svc-registry", "status": "active",
             "scopes": ["ledger_attribute"], "event_prefixes": ["registry."], "rotation": "auto",
             "key_sha256": oa.key_sha256(KEY_REG), "key_created_at": "2026-10-26T01:15:00Z",
             "key_not_after": EXPIRY},
            {**base, "operator_id": "don-breakglass", "status": "active",
             "scopes": ["kill", "revive", "bypass_operator_list"], "rotation": "sealed",
             "key_sha256": oa.key_sha256(KEY_BG)},
        ]}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


class Stack:
    def __init__(self, tmp_path):
        self.path = tmp_path / "operators.json"
        self.write(rows())
        ledger_app = create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl"))
        self.ledger = TestClient(ledger_app)
        # the registry appends to the ledger as its own identity (svc-registry), not as the kill-switch
        reg_ledger = TestClient(ledger_app)
        reg_ledger.headers.update(hdr("svc-registry", KEY_REG))
        self.registry = TestClient(create_registry_app(
            store=RegistryStore(tmp_path / "a.sqlite3"),
            ledger=LedgerClient(client=reg_ledger, base_url="http://t")))
        self.svc = hdr("svc-killswitch", KEY_KSVC)
        self.registry.headers.update(self.svc)
        self.ledger.headers.update(self.svc)
        self.kill = TestClient(create_kill_app(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t")), raise_server_exceptions=False)
        assert self.registry.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                                   "domain": "finance"}).status_code == 201

    def write(self, rs):
        self.path.write_text(json.dumps(rs), encoding="utf-8")

    def status(self):
        return self.registry.get("/agents/a1").json()["status"]

    def events(self, event_type):
        return self.ledger.get("/events", params={"event_type": event_type}).json()


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)


def arm(monkeypatch, stack, mode="enforce"):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(stack.path))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def test_revoked_killswitch_key_every_kill_and_revive_is_502_and_nothing_changes(stack, monkeypatch):
    arm(monkeypatch, stack)
    stack.write(rows(ks_status="revoked"))
    for path in ("/kill/a1", "/revive/a1", "/drill/a1"):
        r = stack.kill.post(path, json=BODY, headers=hdr("don", KEY_DON))
        assert r.status_code in (500, 502), (path, r.status_code, r.text)   # a drill answers 500, not 502 (runbook)
        if path != "/drill/a1":
            assert r.status_code == 502, (path, r.text)
            assert "registry" in r.json()["detail"].lower()
    assert stack.status() == "active"
    assert stack.events("registry.status_changed") == []


def test_an_unreadable_killswitch_identity_is_the_same_fail_closed_502(stack, monkeypatch):
    # "key file unreadable": the kill-switch presents no usable identity to the registry
    arm(monkeypatch, stack)
    stack.registry.headers.pop(oa.HEADER_KEY, None)
    stack.registry.headers.pop(oa.HEADER_OPERATOR, None)
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 502, r.text
    r = stack.kill.post("/revive/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 502, r.text
    assert stack.status() == "active"


def test_the_refusal_is_visible_on_health(stack, monkeypatch):
    arm(monkeypatch, stack)
    stack.write(rows(ks_status="revoked"))
    stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    h = stack.registry.get("/health").json()
    assert json.dumps(h).lower().count("refus") >= 1 or h.get("operator_refused_count", 0) >= 1, h


OBO = "x-field-operator-on-behalf-of"


def test_break_glass_flips_the_record_and_the_ledger_row_names_it(stack, monkeypatch):
    arm(monkeypatch, stack)
    stack.write(rows(ks_status="revoked"))
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 502
    # a bypass-scope identity may change a status only for an operator it names (C-12): without the name it is refused
    r = stack.registry.patch("/agents/a1", json={"status": "killed"}, headers=hdr("don-breakglass", KEY_BG))
    assert r.status_code == 403 and stack.status() == "active"
    r = stack.registry.patch("/agents/a1", json={"status": "killed"},
                             headers={**hdr("don-breakglass", KEY_BG), OBO: "don-breakglass"})
    assert r.status_code == 200, r.text
    assert stack.status() == "killed"
    [change] = stack.events("registry.status_changed")
    assert change["payload"]["to"] == "killed"
    assert change["payload"]["operator_id_authenticated"] == "don-breakglass"
    assert change["payload"]["operator_on_behalf_of"] == "don-breakglass"


def test_b7_dons_own_key_flips_the_record_directly_when_the_killswitch_identity_is_broken(stack, monkeypatch):
    arm(monkeypatch, stack)
    stack.write(rows(ks_status="revoked"))
    r = stack.registry.patch("/agents/a1", json={"status": "killed"}, headers=hdr("don", KEY_DON))
    assert r.status_code == 200 and r.json()["status"] == "killed", r.text
    [change] = stack.events("registry.status_changed")
    assert change["payload"]["operator_id_authenticated"] == "don"


def test_after_the_key_is_restored_kills_pass_again(stack, monkeypatch):
    arm(monkeypatch, stack)
    stack.write(rows(ks_status="revoked"))
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 502
    stack.write(rows())
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.status() == "killed"
    assert stack.kill.post("/revive/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.status() == "active"


@pytest.mark.parametrize("mode", ["off", "log-only"])
def test_off_and_log_only_a_revoked_killswitch_key_changes_nothing(stack, monkeypatch, mode):
    if mode == "log-only":
        arm(monkeypatch, stack, "log-only")
        stack.write(rows(ks_status="revoked"))
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert stack.status() == "killed"
