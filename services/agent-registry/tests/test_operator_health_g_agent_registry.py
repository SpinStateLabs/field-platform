"""Phase G Stage 0, health slice, agent-registry: C-8 /health operator block
including manifests_unresolved (the registry resolves manifest_ref on status
PATCH), C-16 operator.refused under ENFORCE for guard refusals and for the
PATCH-status authorized_operators refusal.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore
from field_core import operator_auth as oa
from field_core.templates_api import template_data

KEY_DON = "tkv-rdon-key-0123456789abcdef"
KEY_SVC = "tkv-rsvc-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}


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


def _manifest(tmp_path, name, authorized):
    data = template_data("default")
    data["agent"]["name"] = name
    data["enforcement"]["kill_switch"]["authorized_operators"] = authorized
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture()
def registry_file(tmp_path):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
             "scopes": ["*"], "names": ["Don Hagell"]},
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
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3"), ledger=led))
    m1 = _manifest(tmp_path, "a1", ["Don Hagell"])
    m2 = _manifest(tmp_path, "a2", ["Don Hagell"])
    for aid, m in (("a1", m1), ("a2", m2), ("a3", None)):
        body = {"agent_id": aid, "name": aid, "owner": "O", "domain": "finance"}
        if m is not None:
            body["manifest_ref"] = str(m)
        assert c.post("/agents", json=body).status_code == 201
    return c, led, m2


def test_health_carries_the_operator_block_with_flags_off(env):
    c, _, _ = env
    h = c.get("/health").json()
    assert OPERATOR_FIELDS | {"manifests_unresolved"} <= set(h)
    assert h["operator_mode"] == "off" and h["manifests_unresolved"] is None
    assert h["agent_count"] == 3 and h["service"] == "agent-registry"


def test_health_reports_the_registry_and_unresolved_manifests(env, log_only):
    c, _, m2 = env
    h = c.get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(log_only[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 2 and h["manifests_unresolved"] == 0
    m2.unlink()                                   # a2's manifest disappears from this host
    assert c.get("/health").json()["manifests_unresolved"] == 1
    body = json.dumps(c.get("/health").json())
    assert KEY_DON not in body and oa.key_sha256(KEY_DON) not in body


def test_retired_agents_are_not_counted(env, log_only):
    c, _, m2 = env
    assert c.patch("/agents/a2", json={"status": "retired"}).status_code == 200
    m2.unlink()
    assert c.get("/health").json()["manifests_unresolved"] == 0


def test_enforce_guard_refusals_are_counted_and_ledgered(env, enforce):
    c, led, _ = env
    assert c.post("/agents/a1/attest", json={"attested_by": "Don"}).status_code == 401
    rec = led.of("operator.refused")
    assert [(p["action"], p["path"], p["reason"]) for p in rec] == [
        ("attest", "/agents/a1/attest", "no_credential")]
    assert c.get("/health").json()["refused_count"] == 1


def test_a_patch_status_refusal_is_counted_and_ledgered(env, enforce):
    c, led, _ = env
    # svc holds kill but is not on a1's authorized_operators
    r = c.patch("/agents/a1", json={"status": "killed"}, headers=hdr("svc", KEY_SVC))
    assert r.status_code == 403
    assert c.get("/agents/a1").json()["status"] == "active"
    r = c.patch("/agents/a1", json={"status": "killed"})
    assert r.status_code == 401
    rec = led.of("operator.refused")
    assert [(p["action"], p["path"], p["reason"], p["claimed_id"]) for p in rec] == [
        ("kill", "/agents/a1", "forbidden", "svc"), ("kill", "/agents/a1", "no_credential", None)]
    assert KEY_SVC not in json.dumps(led.rows)
    assert c.get("/health").json()["refused_count"] == 2
