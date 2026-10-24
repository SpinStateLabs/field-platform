"""Phase G: PUT /contracts is an operator write."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from field_core import operator_auth as oa

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture()
def enforce(tmp_path, monkeypatch):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
            {"operator_id": "svc", "key_sha256": oa.key_sha256(KEY_SVC), "status": "active", "scopes": ["kill"]}]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows))
    monkeypatch.setenv(oa.ENV_REGISTRY, str(p))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


C = {"contract_id": "c1", "counterparty_org": "Acme", "allowed_scopes": ["read"], "allowed_data_classes": ["public"]}


def test_contract_writes_are_guarded(enforce):
    client = TestClient(create_app())
    assert client.put("/contracts/c1", json=C).status_code == 401
    assert client.put("/contracts/c1", json=C, headers=hdr("don", "fok_wrong")).status_code == 403
    assert client.put("/contracts/c1", json=C, headers=hdr("svc", KEY_SVC)).status_code == 403
    assert client.get("/contracts").json() == []
    assert client.put("/contracts/c1", json=C, headers=hdr("don", KEY_DON)).status_code == 200
    assert len(client.get("/contracts").json()) == 1
