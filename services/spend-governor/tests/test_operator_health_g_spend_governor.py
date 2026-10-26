"""Phase G Stage 0, health slice, spend-governor: C-8 /health operator block,
C-9 ledger_getter on the guards (LOG-ONLY operator.unauthenticated is actually
written), C-16 operator.refused under ENFORCE.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from spend_governor.api import create_app
from spend_governor.core import GovernorStore

KEY_DON = "tkv-gdon-key-0123456789abcdef"
KEY_SVC = "tkv-gsvc-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
CAP = {"agent_id": "a1", "limit_cents": 100}


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, dict(payload)))

    def of(self, t):
        return [p for et, p in self.rows if et == t]


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
def env(tmp_path):
    led = Ledger()
    return TestClient(create_app(store=GovernorStore(tmp_path / "g.sqlite3"), ledger=led)), led


def test_health_carries_the_operator_block_with_flags_off(env):
    c, _ = env
    h = c.get("/health").json()
    assert OPERATOR_FIELDS <= set(h) and "manifests_unresolved" not in h
    assert h["operator_mode"] == "off" and h["service"] == "spend-governor"


def test_health_reports_the_registry_the_guards_read(env, log_only):
    c, _ = env
    h = c.get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(log_only[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 2 and h["operator_mode"] == "log-only"
    assert KEY_DON not in json.dumps(h) and oa.key_sha256(KEY_DON) not in json.dumps(h)


@pytest.mark.parametrize("method,path,body,action", [
    ("put", "/caps/a1", CAP, "caps"),
    ("post", "/escalations/e1/resolve", {"resolved_by": "x"}, "escalation"),
])
def test_log_only_unauthenticated_writes_are_ledgered(env, log_only, method, path, body, action):
    """C-9: the guard has a ledger, so the LOG-ONLY evidence row exists."""
    c, led = env
    getattr(c, method)(path, json=body)
    rec = led.of("operator.unauthenticated")
    assert rec and rec[-1]["action"] == action and rec[-1]["reason"] == "no_credential"


def test_enforce_refusals_are_counted_and_ledgered(env, enforce):
    c, led = env
    assert c.put("/caps/a1", json=CAP).status_code == 401
    assert c.put("/caps/a1", json=CAP, headers=hdr("svc", KEY_SVC)).status_code == 403
    rec = led.of("operator.refused")
    assert [(p["action"], p["path"], p["reason"], p["claimed_id"]) for p in rec] == [
        ("caps", "/caps/a1", "no_credential", None), ("caps", "/caps/a1", "forbidden", "svc")]
    assert KEY_SVC not in json.dumps(led.rows)
    assert c.get("/health").json()["refused_count"] == 2
    assert c.put("/caps/a1", json=CAP, headers=hdr("don", KEY_DON)).status_code == 200
