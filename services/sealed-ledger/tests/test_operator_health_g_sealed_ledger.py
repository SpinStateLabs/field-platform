"""Phase G Stage 0, health slice, sealed-ledger: C-8 /health operator block,
C-10/C-15 POST /events through admit_ledger_event (operator.unauthenticated
accepted from any shared-secret caller and stamped self_reported; every other
operator.* type refused; reserved keys only within a ledger_attribute reach),
C-16 operator.refused for the ledger's own refusals.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

KEY_DON = "tkv-ldon-key-0123456789abcdef"
KEY_REG = "tkv-lreg-key-0123456789abcdef"
KEY_KS = "tkv-lks-key-0123456789abcdef"

OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
FORGED = {"operator_id_authenticated": "don", "operator_key_fp": "deadbeef",
          "operator_claimed": "don"}


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


def _row(oid, key, scopes, **kw):
    return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
            "created_at": "2026-10-26", "scopes": scopes, **kw}


@pytest.fixture()
def registry_file(tmp_path):
    rows = [_row("don", KEY_DON, ["*"]),
            _row("svc-registry", KEY_REG, ["ledger_attribute"], event_prefixes=["registry."]),
            _row("svc-killswitch", KEY_KS, ["kill", "bypass_operator_list", "ledger_attribute"],
                 event_prefixes=["kill."])]
    p = tmp_path / "operators.json"
    raw = json.dumps(rows).encode("utf-8")
    p.write_bytes(raw)
    return p, raw


@pytest.fixture()
def log_only(registry_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(registry_file[0]))
    return registry_file


@pytest.fixture()
def enforce(log_only, monkeypatch):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    return log_only


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "e.jsonl")))


def events(client, t):
    return client.get("/events", params={"event_type": t}).json()


# --- C-8 --------------------------------------------------------------------------------


def test_health_carries_the_operator_block_with_flags_off(client):
    h = client.get("/health").json()
    assert OPERATOR_FIELDS <= set(h) and "manifests_unresolved" not in h
    assert h["operator_mode"] == "off" and h["operator_registry_sha256_prefix"] is None
    assert h["operator_registry_rows"] is None and h["refused_count"] == 0
    assert h["service"] == "sealed-ledger" and "event_count" in h      # nothing lost


def test_health_reports_the_registry_the_guards_read(client, log_only):
    _, raw = log_only
    h = client.get("/health").json()
    assert h["operator_mode"] == "log-only"
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(raw).hexdigest()[:16]
    assert h["operator_registry_rows"] == 3 and h["last_registry_error"] is None
    body = json.dumps(h)
    for k in (KEY_DON, KEY_REG, KEY_KS):
        assert k not in body and oa.key_sha256(k) not in body


def test_health_names_a_broken_registry_under_enforce(client, enforce):
    p, _ = enforce
    p.write_text("[]")
    h = client.get("/health").json()
    assert h["operator_mode"] == "enforce" and h["operator_registry_rows"] is None
    assert h["last_registry_error"]


# --- C-10 / C-15: POST /events through admit_ledger_event -------------------------------


@pytest.mark.parametrize("mode_fixture", ["log_only", "enforce"])
def test_operator_unauthenticated_is_accepted_from_any_caller_as_self_reported(
        client, request, mode_fixture):
    request.getfixturevalue(mode_fixture)
    body = {"event_type": "operator.unauthenticated",
            "payload": {"action": "kill", "claimed_id": "x", **FORGED}}
    assert client.post("/events", json=body).status_code == 201
    assert client.post("/events", json=body, headers=hdr("don", KEY_DON)).status_code == 201
    assert client.post("/events", json=body, headers=hdr("svc-killswitch", KEY_KS)).status_code == 201
    got = [e["payload"] for e in events(client, "operator.unauthenticated")]
    assert [p["self_reported"] for p in got] == [True, True, False]
    for p in got:
        assert not (set(FORGED) & set(p)) and p["claimed_id"] == "x"


def test_operator_refused_is_accepted_as_self_reported(client, enforce):
    body = {"event_type": "operator.refused", "payload": {"action": "kill", "reason": "forbidden"}}
    assert client.post("/events", json=body).status_code == 201
    assert events(client, "operator.refused")[0]["payload"]["self_reported"] is True


@pytest.mark.parametrize("etype", ["operator.mode_changed", "operator.registry_changed",
                                   "operator.anything", "Operator.Mode_Changed"])
def test_every_other_operator_type_is_refused_to_every_caller(client, enforce, etype):
    body = {"event_type": etype, "payload": {"mode": "off"}}
    for h in ({}, hdr("don", KEY_DON), hdr("svc-registry", KEY_REG),
              hdr("svc-killswitch", KEY_KS)):
        assert client.post("/events", json=body, headers=h).status_code == 403, h
    assert events(client, etype) == []


def test_attribution_survives_only_inside_the_callers_prefix_reach(client, enforce):
    ks = hdr("svc-killswitch", KEY_KS)
    assert client.post("/events", json={"event_type": "kill.agent", "payload": FORGED},
                       headers=ks).status_code == 201
    assert client.post("/events", json={"event_type": "registry.status_changed",
                                        "payload": FORGED}, headers=ks).status_code == 201
    assert client.post("/events", json={"event_type": "kill.agent", "payload": FORGED},
                       headers=hdr("svc-registry", KEY_REG)).status_code == 201
    kept, other = events(client, "kill.agent")
    assert kept["payload"]["operator_id_authenticated"] == "don"
    assert not (set(FORGED) & set(other["payload"]))
    assert not (set(FORGED) & set(events(client, "registry.status_changed")[0]["payload"]))


def test_flags_off_the_ledger_policy_is_byte_identical(client):
    body = {"event_type": "operator.mode_changed", "payload": FORGED}
    assert client.post("/events", json=body).status_code == 201
    assert events(client, "operator.mode_changed")[0]["payload"] == FORGED


# --- C-16 -------------------------------------------------------------------------------


def test_a_refused_forgery_under_enforce_is_counted_and_ledgered(client, enforce):
    r = client.post("/events", json={"event_type": "operator.mode_changed", "payload": {}},
                    headers=hdr("don", KEY_DON))
    assert r.status_code == 403
    rec = events(client, "operator.refused")
    assert len(rec) == 1
    p = rec[0]["payload"]
    assert (p["action"], p["path"], p["reason"], p["status"], p["claimed_id"]) == (
        "append_event", "/events", "forbidden", 403, "don")
    assert p["event_type_refused"] == "operator.mode_changed"
    assert KEY_DON not in json.dumps(rec)
    assert client.get("/health").json()["refused_count"] == 1


def test_a_guard_refusal_under_enforce_is_counted_and_ledgered(client, enforce):
    assert client.post("/hold", json={"by": "Don", "reason": "r"}).status_code == 401
    assert client.post("/hold", json={"by": "Don", "reason": "r"},
                       headers=hdr("don", "tkv-wrong-0000000")).status_code == 403
    rec = [e["payload"] for e in events(client, "operator.refused")]
    assert [(p["action"], p["path"], p["reason"]) for p in rec] == [
        ("hold", "/hold", "no_credential"), ("hold", "/hold", "forbidden")]
    assert "tkv-wrong-0000000" not in json.dumps(rec)
    assert client.get("/health").json()["refused_count"] == 2


def test_log_only_refusals_are_not_ledgered(client, log_only):
    r = client.post("/events", json={"event_type": "operator.mode_changed", "payload": {}})
    assert r.status_code == 403
    assert events(client, "operator.refused") == []
    assert client.get("/health").json()["refused_count"] == 1
