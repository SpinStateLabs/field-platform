"""attestation-reporter API tests (A2): the pack served = the pack rendered.

The served pack is an UNSIGNED, all-time draft until C4: no window (since/
until ⇒ 422, never silently all-time), no signer, no signature. Every data
route is behind x-field-auth; only /health is open.

The `stack` fixture is a copy of the one in test_attestation_reporter.py
(not imported: that file stays unmodified and self-contained).
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from attestation_reporter import __version__
from attestation_reporter.api import WINDOW_NOT_SUPPORTED, create_app, engine_from_env
from attestation_reporter.engine import BoardPack, PackEngine
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.authn import ENV_VAR, HEADER
from field_core.clients import LedgerClient, RegistryClient
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

# Real now, not a fixed date: the delegation service timestamps with real
# time, so a frozen NOW makes minted tokens expire as the calendar advances.
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


@pytest.fixture()
def api(stack, monkeypatch):
    """The served app over the stack; authn off unless a test sets the secret."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    return TestClient(create_app(engine=stack))


# --- liveness + authn ------------------------------------------------------

def test_health_open_and_names_the_service(api, monkeypatch):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "service": "attestation-reporter",
                        "version": __version__}
    # still open once a secret is set (liveness must stay probeable)
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    assert api.get("/health").status_code == 200


def test_pack_routes_401_without_header_when_secret_set(api, monkeypatch):
    """Both data routes are protected — /pack.html has NO open_paths carve-out:
    it prints every number, so a browser that cannot present the header is
    refused rather than shown the pack."""
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")
    assert api.get("/pack").status_code == 401
    assert api.get("/pack.html").status_code == 401
    assert api.get("/pack", headers={HEADER: "wrong"}).status_code == 401
    assert api.get("/pack", headers={HEADER: "s3cret-demo-only"}).status_code == 200
    assert api.get("/pack.html", headers={HEADER: "s3cret-demo-only"}).status_code == 200


# --- the pack served = the pack rendered ------------------------------------

def _by_name(pack: dict) -> dict:
    return {m["name"]: m for s in pack["sections"] for m in s["metrics"]}


def test_pack_json_matches_staged_state(api, stack):
    r = api.get("/pack", params={"period": "Q3 2026"})
    assert r.status_code == 200
    body = r.json()
    served = BoardPack.model_validate(body)  # the wire shape IS the model
    assert served.period == "Q3 2026"
    assert served.org == "Spin State Labs"

    by_name = _by_name(body)
    # the same numbers test_pack_numbers_match_staged_state expects of render
    assert by_name["Agents registered"]["value"] == 2
    assert by_name["Agents in production (active)"]["value"] == 1
    assert by_name["Agents currently killed"]["value"] == 1
    assert by_name["Conformance ALLOW verdicts"]["value"] == 3
    assert by_name["Conformance BLOCK verdicts"]["value"] == 1
    assert by_name["Conformance ESCALATE verdicts"]["value"] == 1
    assert by_name["Shadow BLOCK verdicts (log-only, not enforced)"]["value"] == 0
    assert by_name["Shadow ESCALATE verdicts (log-only, not enforced)"]["value"] == 0
    conformance = by_name["Conformance rate (ALLOW / all verdicts incl. shadow)"]
    assert conformance["value"] == 60.0  # 3/5
    assert "3 / (3+1+1+0+0)" in conformance["note"]
    assert by_name["Kill-switch activations"]["value"] == 1
    assert by_name["Delegation tokens issued (all time)"]["value"] == 2
    assert by_name["Authorities expiring within 30 days"]["value"] == 1
    assert by_name["Tokens revoked (all time)"]["value"] == 1
    assert by_name["Ledger chain integrity"]["value"] == "INTACT"

    # the rule survives the wire: every metric carries its literal GET query
    for m in served.all_metrics():
        assert m.source_query.startswith("GET "), m.name

    # and metric-for-metric it is what `attest render` would have written
    # over the same engine (generated_at differs; nothing else may)
    rendered = stack.build(period="Q3 2026")
    key = lambda m: (m.name, m.value, m.unit, m.status, m.source_query, m.note)  # noqa: E731
    assert [key(m) for m in served.all_metrics()] == [key(m) for m in rendered.all_metrics()]
    assert [s.title for s in served.sections] == [s.title for s in rendered.sections]


