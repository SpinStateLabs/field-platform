"""Phase G Stage 0, health slice, kill-switch: C-8 /health operator block
including manifests_unresolved (the B-8 manifest gate), C-16 operator.refused
under ENFORCE for guard refusals and authorized_operators refusals.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import hashlib
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import AgentNotRegisteredError
from field_core.templates_api import template_data
from kill_switch.api import create_app

KEY_DON = "tkv-kdon-key-0123456789abcdef"
KEY_OTHER = "tkv-koth-key-0123456789abcdef"
KEY_OWN = "tkv-kown-key-0123456789abcdef"
OPERATOR_FIELDS = {
    "operator_mode", "operator_registry_sha256_prefix", "operator_registry_rows",
    "operator_identity_id", "identity_present", "last_registry_error",
    "dropped_unauthenticated_records", "refused_count", "dropped_refused_records",
}
BODY = {"operator": "Don", "reason": "health-test"}


class Ledger:
    def __init__(self):
        self.rows = []
        self.agent_ids = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, dict(payload)))
        self.agent_ids.append(agent_id)

    def of(self, t):
        return [p for et, p in self.rows if et == t]


class Registry:
    def __init__(self, agents, fail=False):
        self.agents = {a["agent_id"]: dict(a) for a in agents}
        self.fail = fail

    def get_agent(self, agent_id):
        if agent_id not in self.agents:
            raise AgentNotRegisteredError(agent_id)
        return dict(self.agents[agent_id])

    def list_agents(self, domain=None, status=None):
        if self.fail:
            raise RuntimeError("registry down")
        return [dict(a) for a in self.agents.values()
                if (status is None or a["status"] == status)
                and (domain is None or a.get("domain") == domain)]

    def set_status(self, agent_id, status):
        self.agents[agent_id]["status"] = status
        return dict(self.agents[agent_id])


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


def _manifest(tmp_path, name, authorized=None, ok=True):
    path = tmp_path / f"{name}.yaml"
    if not ok:
        path.write_text("agent: [broken\n", encoding="utf-8")
        return str(path)
    data = template_data("default")
    data["agent"]["name"] = name
    if authorized is not None:
        data["enforcement"]["kill_switch"]["authorized_operators"] = authorized
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(path)


@pytest.fixture()
def registry_file(tmp_path):
    rows = [{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
             "scopes": ["*"], "names": ["Don Hagell"]},
            {"operator_id": "other", "key_sha256": oa.key_sha256(KEY_OTHER),
             "status": "active", "scopes": ["*"]}]
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
    agents = [
        {"agent_id": "a1", "status": "active", "domain": "finance",
         "manifest_ref": _manifest(tmp_path, "a1", authorized=["Don Hagell"])},
        {"agent_id": "a2", "status": "active", "domain": "finance", "manifest_ref": None},
        {"agent_id": "a3", "status": "killed", "domain": "finance",
         "manifest_ref": str(tmp_path / "gone.yaml")},
        {"agent_id": "a4", "status": "active", "domain": "finance",
         "manifest_ref": _manifest(tmp_path, "a4", ok=False)},
        {"agent_id": "a5", "status": "retired", "domain": "finance",
         "manifest_ref": str(tmp_path / "also-gone.yaml")},
    ]
    reg, led = Registry(agents), Ledger()
    return TestClient(create_app(registry=reg, ledger=led)), reg, led


def test_health_carries_the_operator_block_with_flags_off(env):
    c, _, _ = env
    h = c.get("/health").json()
    assert OPERATOR_FIELDS | {"manifests_unresolved"} <= set(h)
    assert h["operator_mode"] == "off" and h["manifests_unresolved"] is None
    assert h["service"] == "kill-switch" and h["ok"] is True


def test_health_reports_registry_identity_and_unresolved_manifests(env, log_only, tmp_path,
                                                                   monkeypatch):
    kf = tmp_path / "svc.key"
    kf.write_text(KEY_OWN, encoding="utf-8")
    monkeypatch.setenv(oa.ENV_OPERATOR, "svc-killswitch")
    monkeypatch.setenv(oa.ENV_OPERATOR_KEY_FILE, str(kf))
    c, _, _ = env
    h = c.get("/health").json()
    assert h["operator_registry_sha256_prefix"] == hashlib.sha256(log_only[1]).hexdigest()[:16]
    assert h["operator_registry_rows"] == 2
    assert h["operator_identity_id"] == "svc-killswitch" and h["identity_present"] is True
    # a3 (killed, missing) and a4 (active, invalid); a2 has no ref; a5 is retired
    assert h["manifests_unresolved"] == 2
    body = json.dumps(h)
    for k in (KEY_DON, KEY_OTHER, KEY_OWN):
        assert k not in body and oa.key_sha256(k) not in body


def test_manifests_unresolved_is_null_when_the_registry_cannot_list(env, log_only):
    c, reg, _ = env
    reg.fail = True
    h = c.get("/health").json()
    assert h["ok"] is True and h["manifests_unresolved"] is None


def test_enforce_guard_refusals_are_counted_and_ledgered(env, enforce):
    c, reg, led = env
    assert c.post("/kill/a1", json=BODY).status_code == 401
    assert c.post("/revive/a3", json=BODY, headers=hdr("don", "tkv-wrong-00000")).status_code == 403
    assert reg.agents["a1"]["status"] == "active"
    rec = led.of("operator.refused")
    assert [(p["action"], p["path"], p["reason"], p["claimed_id"]) for p in rec] == [
        ("kill", "/kill/a1", "no_credential", None),
        ("revive", "/revive/a3", "forbidden", "don")]
    assert "tkv-wrong-00000" not in json.dumps(led.rows)
    assert c.get("/health").json()["refused_count"] == 2


@pytest.mark.parametrize("route,action", [("/kill/a1", "kill"), ("/drill/a1", "drill")])
def test_an_authorized_operators_refusal_is_counted_and_ledgered(env, enforce, route, action):
    c, reg, led = env
    r = c.post(route, json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 403 and reg.agents["a1"]["status"] == "active"
    rec = led.of("operator.refused")
    assert len(rec) == 1
    assert (rec[0]["action"], rec[0]["path"], rec[0]["reason"], rec[0]["claimed_id"]) == (
        action, f"/{action}/a1", "forbidden", "other")
    assert led.agent_ids == ["a1"]
    assert c.get("/health").json()["refused_count"] == 1


def test_an_unresolvable_manifest_refusal_is_ledgered_as_unavailable(env, enforce):
    c, reg, led = env
    r = c.post("/kill/a4", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 503 and reg.agents["a4"]["status"] == "active"
    assert led.of("operator.refused")[0]["reason"] == "unavailable"
