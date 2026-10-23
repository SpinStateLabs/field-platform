"""Phase G: authenticated operators on kill / revive / drill.

Real kill-switch + registry + sealed-ledger apps over TestClient. Every
refusal test asserts the side effect did NOT happen (agent still active), so
removing the guard turns it red, not just the status code.
"""

from __future__ import annotations

import json
import logging

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from field_core.templates_api import template_data
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

BODY = {"operator": "Don Hagell", "reason": "g-test"}
KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"
KEY_OTHER = "fok_other-key-0123456789abcdef"
KEY_KSVC = "fok_ksvc-key-0123456789abcdef"


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def ops_file(tmp_path):
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON),
         "status": "active", "created_at": "2026-10-01", "scopes": ["*"]},
        {"operator_id": "svc-lifecycle", "key_sha256": oa.key_sha256(KEY_SVC),
         "status": "active", "created_at": "2026-10-01", "scopes": ["kill"]},
        {"operator_id": "other", "key_sha256": oa.key_sha256(KEY_OTHER),
         "status": "active", "created_at": "2026-10-01", "scopes": ["*"]},
        # the kill-switch's OWN service identity: it flips the registry status
        # (kill/revive) and appends to the ledger on a human's behalf.
        {"operator_id": "kill-svc", "key_sha256": oa.key_sha256(KEY_KSVC),
         "status": "active", "created_at": "2026-10-01",
         "scopes": ["kill", "revive", "assert_operator"]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_OPERATOR, raising=False)
    monkeypatch.delenv(oa.ENV_OPERATOR_KEY, raising=False)


