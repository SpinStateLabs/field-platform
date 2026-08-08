"""Wires the real spine + governor + sentinel in-process for sentinel tests."""

import yaml
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from conformance_sentinel.api import create_app as create_sentinel_app
from conformance_sentinel.engine import (
    DelegationIntrospectClient,
    ManifestResolver,
    SentinelEngine,
    SpendStatusClient,
)
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

AGENT_ID = "invoicing-agent"
SCOPE = ["read timesheets", "draft invoices", "send invoice email"]


def build_manifest(tmp_path, **overrides):
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["agent"]["description"] = "Reads timesheets, drafts invoices"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = "http://127.0.0.1:8005/kill/invoicing-agent"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["escalation_triggers"] = ["send invoice"]
    data["enforcement"]["spend_cap"] = {
        "currency": "USD", "limit": 500, "period": "daily", "on_breach": "halt",
    }
    data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke",
    }
    data.update(overrides)
    path = tmp_path / "invoicing-agent.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


class Stack:
    def __init__(self, tmp_path):
        self.ledger_store = LedgerStore(tmp_path / "events.jsonl")
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
        )
        self.ledger = TestClient(create_ledger_app(store=self.ledger_store))
        self.delegation = TestClient(
            create_delegation_app(
                store=TokenStore(tmp_path / "tokens.sqlite3"),
                ledger=LedgerClient(client=self.ledger, base_url="http://t"),
                registry=RegistryClient(client=self.registry, base_url="http://t"),
            )
        )
        self.governor = TestClient(
            create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3"))
        )
        self.ledger_up = True
        self.manifest_path = build_manifest(tmp_path)

        engine = SentinelEngine(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            delegation=DelegationIntrospectClient(
                client=self.delegation, base_url="http://t"
            ),
            governor=SpendStatusClient(client=self.governor, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            ledger_health=lambda: self.ledger_up,
            manifests=ManifestResolver(manifest_dir=tmp_path),
        )
        self.sentinel = TestClient(create_sentinel_app(engine=engine))

        self.registry.post(
            "/agents",
            json={
                "agent_id": AGENT_ID,
                "name": "Invoice Drafting Copilot",
                "owner": "Controller, Spin State Labs",
                "domain": "finance",
                "manifest_ref": str(self.manifest_path),
            },
        )

    def mint_token(self, scope=None, ttl=3600):
        r = self.delegation.post(
            "/tokens",
            json={
                "agent_id": AGENT_ID,
                "granted_by": "Controller, Spin State Labs",
                "scope": scope or list(SCOPE),
                "ttl_seconds": ttl,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["token_id"]

    def set_cap(self, limit_cents=50_000):
        r = self.governor.put(
            f"/caps/{AGENT_ID}",
            json={"agent_id": AGENT_ID, "limit_cents": limit_cents,
                  "period": "daily", "escalate_at_pct": 80},
        )
        assert r.status_code == 200

    def check(self, action, token_id=None, irreversible=False):
        r = self.sentinel.post(
            "/check",
            json={"agent_id": AGENT_ID, "action": action,
                  "token_id": token_id, "irreversible": irreversible},
        )
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)
