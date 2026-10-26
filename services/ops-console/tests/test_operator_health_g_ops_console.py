"""Phase G Stage 0, health slice, ops-console: C-8 /health operator block (the
console holds no identity: identity_present false), C-16 operator.refused
under ENFORCE when the console refuses a human action that carries no
operator headers. The record goes to the ledger over the console's ledger
client (x-field-auth only, C-14), never with a key.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from ops_console.api import ServiceClient, create_app

KEY_DON = "tkv-cdon-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
BODY = {"operator": "Don", "reason": "r"}


class Rec:
    def __init__(self):
        self.calls = []

    def post(self, path, **kw):
        self.calls.append((path, kw))

        class R:
            status_code = 201

            def json(self):
                return {"ok": True}

        return R()

    def get(self, path, **kw):
        raise ConnectionError("n/a")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def registry_file(tmp_path):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
             "scopes": ["*"]}]
    p = tmp_path / "operators.json"
    raw = json.dumps(rows).encode()
    p.write_bytes(raw)
    return p, raw


@pytest.fixture()
def console():
    ks, dg, led, other = Rec(), Rec(), Rec(), Rec()
    sc = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    app = create_app(registry=sc(other), ledger=sc(led), delegation=sc(dg),
                     governor=sc(other), killswitch=sc(ks), sentinel=sc(other))
    return TestClient(app), ks, dg, led


def refused(led):
    return [kw["json"] for path, kw in led.calls
            if path == "/events" and kw.get("json", {}).get("event_type") == "operator.refused"]


def test_health_carries_the_operator_block_with_flags_off(console):
    c = console[0]
    h = c.get("/health").json()
    assert OPERATOR_FIELDS <= set(h) and "manifests_unresolved" not in h
    assert h["operator_mode"] == "off" and h["identity_present"] is False
    assert h["operator_identity_id"] is None and h["service"] == "ops-console"


def test_health_reports_the_registry(console, registry_file, monkeypatch):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(registry_file[0]))
    h = console[0].get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(registry_file[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 1
    assert KEY_DON not in json.dumps(h) and oa.key_sha256(KEY_DON) not in json.dumps(h)


@pytest.mark.parametrize("path,body,action", [
    ("/api/agents/a1/kill", BODY, "kill"),
    ("/api/agents/a1/drill", BODY, "drill"),
    ("/api/tokens/t1/revoke", None, "revoke"),
])
def test_an_enforce_refusal_at_the_console_is_counted_and_ledgered(console, monkeypatch,
                                                                   path, body, action):
    c, ks, dg, led = console
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    r = c.post(path, json=body) if body is not None else c.post(path)
    assert r.status_code == 401 and ks.calls == [] and dg.calls == []
    rec = refused(led)
    assert len(rec) == 1
    p = rec[0]["payload"]
    assert (p["action"], p["path"], p["reason"], p["claimed_id"]) == (
        action, path, "no_credential", None)
    assert "headers" not in led.calls[0][1]               # x-field-auth only (C-14)
    assert c.get("/health").json()["refused_count"] == 1


def test_a_malformed_header_refusal_is_ledgered_under_enforce(console, monkeypatch):
    c, ks, _, led = console
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    r = c.post("/api/agents/a1/kill", json=BODY, headers={oa.HEADER_OPERATOR: "bad id"})
    assert r.status_code == 400 and ks.calls == []
    assert refused(led)[0]["payload"]["reason"] == "malformed_credential"


def test_off_mode_writes_no_refusal(console):
    c, ks, _, led = console
    assert c.post("/api/agents/a1/kill", json=BODY).status_code == 200
    assert refused(led) == [] and c.get("/health").json()["refused_count"] == 0
