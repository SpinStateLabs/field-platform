"""v1.2 B4 — `tools/provision_ssl_agents.py` is a thin wrapper, and it works.

Two things are worth a test here:

1. the wrapper no longer does its own `PUT /caps` / `POST /tokens` — it goes
   through `lifecycle provision`, so the cap arithmetic and the mint refusals
   are the platform's, not a second copy that can drift;
2. its `probe` function — the part `lifecycle provision` has no opinion about
   — actually runs against a real stack: heartbeat, one sentinel check per
   granted action, and one action that was never granted, which must refuse.

The whole estate is in-process behind a tiny path-prefix router that stands
in for the single-port Caddy proxy.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest
import yaml
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
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

REPO = pathlib.Path(__file__).resolve().parents[3]
TOOL = REPO / "tools" / "provision_ssl_agents.py"

AGENT_ID = "ssl-invoicing-agent"
SCOPE = ["read timesheets", "draft invoices"]
NEVER = "send invoice email"


def _load_tool():
    spec = importlib.util.spec_from_file_location("provision_ssl_agents", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["provision_ssl_agents"] = module
    spec.loader.exec_module(module)
    return module


class Router:
    """Stands in for the Caddy single-port proxy: `http://t/<prefix>/<path>`
    is dispatched to the in-process app registered under `<prefix>`."""

    def __init__(self, apps: dict[str, TestClient]):
        self.apps = apps

    def _split(self, url: str):
        rest = url.split("http://t", 1)[1]
        parts = rest.lstrip("/").split("/", 1)
        prefix = parts[0]
        path = "/" + (parts[1] if len(parts) > 1 else "")
        return self.apps[prefix], path

    def get(self, url, **kw):
        client, path = self._split(url)
        return client.get(path, **kw)

    def post(self, url, **kw):
        client, path = self._split(url)
        return client.post(path, **kw)

    def put(self, url, **kw):
        client, path = self._split(url)
        return client.put(path, **kw)

    def patch(self, url, **kw):
        client, path = self._split(url)
        return client.patch(path, **kw)


def _manifest(tmp_path: pathlib.Path) -> pathlib.Path:
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["agent"]["description"] = "Reads timesheets, drafts invoices. SYNTHETIC."
    data["identity"]["principal"] = "Don Hagell, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = (
        f"http://127.0.0.1:8005/kill/{AGENT_ID}")
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["escalation_triggers"] = []
    data["enforcement"]["spend_cap"] = {
        "currency": "USD", "limit": 5, "period": "daily", "on_breach": "halt"}
    data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    data["delegation"]["granted_by"] = "Don Hagell, Spin State Labs"
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2030-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke"}
    path = tmp_path / f"{AGENT_ID}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture()
def estate(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path))
    manifest = _manifest(tmp_path)

    registry_store = RegistryStore(tmp_path / "agents.sqlite3")
    registry = TestClient(create_registry_app(store=registry_store))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")))
    governor = TestClient(create_governor_app(
        store=GovernorStore(tmp_path / "spend.sqlite3")))
    killswitch = TestClient(create_kill_app(
        registry=RegistryClient(client=registry, base_url="http://t"),
        ledger=LedgerClient(client=ledger, base_url="http://t")))
    sentinel = TestClient(create_sentinel_app(engine=SentinelEngine(
        registry=RegistryClient(client=registry, base_url="http://t"),
        delegation=DelegationIntrospectClient(
            client=delegation, base_url="http://t"),
        governor=SpendStatusClient(client=governor, base_url="http://t"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        ledger_health=lambda: True,
        manifests=ManifestResolver(manifest_dir=str(tmp_path)),
    )))

    router = Router({
        "registry": registry, "ledger": ledger, "delegation": delegation,
        "governor": governor, "killswitch": killswitch, "sentinel": sentinel,
    })

    tool = _load_tool()
    for name, prefix in (("REG", "registry"), ("LED", "ledger"),
                         ("DEL", "delegation"), ("SEN", "sentinel"),
                         ("KIL", "killswitch"), ("GOV", "governor")):
        monkeypatch.setattr(tool, name, f"http://t/{prefix}")
    monkeypatch.setattr(tool, "H", router)

    yield tool, router, manifest, registry, governor, delegation
    registry_store.close()


def test_wrapper_provisions_through_the_lifecycle_engine(estate):
    """No `PUT /caps` and no `POST /tokens` of its own: the cap and the token
    come out of `lifecycle provision`."""
    tool, router, manifest, registry, governor, delegation = estate
    engine = tool.build_engine(client=router)
    report = engine.provision(
        manifest_path=manifest, owner="Don Hagell, Spin State Labs",
        domain="finance", grantor="Don Hagell, Spin State Labs", ttl_days=30,
        name="SSL Invoicing Agent",
        manifest_ref=str(manifest),
    )
    assert report.ok is True
    assert report.registry_outcome == "registered"
    assert governor.get(f"/caps/{AGENT_ID}").json()["limit_cents"] == 500
    assert len(delegation.get("/tokens").json()) == 1

    source = TOOL.read_text(encoding="utf-8")
    assert "/caps/" not in source.replace("caps/{id}", "")
    assert 'f"{DEL}/tokens"' not in source


def test_wrapper_probe_passes_against_the_in_process_stack(estate):
    tool, router, manifest, registry, _, _ = estate
    engine = tool.build_engine(client=router)
    report = engine.provision(
        manifest_path=manifest, owner="Don Hagell, Spin State Labs",
        domain="finance", grantor="Don Hagell, Spin State Labs", ttl_days=30,
        manifest_ref=str(manifest),
    )
    assert report.ok is True

    rows = tool.probe(
        AGENT_ID, {"never": NEVER}, report.scope, report.token_id, client=router
    )
    by_action = {action: (decision, clause) for action, decision, clause in rows}
    assert set(by_action) == set(SCOPE) | {NEVER}
    for action in SCOPE:
        assert by_action[action][0] == "ALLOW", (action, by_action[action])
    # The action nobody granted must refuse, and name the clause.
    never_decision, never_clause = by_action[NEVER]
    assert never_decision != "ALLOW"
    assert never_clause == "D.scope"


def test_wrapper_keeps_its_operator_contract(estate):
    """The bits `lifecycle provision` has no opinion about must survive the
    rewrite: proxy URL, shared secret, tokens file, the 6-service health gate
    and the AGENTS table."""
    tool, *_ = estate
    source = TOOL.read_text(encoding="utf-8")
    for expected in ("FIELD_PROXY_URL", "FIELD_SHARED_SECRET",
                     "FIELD_TOKENS_FILE", "FIELD_TOKEN_TTL_DAYS"):
        assert expected in source, expected
    assert set(tool.AGENTS) == {"ssl-timekeeping-agent", "ssl-invoicing-agent"}
    assert all("never" in meta and "domain" in meta for meta in tool.AGENTS.values())
    # health() gates on all six services before anything is provisioned.
    for service in ("registry", "ledger", "delegation", "sentinel",
                    "killswitch", "governor"):
        assert f'("{service}"' in source, service
    # ...and the out-of-repo local script pointer is annotated, not deleted.
    assert "_local-test/provision_local.py" in source
    assert "lifecycle provision" in source
