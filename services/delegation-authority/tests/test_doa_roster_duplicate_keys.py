"""S12-10: a repeated key in the DOA roster is refused naming the key and line (never the value); a boolean is not a
number. A bad roster makes the mint answer 503 before any ledger write."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.doa import DoaRosterError, load_roster
from delegation_authority.store import TokenStore
from field_core.templates_api import template_data
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
GRANTOR = "Don Hagell, Spin State Labs"
SCOPE = ["read timesheets", "draft invoices"]

ROW = (f"  - grantor: {GRANTOR}\n    allowed_scope: [read timesheets, draft invoices]\n    max_ttl_days: 30\n"
       "    max_spend_usd: 500.0\n    active: true\n")
CLEAN = "grantors:\n" + ROW
TOP_DUP = "grantors:\n" + ROW + "grantors:\n" + ROW
ROW_DUP = "grantors:\n" + ROW + "    active: false\n"
SCOPE_DUP_ITEMS = ("grantors:\n  - grantor: g\n    allowed_scope: [a, a, b]\n    max_ttl_days: 5\n    active: true\n")


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "doa.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_a_clean_roster_loads(tmp_path):
    assert load_roster(_write(tmp_path, CLEAN)).find(GRANTOR).active is True


def test_a_top_level_duplicate_is_refused_naming_key_and_line(tmp_path):
    with pytest.raises(DoaRosterError, match=r"duplicate key 'grantors' at line 7"):
        load_roster(_write(tmp_path, TOP_DUP))


def test_a_duplicate_inside_one_row_is_refused_and_does_not_reactivate(tmp_path):
    with pytest.raises(DoaRosterError, match=r"duplicate key 'active'") as e:
        load_roster(_write(tmp_path, ROW_DUP))
    assert "false" not in str(e.value).lower().replace("duplicate key", "")


def test_repeated_list_items_are_not_duplicate_keys(tmp_path):
    assert load_roster(_write(tmp_path, SCOPE_DUP_ITEMS)).grantors[0].grantor == "g"


@pytest.mark.parametrize("line", ["max_ttl_days: yes", "max_spend_usd: on"])
def test_a_boolean_is_not_a_number(tmp_path, line):
    key = line.split(":")[0]
    text = CLEAN.replace(f"    {key}: " + ("30" if key == "max_ttl_days" else "500.0"), f"    {line}")
    assert line in text
    with pytest.raises(DoaRosterError, match=key):
        load_roster(_write(tmp_path, text))


def _client(tmp_path, monkeypatch, text):
    manifest = tmp_path / "agent-manifest.yaml"
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["identity"]["principal"] = GRANTOR
    data["delegation"]["granted_by"] = GRANTOR
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2099-06-30"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(_write(tmp_path, text)))
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    assert registry.post("/agents", json={"agent_id": AGENT_ID, "name": "Invoicing", "owner": GRANTOR,
                                          "domain": "finance", "manifest_ref": str(manifest)}).status_code == 201
    app = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")), raise_server_exceptions=False)
    return app, ledger


@pytest.mark.parametrize("text", [TOP_DUP, ROW_DUP])
def test_the_mint_answers_503_before_any_ledger_write(tmp_path, monkeypatch, text):
    app, ledger = _client(tmp_path, monkeypatch, text)
    before = len(ledger.get("/events").json())
    r = app.post("/tokens", json={"agent_id": AGENT_ID, "granted_by": GRANTOR, "scope": [SCOPE[0]],
                                  "ttl_seconds": 86400})
    assert r.status_code == 503
    assert len(ledger.get("/events").json()) == before
