"""Phase G Stage 0, health slice, federation-broker: C-8 /health operator
block, C-9 ledger_getter on the guard (LOG-ONLY operator.unauthenticated is
actually written), C-16 operator.refused under ENFORCE.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore
from field_core import operator_auth as oa

KEY_DON = "tkv-fdon-key-0123456789abcdef"
KEY_SVC = "tkv-fsvc-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
C = {"contract_id": "c1", "counterparty_org": "Acme", "allowed_scopes": ["read"],
     "allowed_data_classes": ["public"]}


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, dict(payload)))

    def of(self, t):
        return [p for et, p in self.rows if et == t]


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))


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
def env(tmp_path):
    led = Ledger()
    engine = BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=led)
    return TestClient(create_app(engine=engine)), led


def test_health_carries_the_operator_block_with_flags_off(env):
    c, _ = env
    h = c.get("/health").json()
    assert OPERATOR_FIELDS <= set(h) and "manifests_unresolved" not in h
    assert h["operator_mode"] == "off" and h["service"] == "federation-broker"


def test_health_reports_the_registry_the_guards_read(env, log_only):
    c, _ = env
    h = c.get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(log_only[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 2
    assert KEY_DON not in json.dumps(h) and oa.key_sha256(KEY_DON) not in json.dumps(h)


def test_log_only_unauthenticated_contract_write_is_ledgered(env, log_only):
    """C-9: the guard has a ledger (the engine's), so the LOG-ONLY row exists."""
    c, led = env
    assert c.put("/contracts/c1", json=C).status_code == 200
    rec = led.of("operator.unauthenticated")
    assert rec and rec[0]["action"] == "federation" and rec[0]["path"] == "/contracts/c1"


def test_enforce_refusals_are_counted_and_ledgered(env, enforce):
    c, led = env
    assert c.put("/contracts/c1", json=C).status_code == 401
    assert c.put("/contracts/c1", json=C, headers=hdr("don", "tkv-wrong-000000")).status_code == 403
    rec = led.of("operator.refused")
    assert [(p["action"], p["reason"], p["claimed_id"]) for p in rec] == [
        ("federation", "no_credential", None), ("federation", "forbidden", "don")]
    assert "tkv-wrong-000000" not in json.dumps(led.rows)
    assert c.get("/health").json()["refused_count"] == 2