def test_pack_org_query_overrides_engine_org_per_request(api):
    assert api.get("/pack", params={"org": "Acme Corp"}).json()["org"] == "Acme Corp"
    # the override never leaks into the shared engine
    assert api.get("/pack").json()["org"] == "Spin State Labs"
    assert "Acme Corp" in api.get("/pack.html", params={"org": "Acme Corp"}).text


def test_pack_window_params_422_until_c4(api):
    """ADVERSARIAL: a caller asking for a window must be refused, never handed
    all-time counts labeled as if they were the window. To be replaced in C4."""
    for params in ({"since": "2026-07-01"}, {"until": "2026-09-30"},
                   {"since": "2026-07-01", "until": "2026-09-30"},
                   {"period": "Q3 2026", "since": "2026-07-01"}):
        r = api.get("/pack", params=params)
        assert r.status_code == 422, params
        assert "C4" in r.json()["detail"], params
        assert "period, org" in r.json()["detail"]
        assert "sections" not in r.text  # no pack body rides along with the refusal
    assert r.json()["detail"] == WINDOW_NOT_SUPPORTED
    html = api.get("/pack.html", params={"since": "2026-07-01"})
    assert html.status_code == 422
    assert "C4" in html.json()["detail"]


def test_pack_html_is_html_with_the_rule(api):
    r = api.get("/pack.html", params={"period": "Q3 2026"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "FIELD governance board pack" in r.text
    assert "No number without a source." in r.text
    assert "Q3 2026" in r.text
    assert "INTACT" in r.text
    assert "60.0" in r.text


# --- unavailable ≠ zero, through the served app ----------------------------

class _Unreachable:
    """An httpx-like client whose upstream is down (connection refused)."""

    def get(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")


def test_governor_unreachable_served_metric_unavailable_not_zero(stack, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    stack.governor = _Unreachable()
    api = TestClient(create_app(engine=stack))

    body = api.get("/pack").json()
    spend = _by_name(body)["Open spend escalations (human queue)"]
    assert spend["status"] == "unavailable"
    assert spend["value"] is None
    assert spend["source_query"].startswith("GET ")
    # the other upstreams are untouched — a dead governor never blanks the pack
    assert _by_name(body)["Agents registered"]["value"] == 2

    html = api.get("/pack.html").text
    assert "unavailable" in html
    assert "Open spend escalations (human queue)" in html


# --- the default engine is the CLI's engine --------------------------------

def test_default_engine_reads_the_four_env_urls_and_attaches_auth(monkeypatch):
    monkeypatch.setenv("FIELD_REGISTRY_URL", "http://reg.test:8001")
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://led.test:8002")
    monkeypatch.setenv("FIELD_DELEGATION_URL", "http://del.test:8003")
    monkeypatch.setenv("FIELD_GOVERNOR_URL", "http://gov.test:8006")
    monkeypatch.setenv(ENV_VAR, "s3cret-demo-only")

    app = create_app()  # no engine injected ⇒ built from the environment
    eng: PackEngine = app.state.engine
    assert (eng.registry_base, eng.ledger_base, eng.delegation_base, eng.governor_base) == (
        "http://reg.test:8001", "http://led.test:8002",
        "http://del.test:8003", "http://gov.test:8006",
    )
    for client, base in ((eng.registry, eng.registry_base), (eng.ledger, eng.ledger_base),
                         (eng.delegation, eng.delegation_base),
                         (eng.governor, eng.governor_base)):
        assert isinstance(client, httpx.Client)
        assert str(client.base_url).rstrip("/") == base
        assert client.headers[HEADER] == "s3cret-demo-only"  # outbound calls carry it

    # and the CLI's builder is the very same function with the same defaults
    monkeypatch.delenv("FIELD_GOVERNOR_URL")
    assert engine_from_env(org="Acme").governor_base == "http://127.0.0.1:8006"
    assert engine_from_env(org="Acme").org == "Acme"
