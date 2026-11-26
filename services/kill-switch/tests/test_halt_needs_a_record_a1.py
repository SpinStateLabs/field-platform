"""A listed operator must not be able to halt an agent while the ledger takes no row for it.

The reproduction: an id over the ledger's 200-character ``agent_id`` bound that reads agent X. Before the id rule, the
kill authorised on X, the registry write was refused, the halt signal went to X's own endpoint and every row was refused
(422), leaving nothing in the ledger. The stubs here stand for that chain. This file imports nothing the fix added, so
it runs, and fails, on the code before it.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import httpx
import yaml
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import LedgerUnreachableError, RegistryUnreachableError
from field_core.templates_api import template_data
from kill_switch.api import create_app

KEY_DON = "tkv-adon-key-0123456789abcdef"


class RefusingLedger:
    def __init__(self):
        self.attempts = []

    def append(self, event_type, payload, agent_id=None):
        self.attempts.append((event_type, agent_id))
        raise LedgerUnreachableError("ledger append returned 422", status_code=422)


class RegistryAnsweringX:
    """Every read answers agent X; every write is refused."""

    def __init__(self, record):
        self.record = record
        self.reads = []
        self.writes = []

    def get_agent(self, agent_id):
        self.reads.append(agent_id)
        return dict(self.record)

    def list_agents(self, domain=None, status=None):
        return [dict(self.record)]

    def set_status(self, agent_id, status, **kw):
        self.writes.append((agent_id, status))
        raise RegistryUnreachableError("registry returned 403")


class Endpoint:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers=None, timeout=None):
        self.calls.append(url)
        return httpx.Response(200)


def test_an_over_long_id_that_reads_x_sends_no_signal(tmp_path, monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(name, raising=False)
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
                                "scopes": ["kill"]}]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "agent.host")
    data = template_data("default")
    data["agent"]["name"] = "agent-x"
    data["enforcement"]["kill_switch"].update(authorized_operators=["don"], endpoint="http://agent.host/halt",
                                              method="HTTP POST")
    manifest = tmp_path / "agent-x.yaml"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    registry = RegistryAnsweringX({"agent_id": "agent-x", "status": "active", "domain": "ops",
                                   "manifest_ref": str(manifest)})
    ledger, endpoint = RefusingLedger(), Endpoint()
    client = TestClient(create_app(registry=registry, ledger=ledger, endpoint_client=endpoint))
    r = client.post("/kill/" + "a" * 201, json={"operator": "someone", "reason": "a1"},
                    headers={oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON})
    assert endpoint.calls == [], "a halt signal went out although no ledger row could be written"
    assert r.status_code == 422, (r.status_code, r.text)
    assert registry.reads == [] and registry.writes == [] and ledger.attempts == []
