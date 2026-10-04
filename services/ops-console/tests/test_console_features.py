"""ops-console v0.2 features: drill-to-details, manifest viewer (path guard),
platform panels, ledger filter + export, bulk ops, fleet halt, live stream,
and the Harness selection that must survive a refresh.

Upstreams are the real service apps in TestClients, as in test_ops_console.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from ops_console.api import ServiceClient, create_app, guarded_manifest_path, \
    ManifestRefused
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

REPO = Path(__file__).resolve().parents[3]
VALID_MANIFEST = REPO / "manifests" / "ssl-invoicing-agent.yaml"


def wrap(test_client) -> ServiceClient:
    return ServiceClient(client=test_client, base_url="http://t")


class Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


DEAD = ServiceClient(client=Dead(), base_url="http://dead")


@pytest.fixture()
def env(tmp_path):
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    (mdir / "good.yaml").write_text(VALID_MANIFEST.read_text(encoding="utf-8"),
                                    encoding="utf-8")
    (mdir / "bad.yaml").write_text("not: [a, field, manifest\n", encoding="utf-8")
    secrets = tmp_path / "keys"
    secrets.mkdir()
    (secrets / "ledger-sign.pem").write_text("-----BEGIN PRIVATE KEY-----\nSECRET\n")
    (secrets / "outside.yaml").write_text(VALID_MANIFEST.read_text(encoding="utf-8"))
    (mdir / "key.pem").write_text("-----BEGIN PRIVATE KEY-----\nSECRET\n")
    os.symlink(secrets / "ledger-sign.pem", mdir / "escape.yaml")
    (mdir / "huge.yaml").write_text("x: " + "a" * (300 * 1024))

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

    for agent_id, domain in (("invoicing-agent", "finance"),
                             ("payroll-agent", "finance"),
                             ("support-agent", "support")):
        registry.post("/agents", json={
            "agent_id": agent_id, "name": agent_id, "owner": "Ops",
            "domain": domain})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller",
        "scope": ["draft invoices"], "ttl_seconds": 3600})
    for agent_id, etype, clause in (("support-agent", "conformance.allow", None),
                                    ("support-agent", "conformance.block", "E.irreversible"),
                                    ("invoicing-agent", "conformance.allow", None)):
        assert ledger.post("/events", json={
            "event_type": etype, "agent_id": agent_id,
            "payload": {"clause_id": clause} if clause else {}}).status_code == 201

    def make(**kw):
        args = dict(
            registry=wrap(registry), ledger=wrap(ledger),
            delegation=wrap(delegation), governor=wrap(governor),
            killswitch=wrap(killswitch), sentinel=wrap(killswitch),
            lifecycle=DEAD, attest=DEAD, crosswalk=DEAD, federation=DEAD,
            replay=DEAD, gateway=DEAD, manifest_dir=mdir,
            stream_interval=0.01, stream_keepalive=0.0)
        args.update(kw)
        return TestClient(create_app(**args))

    return {"console": make(), "make": make, "registry": registry,
            "ledger": ledger, "mdir": mdir, "secrets": secrets}


def set_ref(env, agent_id, ref):
    # PATCH can set any ref (registry LIMITS); that is exactly the threat.
    r = env["registry"].patch(f"/agents/{agent_id}", json={"manifest_ref": ref})
    assert r.status_code == 200, r.text


# ---- drill to details ------------------------------------------------------

def test_agent_detail_aggregates_sections(env):
    d = env["console"].get("/api/agents/invoicing-agent").json()
    assert d["agent"]["available"] and d["agent"]["data"]["domain"] == "finance"
    assert d["tokens"]["available"] and len(d["tokens"]["data"]) == 1
    assert d["heartbeat"]["available"]
    assert d["events"]["available"] and d["events"]["data"]
    assert all(e["agent_id"] == "invoicing-agent" for e in d["events"]["data"])


def test_agent_detail_unknown_is_404(env):
    assert env["console"].get("/api/agents/nobody").status_code == 404


def test_agent_detail_dead_upstream_is_unavailable_not_empty(env):
    console = env["make"](delegation=DEAD)
    d = console.get("/api/agents/invoicing-agent").json()
    assert d["tokens"]["available"] is False and d["tokens"]["data"] is None
    assert d["agent"]["available"] is True


# ---- manifest viewer + path guard ------------------------------------------

def test_manifest_valid(env):
    set_ref(env, "invoicing-agent", "good.yaml")
    m = env["console"].get("/api/agents/invoicing-agent/manifest").json()
    assert m["validation"] == "ok" and "agent" in m["raw"]


def test_manifest_invalid_is_shown_with_badge(env):
    set_ref(env, "invoicing-agent", "bad.yaml")
    m = env["console"].get("/api/agents/invoicing-agent/manifest").json()
    assert m["validation"] == "invalid" and m["raw"].startswith("not:")


def test_manifest_no_ref(env):
    m = env["console"].get("/api/agents/payroll-agent/manifest").json()
    assert m["validation"] == "no_ref" and m["raw"] is None


@pytest.mark.parametrize("ref_fn", [
    lambda e: "../keys/ledger-sign.pem",                  # traversal
    lambda e: "../keys/outside.yaml",                      # traversal, manifest suffix
    lambda e: str(e["secrets"] / "ledger-sign.pem"),       # absolute outside
    lambda e: str(e["secrets"] / "outside.yaml"),          # absolute outside, valid yaml
    lambda e: "escape.yaml",                               # symlink escaping the dir
    lambda e: "key.pem",                                   # inside, wrong suffix
    lambda e: "huge.yaml",                                 # oversize
])
def test_manifest_guard_refuses_and_never_leaks(env, ref_fn):
    set_ref(env, "invoicing-agent", ref_fn(env))
    r = env["console"].get("/api/agents/invoicing-agent/manifest")
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["validation"] == "refused"
    assert "SECRET" not in r.text and "PRIVATE KEY" not in r.text


def test_manifest_missing_file_is_404(env):
    set_ref(env, "invoicing-agent", "gone.yaml")
    r = env["console"].get("/api/agents/invoicing-agent/manifest")
    assert r.status_code == 404 and r.json()["detail"]["validation"] == "missing"


def test_manifest_guard_is_no_existence_oracle(env):
    """An absent file outside the dir must look exactly like a present one."""
    for ref in (str(env["secrets"] / "nope.pem"), "../keys/nope.yaml",
                str(env["secrets"] / "ledger-sign.pem")):
        set_ref(env, "invoicing-agent", ref)
        r = env["console"].get("/api/agents/invoicing-agent/manifest")
        assert r.status_code == 403, (ref, r.text)


def test_manifest_refused_when_dir_unconfigured(env, monkeypatch):
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)
    console = env["make"](manifest_dir=None)
    set_ref(env, "invoicing-agent", "good.yaml")
    r = console.get("/api/agents/invoicing-agent/manifest")
    assert r.status_code == 403 and "not configured" in r.text


def test_guard_allows_absolute_ref_inside_dir(env):
    p = guarded_manifest_path(env["mdir"], str(env["mdir"] / "good.yaml"))
    assert p.name == "good.yaml"
    with pytest.raises(ManifestRefused):
        guarded_manifest_path(env["mdir"], "/etc/passwd")


# ---- newer-service panels --------------------------------------------------

def test_platform_marks_each_dead_service_alone(env):
    p = env["console"].get("/api/platform").json()
    assert len(p["health"]) == 12
    assert p["health"]["registry"]["available"] is True
    assert p["health"]["lifecycle"]["available"] is False
    assert p["federation"]["available"] is False and p["federation"]["data"] is None


def test_platform_lifecycle_404_means_no_sweep_yet(env):
    class NoSweep:
        def get(self, path, **k):
            class R:
                status_code = 404 if path == "/findings" else 200
                def json(self):
                    return {"message": "no sweep yet", "last_tick": None}
            return R()
    console = env["make"](lifecycle=ServiceClient(client=NoSweep(), base_url="http://l"))
    p = console.get("/api/platform").json()
    assert p["lifecycle"]["available"] is True
    assert p["lifecycle"]["data"]["no_sweep_yet"] is True


# ---- ledger filter + export ------------------------------------------------

def test_events_filter_by_agent_and_type(env):
    c = env["console"]
    rows = c.get("/api/events", params={"agent_id": "support-agent"}).json()
    assert rows and all(e["agent_id"] == "support-agent" for e in rows)
    typed = c.get("/api/events", params={"event_type": "conformance.block"}).json()
    assert [e["agent_id"] for e in typed] == ["support-agent"]
    assert typed[0]["payload"]["clause_id"] == "E.irreversible"


def test_events_bad_since_passes_ledger_422(env):
    r = env["console"].get("/api/events", params={"since": "yesterday-ish"})
    assert r.status_code == 422


def test_export_csv_and_json(env):
    c = env["console"]
    r = c.get("/api/events/export", params={"format": "csv"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert any(x["clause_id"] == "E.irreversible" for x in rows)
    assert rows and {"ts", "event_id", "hash", "prev_hash", "payload_json"} <= set(rows[0])
    j = c.get("/api/events/export", params={"format": "json",
                                            "agent_id": "invoicing-agent"}).json()
    assert j["count"] == len(j["events"]) > 0
    assert "unsigned" in j["note"] and j["filters"]["agent_id"] == "invoicing-agent"


# ---- bulk ops + fleet halt -------------------------------------------------

def test_bulk_kill_partial_failure_is_reported(env):
    c, registry, ledger = env["console"], env["registry"], env["ledger"]
    r = c.post("/api/agents/bulk", json={
        "action": "kill", "agent_ids": ["invoicing-agent", "ghost", "payroll-agent"],
        "operator": "CISO via console", "reason": "bulk test"}).json()
    assert r["all_ok"] is False
    by = {x["agent_id"]: x for x in r["results"]}
    assert by["ghost"]["ok"] is False and by["ghost"]["status"] == 404
    for a in ("invoicing-agent", "payroll-agent"):
        assert by[a]["ok"] and registry.get(f"/agents/{a}").json()["status"] == "killed"
    kills = ledger.get("/events", params={"event_type": "kill.agent"}).json()
    assert {e["agent_id"] for e in kills} >= {"invoicing-agent", "payroll-agent"}
    assert all(e["payload"]["operator"] == "CISO via console" for e in kills)


def test_bulk_requires_operator(env):
    r = env["console"].post("/api/agents/bulk", json={
        "action": "kill", "agent_ids": ["invoicing-agent"], "operator": ""})
    assert r.status_code == 422


def test_fleet_halt_requires_typed_confirm(env):
    c = env["console"]
    for confirm in (None, "halt", "yes"):
        body = {"operator": "CISO", "reason": "drill"}
        if confirm:
            body["confirm"] = confirm
        assert c.post("/api/fleet/halt", json=body).status_code == 422
    assert env["registry"].get("/agents/invoicing-agent").json()["status"] == "active"


def test_fleet_halt_kills_every_domain(env):
    r = env["console"].post("/api/fleet/halt", json={
        "operator": "CISO", "reason": "incident", "confirm": "HALT"}).json()
    assert r["all_ok"] is True and r["domains"] == ["finance", "support"]
    for a in env["registry"].get("/agents").json():
        assert a["status"] == "killed"


def test_fleet_halt_registry_down_refuses_without_domains(env):
    console = env["make"](registry=DEAD)
    r = console.post("/api/fleet/halt", json={
        "operator": "CISO", "reason": "x", "confirm": "HALT"})
    assert r.status_code == 502


# ---- live stream -----------------------------------------------------------

def test_stream_emits_overview_frame(env):
    with env["console"].stream("GET", "/api/stream", params={"frames": 2}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert body.startswith("event: overview\ndata: ")
    data = json.loads(body.split("data: ", 1)[1].split("\n\n", 1)[0])
    assert data["agents"]["available"] is True
    assert ": keep-alive" in body           # unchanged overview → keep-alive only


def test_stream_cap_answers_503(env):
    console = env["make"](max_streams=0)
    assert console.get("/api/stream", params={"frames": 1}).status_code == 503


def test_stream_slot_is_released(env):
    console = env["make"](max_streams=1)
    for _ in range(3):  # would 503 on the 2nd pass if the slot leaked
        with console.stream("GET", "/api/stream", params={"frames": 1}) as r:
            assert r.status_code == 200
            "".join(r.iter_text())


def test_stream_locked_behind_secret(env, monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "s3cret")
    c = env["console"]
    assert c.get("/api/stream", params={"frames": 1}).status_code == 401
    assert c.get("/api/events/export").status_code == 401
    assert c.get("/api/agents/invoicing-agent/manifest").status_code == 401


# ---- the served page -------------------------------------------------------

def test_harness_selection_survives_refresh(env):
    """The 5 s refresh used to rebuild the Harness <select>s and drop the
    operator's choice. The page must route both through fillSelect, which
    keeps the current value and skips the rebuild while focused."""
    html = env["console"].get("/").text
    start = html.index("function fillSelect(")
    body = html[start:html.index("\n}\n", start)]
    assert "document.activeElement === sel" in body
    assert "sel.value = keep" in body
    assert 'fillSelect($("h-agent")' in html and 'fillSelect($("h-token")' in html
    assert 'sel.innerHTML = sec.data.map' not in html
