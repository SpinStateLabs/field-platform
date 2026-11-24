"""S8-16 — GrantorRow.max_ttl_days has an upper bound (3650 days, ten years). A hand-edited row above
it is refused at load, so a mint answers the existing 503 'DOA roster unavailable' naming the row
instead of an OverflowError 500 from timedelta(days=N) (N above 999999999)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.doa import MAX_TTL_DAYS, DoaRosterError, load_roster
from delegation_authority.store import TokenStore
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
GRANTOR = "Don Hagell, Spin State Labs"
SCOPE = ["read timesheets", "draft invoices", "send invoice email"]


def _roster(tmp_path: Path, ttl) -> Path:
    row = {"grantor": GRANTOR, "allowed_scope": list(SCOPE), "max_ttl_days": ttl,
           "max_spend_usd": 500.0, "active": True}
    path = tmp_path / "doa-roster.yaml"
    path.write_text(yaml.safe_dump({"grantors": [row]}, sort_keys=False), encoding="utf-8")
    return path


def _client(tmp_path: Path, monkeypatch, ttl) -> TestClient:
    manifest = tmp_path / "agent-manifest.yaml"
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["identity"]["principal"] = GRANTOR
    data["delegation"]["granted_by"] = GRANTOR
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2099-06-30"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(_roster(tmp_path, ttl)))
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    assert registry.post("/agents", json={"agent_id": AGENT_ID, "name": "Invoicing", "owner": GRANTOR,
                                          "domain": "finance", "manifest_ref": str(manifest)}).status_code == 201
    return TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")), raise_server_exceptions=False)


def _mint(client, ttl_seconds=86400):
    return client.post("/tokens", json={"agent_id": AGENT_ID, "granted_by": GRANTOR, "scope": [SCOPE[0]],
                                        "ttl_seconds": ttl_seconds})


def test_the_bound_is_ten_years():
    assert MAX_TTL_DAYS == 3650


@pytest.mark.parametrize("ttl", [10**9, 10**9 + 1, 10**18, 3651])
def test_a_row_above_the_bound_is_refused_at_load_naming_the_field(tmp_path, ttl):
    with pytest.raises(DoaRosterError, match="max_ttl_days"):
        load_roster(_roster(tmp_path, ttl))


@pytest.mark.parametrize("ttl", [1, 30, 3650])
def test_a_row_at_or_under_the_bound_loads(tmp_path, ttl):
    assert load_roster(_roster(tmp_path, ttl)).grantors[0].max_ttl_days == ttl


@pytest.mark.parametrize("ttl", [10**9, 10**9 + 1])
def test_a_mint_under_a_huge_row_is_the_existing_503_not_a_500(tmp_path, monkeypatch, ttl):
    r = _mint(_client(tmp_path, monkeypatch, ttl))
    assert r.status_code == 503, r.text
    assert "DOA roster unavailable" in str(r.json()["detail"])


def test_a_mint_under_a_row_at_the_bound_still_works(tmp_path, monkeypatch):
    assert _mint(_client(tmp_path, monkeypatch, 3650)).status_code == 201


def test_a_mint_over_a_normal_row_is_still_the_403_d_grantor(tmp_path, monkeypatch):
    r = _mint(_client(tmp_path, monkeypatch, 1), ttl_seconds=2 * 86400)
    assert r.status_code == 403 and r.json()["detail"]["clause_id"] == "D.grantor"
