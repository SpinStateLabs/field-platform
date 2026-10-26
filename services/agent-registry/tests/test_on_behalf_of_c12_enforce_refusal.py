"""Phase G Stage 0, guards slice, C-12 (design 2.2.1, RT1-3), the ENFORCE refusal:
under FIELD_OPERATOR_REQUIRE a status PATCH from an identity holding
``bypass_operator_list`` that does not name, in exactly one well-formed
``x-field-operator-on-behalf-of``, the operator it acts for is refused 403
(the same body as every other refusal), changes nothing, writes no status event
and is ledgered as ``operator.refused`` (C-16). A non-status edit, a caller
without the bypass scope, and LOG-ONLY are not affected.

Test key values are throwaway constants."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

KEY_DON = "tkv-c12e-don-key-0123456789abcdef"
KEY_KS = "tkv-c12e-ks-key-0123456789abcdef"
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
        return [(p, a) for t, p, a in self.events if t == event_type]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
         "scopes": ["*"]},
        {"operator_id": "svc-killswitch", "key_sha256": oa.key_sha256(KEY_KS), "status": "active",
         "scopes": ["kill", "revive", "decommission", "registry_edit", "bypass_operator_list"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    ledger = Ledger()
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=ledger))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    return c, ledger, monkeypatch


def ks(on_behalf=None):
    h = {oa.HEADER_OPERATOR: "svc-killswitch", oa.HEADER_KEY: KEY_KS}
    if on_behalf is not None:
        h[OBO] = on_behalf
    return h


@pytest.mark.parametrize("target", ["killed", "active", "retired"])
@pytest.mark.parametrize("on_behalf", [None, "fok_" + "b" * 40, "not an id"])
def test_enforce_bypass_status_patch_without_a_named_operator_is_refused(env, target, on_behalf):
    c, ledger, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    if target == "active":
        assert c.patch("/agents/a1", json={"status": "killed"},
                       headers=ks("don")).status_code == 200
        ledger.events.clear()
    before = c.get("/agents/a1").json()["status"]
    r = c.patch("/agents/a1", json={"status": target}, headers=ks(on_behalf))
    assert r.status_code == 403 and r.json()["detail"] == oa.FORBIDDEN_DETAIL
    assert c.get("/agents/a1").json()["status"] == before
    assert ledger.of("registry.status_changed") == [] and ledger.of("registry.updated") == []
    [(refused, agent)] = ledger.of("operator.refused")
    assert agent == "a1" and refused["claimed_id"] == "svc-killswitch" and refused["status"] == 403
    assert "fok_" not in json.dumps(ledger.events)


def test_enforce_a_duplicated_header_is_refused_too(env):
    c, ledger, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    h = [(oa.HEADER_OPERATOR, "svc-killswitch"), (oa.HEADER_KEY, KEY_KS), (OBO, "don"), (OBO, "don")]
    assert c.patch("/agents/a1", json={"status": "killed"}, headers=h).status_code == 403
    assert c.get("/agents/a1").json()["status"] == "active"


def test_enforce_bypass_status_patch_naming_the_operator_is_allowed(env):
    c, ledger, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"status": "killed"}, headers=ks("don")).status_code == 200
    [(ev, _)] = ledger.of("registry.status_changed")
    assert ev["operator_on_behalf_of"] == "don"


def test_enforce_a_non_status_edit_by_the_bypass_identity_needs_no_name(env):
    c, _, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"domain": "ops"}, headers=ks()).status_code == 200


def test_enforce_a_caller_without_the_bypass_scope_needs_no_name(env):
    c, _, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"status": "killed"},
                   headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON}).status_code == 200


def test_log_only_never_refuses_it(env):
    c, ledger, _ = env
    assert c.patch("/agents/a1", json={"status": "killed"}, headers=ks()).status_code == 200
    [(ev, _)] = ledger.of("registry.status_changed")
    assert "operator_on_behalf_of" not in ev


def test_a_retired_agent_is_still_409_first(env):
    """The integrity rule keeps its own answer for every identity."""
    c, _, mp = env
    mp.setenv(oa.ENV_REQUIRE, "1")
    assert c.patch("/agents/a1", json={"status": "retired"},
                   headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON}).status_code == 200
    assert c.patch("/agents/a1", json={"status": "active"}, headers=ks()).status_code == 409