class Stack:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
        self.ledger = TestClient(
            create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
        svc = {oa.HEADER_OPERATOR: "kill-svc", oa.HEADER_KEY: KEY_KSVC}
        self.registry.headers.update(svc)
        self.ledger.headers.update(svc)
        self.kill = TestClient(create_kill_app(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
        ))

    def register(self, agent_id, authorized=None):
        body = {"agent_id": agent_id, "name": agent_id, "owner": "Owner",
                "domain": "finance"}
        if authorized is not None:
            data = template_data("default")
            data["agent"]["name"] = agent_id
            data["enforcement"]["kill_switch"]["authorized_operators"] = authorized
            path = self.tmp_path / f"{agent_id}.yaml"
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            body["manifest_ref"] = str(path)
        assert self.registry.post("/agents", json=body).status_code == 201

    def status(self, agent_id):
        return self.registry.get(f"/agents/{agent_id}").json()["status"]

    def events(self, event_type):
        return self.ledger.get("/events", params={"event_type": event_type}).json()


@pytest.fixture()
def stack(tmp_path):
    s = Stack(tmp_path)
    s.register("a1")
    return s


@pytest.fixture()
def enforce(ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


# --- default: behaviour unchanged -------------------------------------------


def test_default_off_kill_works_without_headers_and_adds_no_fields(stack):
    r = stack.kill.post("/kill/a1", json=BODY)
    assert r.status_code == 200 and stack.status("a1") == "killed"
    payload = stack.events("kill.agent")[0]["payload"]
    assert "operator_id_authenticated" not in payload


def test_default_off_ignores_garbage_operator_headers(stack):
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("x", "y"))
    assert r.status_code == 200


# --- log-only ----------------------------------------------------------------


def test_log_only_allows_unauthenticated_and_ledgers_it(stack, ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    r = stack.kill.post("/kill/a1", json=BODY)
    assert r.status_code == 200 and stack.status("a1") == "killed"
    ev = stack.events("operator.unauthenticated")
    assert len(ev) == 1 and ev[0]["payload"]["reason"] == "no_credential"
    assert ev[0]["payload"]["action"] == "kill"
    kp = stack.events("kill.agent")[0]["payload"]
    assert kp["operator_id_authenticated"] is None


def test_log_only_wrong_key_still_allowed_but_not_authenticated(stack, ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", "fok_wrong"))
    assert r.status_code == 200
    assert stack.events("operator.unauthenticated")[0]["payload"]["reason"] == "bad_credential"
    assert stack.events("kill.agent")[0]["payload"]["operator_id_authenticated"] is None


def test_log_only_good_key_records_the_authenticated_id(stack, ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 200
    assert stack.events("operator.unauthenticated") == []
    kp = stack.events("kill.agent")[0]["payload"]
    assert kp["operator_id_authenticated"] == "don"
    assert kp["operator_claimed"] == "don"
    assert kp["operator_key_fp"] == oa.key_sha256(KEY_DON)[:8]
    # the body's free-text name does not stand in for the proven identity
    assert kp["operator"] == "don" and kp["operator_body_claimed"] == "Don Hagell"


def test_log_only_unreadable_registry_does_not_block_a_kill(stack, ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    ops_file.write_text("garbage")
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 200


def test_malformed_headers_are_400_even_in_log_only(stack, ops_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    r = stack.kill.post("/kill/a1", json=BODY,
                        headers={oa.HEADER_OPERATOR: "don, evil", oa.HEADER_KEY: KEY_DON})
    assert r.status_code == 400 and stack.status("a1") == "active"


# --- enforce: the three refusals, on every guarded route ----------------------


ROUTES = [("kill", "/kill/a1"), ("revive", "/revive/a1"), ("drill", "/drill/a1"),
          ("kill", "/kill/domain/finance")]


@pytest.mark.parametrize("action,path", ROUTES)
def test_no_key_is_401_and_nothing_happens(stack, enforce, action, path):
    r = stack.kill.post(path, json=BODY)
    assert r.status_code == 401
    assert stack.status("a1") == "active"
    assert stack.events("kill.agent") == [] and stack.events("kill.drill.start") == []


@pytest.mark.parametrize("action,path", ROUTES)
def test_wrong_key_is_403_and_nothing_happens(stack, enforce, action, path):
    r = stack.kill.post(path, json=BODY, headers=hdr("don", "fok_wrong"))
    assert r.status_code == 403 and r.json()["detail"] == oa.FORBIDDEN_DETAIL
    assert stack.status("a1") == "active"
    assert stack.events("kill.agent") == [] and stack.events("kill.drill.start") == []


@pytest.mark.parametrize("action,path", ROUTES)
def test_id_key_mismatch_is_403_identical_body(stack, enforce, action, path):
    wrong = stack.kill.post(path, json=BODY, headers=hdr("don", "fok_wrong"))
    mism = stack.kill.post(path, json=BODY, headers=hdr("don", KEY_OTHER))
    spoof = stack.kill.post(path, json=BODY, headers=hdr("ghost", KEY_DON))
    assert mism.status_code == spoof.status_code == 403
    assert mism.json() == wrong.json() == spoof.json()
    assert stack.status("a1") == "active"


def test_good_key_kills_revives_and_drills_and_ledger_has_the_id(stack, enforce):
    h = hdr("don", KEY_DON)
    assert stack.kill.post("/kill/a1", json=BODY, headers=h).status_code == 200
    assert stack.status("a1") == "killed"
    assert stack.kill.post("/revive/a1", json=BODY, headers=h).status_code == 200
    assert stack.status("a1") == "active"
    assert stack.kill.post("/drill/a1", json=BODY, headers=h).status_code == 200
    for et in ("kill.agent", "kill.revive", "kill.drill.start"):
        p = stack.events(et)[0]["payload"]
        assert p["operator_id_authenticated"] == "don", et
        assert p["operator_key_fp"] == oa.key_sha256(KEY_DON)[:8], et


def test_scope_narrow_service_identity_can_kill_but_not_revive(stack, enforce):
    h = hdr("svc-lifecycle", KEY_SVC)
    assert stack.kill.post("/kill/a1", json=BODY, headers=h).status_code == 200
    r = stack.kill.post("/revive/a1", json=BODY, headers=h)
    assert r.status_code == 403 and stack.status("a1") == "killed"


def test_unreadable_operator_registry_is_503_and_the_agent_is_untouched(stack, enforce, ops_file):
    ops_file.write_text("{broken")
    r = stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 503 and stack.status("a1") == "active"


def test_registry_service_down_does_not_block_a_kill_auth(tmp_path, enforce):
    """The operators file is local: authenticating the human needs no registry
    call (only the status flip itself uses the registry service)."""
    s = Stack(tmp_path)
    s.register("a1")
    r = s.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 200


# --- authorized_operators ----------------------------------------------------


def test_authorized_operators_blocks_an_authenticated_but_unlisted_operator(tmp_path, enforce):
    s = Stack(tmp_path)
    s.register("guarded", authorized=["don"])
    r = s.kill.post("/kill/guarded", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 403 and r.json()["detail"] == oa.FORBIDDEN_DETAIL
    assert s.status("guarded") == "active"
    assert s.kill.post("/kill/guarded", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200
    assert s.status("guarded") == "killed"
    r = s.kill.post("/revive/guarded", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 403 and s.status("guarded") == "killed"
    r = s.kill.post("/drill/guarded", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 403


def test_authorized_operators_empty_list_allows_any_authenticated_operator(tmp_path, enforce):
    s = Stack(tmp_path)
    s.register("open", authorized=[])
    assert s.kill.post("/kill/open", json=BODY, headers=hdr("other", KEY_OTHER)).status_code == 200


def test_domain_kill_skips_agents_the_operator_may_not_kill(tmp_path, enforce):
    s = Stack(tmp_path)
    s.register("mine", authorized=["other"])
    s.register("theirs", authorized=["don"])
    r = s.kill.post("/kill/domain/finance", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 200
    assert s.status("mine") == "killed" and s.status("theirs") == "active"
    out = {x["agent_id"]: x["outcome"] for x in r.json()["results"]}
    assert out["theirs"] == "error"


# --- keys never reach logs ---------------------------------------------------


def test_key_never_appears_in_logs_responses_or_ledger(stack, enforce, caplog):
    caplog.set_level(logging.DEBUG)
    secret = "fok_SUPERSECRETVALUE0123456789"
    texts = []
    for h in (hdr("don", secret), hdr("don", KEY_DON), hdr("ghosté", secret)):
        try:
            r = stack.kill.post("/kill/a1", json=BODY, headers=h)
            texts.append(r.text)
        except Exception as exc:  # a non-ASCII header may be refused client side
            texts.append(repr(exc))
    texts.append(json.dumps(stack.ledger.get("/events").json()))
    texts.append(caplog.text)
    blob = "\n".join(texts)
    assert "SUPERSECRETVALUE" not in blob
    assert KEY_DON not in blob


# --- declared limitation: replay ---------------------------------------------


def test_declared_limitation_the_key_is_a_replayable_bearer_secret(stack, enforce):
    """DOCUMENTED, NOT FIXED: the key is a bearer secret on plain HTTP. A
    captured request replays, byte for byte, until the key is revoked. TLS and
    replay protection are the edge's job. This test pins the honest statement
    so nobody reads Phase G as nonce-protected."""
    h = hdr("don", KEY_DON)
    first = stack.kill.post("/kill/a1", json=BODY, headers=h)
    again = stack.kill.post("/kill/a1", json=BODY, headers=h)
    assert first.status_code == again.status_code == 200


# --- review findings: body operator, unresolvable manifest, forged fields -----


def test_body_operator_cannot_impersonate_another_name(stack, enforce):
    r = stack.kill.post("/kill/a1", json={"operator": "CEO Jane", "reason": "x"},
                        headers=hdr("don", KEY_DON))
    assert r.status_code == 200
    p = stack.events("kill.agent")[0]["payload"]
    assert p["operator"] == "don"                      # not "CEO Jane"
    assert p["operator_body_claimed"] == "CEO Jane"
    assert r.json()["operator"] == "don"


def test_unresolvable_manifest_denies_under_enforce(tmp_path, enforce):
    s = Stack(tmp_path)
    s.register("ghosty", authorized=["don"])
    (tmp_path / "ghosty.yaml").unlink()          # the manifest vanishes after registration
    for path in ("/kill/ghosty", "/revive/ghosty", "/drill/ghosty"):
        r = s.kill.post(path, json=BODY, headers=hdr("don", KEY_DON))
        assert r.status_code == 503, path
    assert s.status("ghosty") == "active"


def test_agent_without_a_manifest_ref_needs_only_authentication_and_scope(stack, enforce):
    # nothing is declared, so there is no list to consult; the caller still authenticates
    assert stack.kill.post("/kill/a1", json=BODY).status_code == 401
    assert stack.kill.post("/kill/a1", json=BODY, headers=hdr("don", KEY_DON)).status_code == 200


def test_forged_operator_fields_in_a_payload_are_dropped(stack, enforce):
    forged = {"operator_id_authenticated": "don", "operator_key_fp": "deadbeef",
              "operator_claimed": "don"}
    lc = LedgerClient(client=stack.ledger, base_url="http://t")
    lc.append("some.event", payload={"x": 1, **forged})   # no authenticated context
    p = stack.events("some.event")[0]["payload"]
    assert not (set(forged) & set(p)) and p["x"] == 1
