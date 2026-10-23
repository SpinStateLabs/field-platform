"""Phase G: POST /agents/{id}/attest needs an authenticated operator."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa

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


class Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload, agent_id=None):
        self.events.append((event_type, payload))


@pytest.fixture()
def env(tmp_path):
    ledger = Ledger()
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=ledger))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    return c, ledger


ATT = {"attested_by": "Don Hagell"}


def attested(c):
    return c.get("/agents/a1").json()["attested_at"]


def test_off_by_default(env):
    c, _ = env
    assert c.post("/agents/a1/attest", json=ATT).status_code == 200


def test_attest_refusals_leave_the_clock_untouched(env, enforce):
    c, ledger = env
    before = attested(c)
    assert c.post("/agents/a1/attest", json=ATT).status_code == 401
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", "fok_wrong")).status_code == 403
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_SVC)).status_code == 403
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("svc", KEY_SVC)).status_code == 403
    assert attested(c) == before
    assert [e for e in ledger.events if e[0] == "registry.attested"] == []


def test_attest_with_key_records_the_authenticated_id(env, enforce):
    c, ledger = env
    assert c.post("/agents/a1/attest", json=ATT, headers=hdr("don", KEY_DON)).status_code == 200
    payload = [p for t, p in ledger.events if t == "registry.attested"][0]
    assert payload["operator_id_authenticated"] == "don"
    assert payload["attested_by"] == "Don Hagell"
