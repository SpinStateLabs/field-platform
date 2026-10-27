"""Phase G: POST /tokens (mint) needs an authenticated operator, and
granted_by must equal that operator."""

from __future__ import annotations

import json

import pytest

from field_core import operator_auth as oa
from test_doa_roster import AGENT_ID, Spine, write_manifest

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"
KEY_DSVC = "fok_dsvc-key-0123456789abcdef"


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
        # the delegation service's own identity: appends mint events on a human's behalf
        {"operator_id": "dsvc", "key_sha256": oa.key_sha256(KEY_DSVC),
         "status": "active", "scopes": ["ledger_attribute"], "event_prefixes": ["delegation."]},
    ]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


@pytest.fixture()
def spine(tmp_path):
    s = Spine(tmp_path, write_manifest(tmp_path))
    s.ledger.headers.update(hdr("dsvc", KEY_DSVC))
    return s


def body(granted_by):
    return {"agent_id": AGENT_ID, "granted_by": granted_by, "scope": ["x"], "ttl_seconds": 60}


def tokens(spine):
    return spine.delegation.get("/tokens").json()


def test_off_by_default_mint_needs_no_headers(spine):
    assert spine.mint(granted_by="Anyone").status_code == 201


def test_mint_refusals_create_no_token(spine, enforce):
    post = spine.delegation.post
    assert post("/tokens", json=body("don")).status_code == 401
    assert post("/tokens", json=body("don"), headers=hdr("don", "fok_wrong")).status_code == 403
    assert post("/tokens", json=body("don"), headers=hdr("don", KEY_SVC)).status_code == 403
    # scope: svc may only kill
    assert post("/tokens", json=body("svc"), headers=hdr("svc", KEY_SVC)).status_code == 403
    assert tokens(spine) == []


def test_granted_by_must_equal_the_authenticated_operator(spine, enforce):
    r = spine.delegation.post("/tokens", json=body("Somebody Else"),
                              headers=hdr("don", KEY_DON))
    assert r.status_code == 403 and tokens(spine) == []


def test_matching_granted_by_mints_and_ledgers_the_id(spine, enforce):
    r = spine.delegation.post("/tokens", json=body("don"), headers=hdr("don", KEY_DON))
    assert r.status_code == 201, r.text
    p = spine.mint_events()[0]["payload"]
    assert p["operator_id_authenticated"] == "don" and p["granted_by"] == "don"


# --- review finding: revoke was unguarded -----------------------------------------


def test_revoke_needs_an_authenticated_operator_with_the_revoke_scope(spine, enforce):
    r = spine.delegation.post("/tokens", json=body("don"), headers=hdr("don", KEY_DON))
    tid = r.json()["token_id"]
    post = spine.delegation.post
    assert post(f"/tokens/{tid}/revoke").status_code == 401
    assert post(f"/tokens/{tid}/revoke", headers=hdr("don", "fok_wrong")).status_code == 403
    assert post(f"/tokens/{tid}/revoke", headers=hdr("svc", KEY_SVC)).status_code == 403  # kill-only
    assert spine.delegation.get(f"/tokens/{tid}").json()["revoked"] is False
    assert post(f"/tokens/{tid}/revoke", headers=hdr("don", KEY_DON)).status_code == 200
    assert spine.delegation.get(f"/tokens/{tid}").json()["revoked"] is True


def test_mint_event_from_a_ledger_caller_without_ledger_attribute_drops_the_operator_fields(spine, enforce):
    # PG0-CORE-R3-01 (renamed; was ..._with_service_identity_keeps_the_operator_fields). The
    # ledger drops reserved keys from a caller that does not hold ledger_attribute with an
    # event_prefix reaching the type (C-10). Here the delegation service's ledger client
    # presents don, whose "*" does NOT imply ledger_attribute, so the mint event loses its
    # operator fields. The positive path (svc-delegation, ledger_attribute, "delegation.")
    # is test_matching_granted_by_mints_and_ledgers_the_id.
    import json as _j
    spine.ledger.headers.update(hdr("don", KEY_DON))   # "*" does NOT include assert_operator
    r = spine.delegation.post("/tokens", json=body("don"), headers=hdr("don", KEY_DON))
    assert r.status_code == 201
    p = spine.mint_events()[0]["payload"]
    assert "operator_id_authenticated" not in p
