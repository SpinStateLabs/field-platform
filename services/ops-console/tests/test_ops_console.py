"""ops-console tests: aggregation honesty, action proxying, authn split."""

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from ops_console.api import ServiceClient, create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore


def wrap(test_client) -> ServiceClient:
    return ServiceClient(client=test_client, base_url="http://t")


@pytest.fixture()
def stack(tmp_path):
    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(
        create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t")))
    governor = TestClient(
        create_governor_app(store=GovernorStore(tmp_path / "spend.sqlite3")))
    killswitch = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t")))

    console = TestClient(create_app(
        registry=wrap(registry), ledger=wrap(ledger),
        delegation=wrap(delegation), governor=wrap(governor),
        killswitch=wrap(killswitch),
        sentinel=wrap(killswitch),  # placeholder; /api/check tested via kill app? no —
    ))
    # sentinel not needed for most tests; overview never queries it.

    registry.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoicing",
        "owner": "AP Team Lead", "domain": "finance"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller",
        "scope": ["draft invoices"], "ttl_seconds": 3600})
    governor.put("/caps/invoicing-agent", json={
        "agent_id": "invoicing-agent", "limit_cents": 50_000,
        "period": "daily", "escalate_at_pct": 80})
    governor.post("/spend", json={"agent_id": "invoicing-agent", "cents": 41_000})
    return console, registry, ledger, delegation, governor


def test_overview_aggregates_live_state(stack):
    console, *_ = stack
    o = console.get("/api/overview").json()
    assert o["agents"]["available"] is True
    assert o["agents"]["data"][0]["agent_id"] == "invoicing-agent"
    assert o["tokens"]["available"] is True and len(o["tokens"]["data"]) == 1
    assert o["escalations"]["available"] is True
    assert len(o["escalations"]["data"]) == 1  # 82% threshold crossed
    assert o["ledger_verify"]["data"]["ok"] is True
    assert o["recent_events"]["available"] is True
    assert o["token_usage"]["available"] is True
    for section in ("agents", "tokens", "escalations", "ledger_verify",
                    "token_usage"):
        assert o[section]["source"].startswith("GET http")


def test_token_usage_surfaces_cost_and_rogue(stack):
    console, _, _, _, governor = stack
    # agent may only use Haiku; it reports Opus usage → rogue_model + cost.
    governor.put("/policies/invoicing-agent", json={
        "agent_id": "invoicing-agent", "allowed_models": ["claude-haiku-4-5"]})
    governor.post("/usage", json={
        "agent_id": "invoicing-agent", "model": "claude-opus-4-8",
        "input_tokens": 100000, "output_tokens": 50000})
    o = console.get("/api/overview").json()
    usage = o["token_usage"]["data"]
    row = next(u for u in usage if u["agent_id"] == "invoicing-agent")
    assert row["total_input_tokens"] == 100000
    assert row["total_cost_units"] > 0            # priced Opus cost
    assert row["open_rogue_flags"] >= 1           # off-list model flagged
    assert any(not m["allowed"] for m in row["by_model"])


def test_unavailable_service_is_marked_not_faked(tmp_path):
    """Aggregation honesty: a dead governor shows unavailable, not empty."""
    class Dead:
        def get(self, *a, **k):
            raise ConnectionError("down")
        def post(self, *a, **k):
            raise ConnectionError("down")

    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    ledger = TestClient(
        create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    console = TestClient(create_app(
        registry=wrap(registry), ledger=wrap(ledger),
        delegation=ServiceClient(client=Dead(), base_url="http://t"),
        governor=ServiceClient(client=Dead(), base_url="http://t"),
        killswitch=wrap(ledger), sentinel=wrap(ledger)))
    o = console.get("/api/overview").json()
    assert o["escalations"]["available"] is False
    assert o["escalations"]["data"] is None          # never a fake empty list
    assert o["escalations"]["error"]


def test_kill_and_revive_proxy_through_killswitch(stack):
    console, registry, ledger, *_ = stack
    r = console.post("/api/agents/invoicing-agent/kill",
                     json={"operator": "CISO via console", "reason": "test"})
    assert r.status_code == 200
    assert registry.get("/agents/invoicing-agent").json()["status"] == "killed"
    kills = ledger.get("/events", params={"event_type": "kill.agent"}).json()
    assert kills[0]["payload"]["operator"] == "CISO via console"

    console.post("/api/agents/invoicing-agent/revive",
                 json={"operator": "CISO via console", "reason": "test done"})
    assert registry.get("/agents/invoicing-agent").json()["status"] == "active"


def test_operator_is_mandatory_on_mutations(stack):
    console, *_ = stack
    r = console.post("/api/agents/invoicing-agent/kill",
                     json={"operator": "", "reason": "x"})
    assert r.status_code == 422  # nameless kills are not a thing


def test_token_revoke_and_escalation_resolve_proxy(stack):
    console, _, ledger, delegation, governor = stack
    token_id = delegation.get("/tokens").json()[0]["token_id"]
    assert console.post(f"/api/tokens/{token_id}/revoke").status_code == 200
    assert delegation.get(f"/tokens/{token_id}").json()["revoked"] is True

    esc_id = governor.get("/escalations").json()[0]["escalation_id"]
    r = console.post(f"/api/escalations/{esc_id}/resolve",
                     json={"resolved_by": "Controller via console"})
    assert r.status_code == 200
    assert governor.get("/escalations").json() == []


def test_escalation_resolve_through_console_keeps_the_first_resolver(stack):
    """spend-governor: first resolver wins. The console passes the same
    human's retry through as 200 and another human's resolve as 409, whose
    detail still names the first resolver."""
    console, *_, governor = stack
    esc_id = governor.get("/escalations").json()[0]["escalation_id"]
    path = f"/api/escalations/{esc_id}/resolve"
    first = console.post(path, json={"resolved_by": "Controller via console"})
    assert first.status_code == 200
    assert first.json()["resolved_by"] == "Controller via console"
    retry = console.post(path, json={"resolved_by": "Controller via console"})
    assert (retry.status_code, retry.json()) == (200, first.json())
    other = console.post(path, json={"resolved_by": "CFO via console"})
    assert other.status_code == 409
    assert other.json()["detail"] == first.json()
    assert governor.get("/escalations").json() == []


def test_proxy_surfaces_upstream_refusals(stack):
    console, *_ = stack
    r = console.post("/api/agents/ghost/kill",
                     json={"operator": "CISO", "reason": "x"})
    assert r.status_code == 404  # kill-switch's refusal passes through


def test_page_open_but_api_locked_when_secret_set(stack, monkeypatch):
    console, *_ = stack
    monkeypatch.setenv("FIELD_SHARED_SECRET", "s3cret")
    page = console.get("/")
    assert page.status_code == 200          # shell page holds no data
    assert "FIELD OPS CONSOLE" in page.text
    assert console.get("/api/overview").status_code == 401
    assert console.get(
        "/api/overview", headers={"x-field-auth": "s3cret"}
    ).status_code == 200
