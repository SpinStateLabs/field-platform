"""Phase G: spend-governor caps / rate-limits / policies / escalation resolve are operator writes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

KEY_DON = "fok_don-key-0123456789abcdef"
KEY_SVC = "fok_svc-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


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


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=GovernorStore(tmp_path / "g.sqlite3")))


CAP = {"agent_id": "a1", "limit_cents": 100}
POLICY = {"agent_id": "a1", "allowed_models": ["claude-opus-4-1"]}


def test_off_by_default(client):
    assert client.put("/caps/a1", json=CAP).status_code == 200


@pytest.mark.parametrize("method,path,body", [
    ("put", "/caps/a1", CAP), ("put", "/policies/a1", POLICY),
    ("put", "/rate-limits/a1", {"agent_id": "a1", "limits": []}),
    ("post", "/escalations/e1/resolve", {"resolved_by": "x"}),
])
def test_refusals_leave_state_untouched(client, enforce, method, path, body):
    call = getattr(client, method)
    assert call(path, json=body).status_code == 401
    assert call(path, json=body, headers=hdr("don", "fok_wrong")).status_code == 403
    assert call(path, json=body, headers=hdr("svc", KEY_SVC)).status_code == 403
    assert client.get("/caps/a1").status_code == 404


def test_authorised_cap_write(client, enforce):
    assert client.put("/caps/a1", json=CAP, headers=hdr("don", KEY_DON)).status_code == 200
    assert client.get("/caps/a1").json()["limit_cents"] == 100
