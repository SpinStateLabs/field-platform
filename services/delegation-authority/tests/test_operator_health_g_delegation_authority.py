"""Phase G Stage 0, health slice, delegation-authority: C-8 /health operator
block, C-16 operator.refused under ENFORCE (guard refusals and the
granted_by refusal), written through the real sealed-ledger, which accepts it
from the shared-secret caller as self-reported (C-15).

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest

from field_core import operator_auth as oa
from test_doa_roster import AGENT_ID, Spine, write_manifest

KEY_DON = "tkv-ddon-key-0123456789abcdef"
KEY_SVC = "tkv-dsvc-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def registry_file(tmp_path):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
             "scopes": ["*"]},
            {"operator_id": "svc", "key_sha256": oa.key_sha256(KEY_SVC), "status": "active",
             "scopes": ["kill"]}]
    p = tmp_path / "operators.json"
    raw = json.dumps(rows).encode()
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
def spine(tmp_path):
    return Spine(tmp_path, write_manifest(tmp_path))


def body(granted_by):
    return {"agent_id": AGENT_ID, "granted_by": granted_by, "scope": ["x"], "ttl_seconds": 60}


def refused(spine):
    return [e["payload"] for e in
            spine.ledger.get("/events", params={"event_type": "operator.refused"}).json()]


def test_health_carries_the_operator_block_with_flags_off(spine):
    h = spine.delegation.get("/health").json()
    assert OPERATOR_FIELDS <= set(h) and "manifests_unresolved" not in h
    assert h["operator_mode"] == "off" and h["service"] == "delegation-authority"
    assert "token_count" in h


def test_health_reports_the_registry_the_guards_read(spine, log_only):
    h = spine.delegation.get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(log_only[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 2
    assert KEY_DON not in json.dumps(h) and oa.key_sha256(KEY_DON) not in json.dumps(h)


def test_enforce_refusals_are_counted_and_ledgered_as_self_reported(spine, enforce):
    post = spine.delegation.post
    assert post("/tokens", json=body("don")).status_code == 401
    assert post("/tokens", json=body("svc"), headers=hdr("svc", KEY_SVC)).status_code == 403
    # granted_by refusal happens inside the handler, after the guard
    assert post("/tokens", json=body("Somebody Else"),
                headers=hdr("don", KEY_DON)).status_code == 403
    assert post("/tokens/t-none/revoke", json={"by": "x"}).status_code == 401
    rec = refused(spine)
    assert [(p["action"], p["path"], p["reason"], p["claimed_id"]) for p in rec] == [
        ("mint", "/tokens", "no_credential", None), ("mint", "/tokens", "forbidden", "svc"),
        ("mint", "/tokens", "forbidden", "don"),
        ("revoke", "/tokens/t-none/revoke", "no_credential", None)]
    assert all(p["self_reported"] is True for p in rec)
    assert KEY_SVC not in json.dumps(rec) and KEY_DON not in json.dumps(rec)
    assert spine.delegation.get("/health").json()["refused_count"] == 4
    assert spine.delegation.get("/tokens").json() == []
