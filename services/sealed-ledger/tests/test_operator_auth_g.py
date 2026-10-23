"""Phase G: /rotate and /hold on the sealed ledger need an authenticated operator."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

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


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "e.jsonl")))


HOLD = {"by": "Don", "reason": "litigation"}


def events(client, t):
    return client.get("/events", params={"event_type": t}).json()


def test_off_by_default_hold_needs_no_headers(client):
    assert client.post("/hold", json=HOLD).status_code == 201
    p = events(client, "ledger.legal_hold.placed")[0]["payload"]
    assert "operator_id_authenticated" not in p


@pytest.mark.parametrize("path,body", [
    ("/hold", HOLD), ("/hold/release", {"by": "Don"}),
    ("/rotate", {"operator": "Don", "reason": "r"}),
])
def test_refusals_on_every_guarded_ledger_write(client, enforce, path, body):
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=hdr("don", "fok_wrong")).status_code == 403
    assert client.post(path, json=body, headers=hdr("don", KEY_SVC)).status_code == 403
    assert client.post(path, json=body, headers=hdr("svc", KEY_SVC)).status_code == 403  # scope
    assert client.get("/hold").json()["held"] is False
    assert events(client, "ledger.legal_hold.placed") == []


def test_authenticated_hold_and_release_record_the_id_in_the_event(client, enforce):
    h = hdr("don", KEY_DON)
    assert client.post("/hold", json=HOLD, headers=h).status_code == 201
    assert client.post("/hold/release", json={"by": "Don"}, headers=h).status_code == 200
    for t in ("ledger.legal_hold.placed", "ledger.legal_hold.released"):
        p = events(client, t)[0]["payload"]
        assert p["operator_id_authenticated"] == "don"
        assert p["operator_key_fp"] == oa.key_sha256(KEY_DON)[:8]


def test_log_only_hold_is_allowed_and_ledgers_operator_unauthenticated(client, enforce, monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert client.post("/hold", json=HOLD).status_code == 201
    assert events(client, "operator.unauthenticated")[0]["payload"]["action"] == "hold"


def test_unreadable_operator_registry_denies_503(client, enforce, tmp_path):
    (tmp_path / "operators.json").write_text("nope")
    assert client.post("/hold", json=HOLD, headers=hdr("don", KEY_DON)).status_code == 503
    assert client.get("/hold").json()["held"] is False
