"""attestation-reporter tests: sourced numbers, unavailable ≠ zero, HTML."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from attestation_reporter.engine import Metric, PackEngine
from attestation_reporter.render import render_html
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

# Real now, not a fixed date: the delegation service timestamps with real
# time, so a frozen NOW makes minted tokens expire as the calendar advances.
# Every other date in this file is an offset from NOW — still deterministic.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def stack(tmp_path):
    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        )
    )
    governor = TestClient(
        create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3"))
    )

    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Inv",
                                   "owner": "AP Lead", "domain": "finance"})
    registry.post("/agents", json={"agent_id": "crm-agent", "name": "CRM",
                                   "owner": "RevOps", "domain": "sales"})
    registry.patch("/agents/crm-agent", json={"status": "killed"})

    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller",
        "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})
    # a second token, revoked — proves revoked/expiring are computed from
    # the real token list, not the list's length
    revoked_token = delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller",
        "scope": ["read timesheets"],
        "expires_at": (NOW + timedelta(days=5)).isoformat()}).json()
    delegation.post(f"/tokens/{revoked_token['token_id']}/revoke")

    for event_type in ("conformance.allow", "conformance.allow",
                       "conformance.allow", "conformance.block",
                       "conformance.escalate", "kill.agent"):
        ledger.post("/events", json={"event_type": event_type,
                                     "agent_id": "invoicing-agent",
                                     "payload": {}})

    return PackEngine(
        registry=registry, ledger=ledger, delegation=delegation,
        governor=governor,
    )


def test_every_number_has_a_source(stack):
    pack = stack.build(period="Q3 2026", now=NOW)
    for metric in pack.all_metrics():
        assert metric.source_query.strip(), f"{metric.name} lacks a source query"
        assert metric.source_query.startswith("GET "), metric.name


def test_pack_numbers_match_staged_state(stack):
    pack = stack.build(period="Q3 2026", now=NOW)
    by_name = {m.name: m for m in pack.all_metrics()}

    assert by_name["Agents registered"].value == 2
    assert by_name["Agents in production (active)"].value == 1
    assert by_name["Agents currently killed"].value == 1

    # 4 allow (3 staged + 1 delegation.mint? no — mint is delegation.mint;
    # allows are exactly the 3 staged)
    assert by_name["Conformance ALLOW verdicts"].value == 3
    assert by_name["Conformance BLOCK verdicts"].value == 1
    assert by_name["Conformance ESCALATE verdicts"].value == 1
    conformance = by_name["Conformance rate (ALLOW / all verdicts)"]
    assert conformance.value == 60.0  # 3/5
    assert "3 / (3+1+1)" in conformance.note

    assert by_name["Kill-switch activations"].value == 1
    assert by_name["Delegation tokens issued (all time)"].value == 2
    # the revoked token is excluded from expiring even though it lapses in 5 d
    assert by_name["Authorities expiring within 30 days"].value == 1
    assert by_name["Tokens revoked (all time)"].value == 1
    assert by_name["Ledger chain integrity"].value == "INTACT"


def test_adversarial_unavailable_service_never_fabricates_zero(stack):
    """Governor down ⇒ 'unavailable', not a fake 0 the board would trust."""
    stack.governor = None
    pack = stack.build(now=NOW)
    spend = next(m for m in pack.all_metrics()
                 if m.name == "Open spend escalations (human queue)")
    assert spend.status == "unavailable"
    assert spend.value is None
    assert spend.source_query.startswith("GET ")  # the failed query still shown


def test_metric_model_enforces_the_rule():
    with pytest.raises(Exception):
        Metric(name="x", value=5, source_query="")       # number without source
    with pytest.raises(Exception):
        Metric(name="x", value=5, source_query="GET /y",
               status="unavailable")                     # unavailable with value
    with pytest.raises(Exception):
        Metric(name="x", source_query="GET /y")          # ok without value


def test_html_renders_values_and_queries(stack):
    pack = stack.build(period="Q3 2026", now=NOW)
    html = render_html(pack)
    assert "FIELD governance board pack" in html
    assert "No number without a source." in html
    assert "GET http://testserver/agents?status=active" in html or "GET http" in html
    assert "INTACT" in html
    assert "60.0" in html


def test_broken_ledger_shows_in_pack(stack, tmp_path):
    """A tampered chain must surface as BROKEN in the board pack."""
    import json as jsonlib

    # find the events file the stack fixture created
    events_files = list(tmp_path.glob("events.jsonl"))
    assert events_files
    path = events_files[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = jsonlib.loads(lines[1])
    rec["payload"] = {"tampered": True}
    lines[1] = jsonlib.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # fresh ledger app over the tampered file
    tampered_ledger = TestClient(create_ledger_app(store=LedgerStore(path)))
    stack.ledger = tampered_ledger
    pack = stack.build(now=NOW)
    integrity = next(m for m in pack.all_metrics()
                     if m.name == "Ledger chain integrity")
    assert str(integrity.value).startswith("BROKEN")
