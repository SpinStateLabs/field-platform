"""Phase G Stage 0, guards slice, C-11 (design 2.2.1, 5.1, RT1-1), the scope half:
under ENFORCE a served ``POST /sweep`` that arms auto-kill (``auto_kill_orphans:
true``) also needs the separate ``sweep_kill`` scope, held explicitly by the
caller's row. ``*`` does not imply it and ``sweep`` alone is not enough; the
refusal happens before anything is swept, killed or persisted, and is ledgered
as ``operator.refused`` (C-16). A sweep without auto-kill needs only ``sweep``.
LOG-ONLY and OFF never refuse (no flag default changes).

The stack is the real registry, delegation and ledger apps over TestClient (as in
test_api.py, copied so the files stay independent); the kill-switch is a spy, so
a zero call count is the adversarial assertion. Test key values are throwaway."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core import operator_auth as oa
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager.api import create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"
KEY_SWEEP = "tkv-c11-sweep-key-0123456789abcdef"
KEY_STAR = "tkv-c11-star-key-0123456789abcdef"
KEY_SK = "tkv-c11-sk-key-0123456789abcdef"
KEY_SKONLY = "tkv-c11-skonly-key-0123456789abcdef"


class KillSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, json=None, **kw):  # noqa: A002 - httpx-compatible
        self.calls.append((url, json or {}))

        class _R:
            status_code = 200

        return _R()


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY,
              oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def ops_file(tmp_path):
    def row(oid, key, scopes):
        return {"operator_id": oid, "key_sha256": oa.key_sha256(key), "status": "active",
                "scopes": scopes}
    rows = [row("sweeper", KEY_SWEEP, ["sweep"]),
            row("star", KEY_STAR, ["*"]),
            row("sweep-killer", KEY_SK, ["sweep", "sweep_kill"]),
            row("kill-only", KEY_SKONLY, ["sweep_kill"])]
    p = tmp_path / "operators.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_LIFECYCLE_ROSTER", raising=False)
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")))
    registry.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoicing",
                                   "owner": "AP Team Lead", "domain": "finance"})
    registry.post("/agents", json={"agent_id": "rogue-experiment", "name": "Rogue",
                                   "owner": "Departed Employee", "domain": "growth"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
        "scope": ["draft invoices"], "expires_at": (NOW + timedelta(days=10)).isoformat()})
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    spy = KillSpy()
    app = create_app(registry=RegistryClient(client=registry, base_url="http://t"),
                     delegation=delegation, ledger=LedgerClient(client=ledger, base_url="http://t"),
                     killswitch=spy, roster_path=roster)
    return TestClient(app), registry, ledger, spy, app


def hdr(op, key):
    return {oa.HEADER_OPERATOR: op, oa.HEADER_KEY: key}


def arm(monkeypatch, ops_file, mode):
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


AUTO = {"auto_kill_orphans": True}


@pytest.mark.parametrize("who,key", [("sweeper", KEY_SWEEP), ("star", KEY_STAR)])
def test_enforce_auto_kill_without_sweep_kill_is_403_and_nothing_happens(stack, ops_file, monkeypatch, who, key):
    client, registry, ledger, spy, app = stack
    arm(monkeypatch, ops_file, "enforce")
    r = client.post("/sweep", json=AUTO, headers=hdr(who, key))
    assert r.status_code == 403 and r.json()["detail"] == oa.FORBIDDEN_DETAIL
    assert spy.calls == []
    assert registry.get("/agents/rogue-experiment").json()["status"] == "active"
    assert not app.state.findings_path.exists()
    types = [e["event_type"] for e in ledger.get("/events").json()]
    assert "lifecycle.orphan" not in types
    [refused] = ledger.get("/events", params={"event_type": "operator.refused"}).json()
    assert refused["payload"]["action"] == "sweep_kill" and refused["payload"]["claimed_id"] == who
    assert key not in json.dumps(refused)


def test_enforce_auto_kill_with_sweep_and_sweep_kill_kills_the_orphan(stack, ops_file, monkeypatch):
    client, registry, ledger, spy, app = stack
    arm(monkeypatch, ops_file, "enforce")
    r = client.post("/sweep", json=AUTO, headers=hdr("sweep-killer", KEY_SK))
    assert r.status_code == 200, r.text
    assert r.json()["orphans"][0]["auto_killed"] is True
    assert spy.calls and "rogue-experiment" in spy.calls[0][0]


def test_enforce_sweep_kill_alone_does_not_open_the_sweep_route(stack, ops_file, monkeypatch):
    client, _, _, spy, _ = stack
    arm(monkeypatch, ops_file, "enforce")
    assert client.post("/sweep", json=AUTO, headers=hdr("kill-only", KEY_SKONLY)).status_code == 403
    assert spy.calls == []


def test_enforce_a_sweep_without_auto_kill_needs_only_sweep(stack, ops_file, monkeypatch):
    client, _, _, spy, _ = stack
    arm(monkeypatch, ops_file, "enforce")
    r = client.post("/sweep", json={}, headers=hdr("sweeper", KEY_SWEEP))
    assert r.status_code == 200, r.text
    assert r.json()["orphans"][0]["auto_killed"] is False and spy.calls == []


def test_log_only_never_refuses_the_auto_kill(stack, ops_file, monkeypatch):
    client, _, _, spy, _ = stack
    arm(monkeypatch, ops_file, "log-only")
    r = client.post("/sweep", json=AUTO, headers=hdr("sweeper", KEY_SWEEP))
    assert r.status_code == 200, r.text
    assert spy.calls


def test_flags_off_auto_kill_is_unchanged(stack):
    client, _, _, spy, _ = stack
    r = client.post("/sweep", json=AUTO)
    assert r.status_code == 200, r.text
    assert r.json()["orphans"][0]["auto_killed"] is True and spy.calls


def test_the_scheduler_never_needs_sweep_kill(stack, ops_file, monkeypatch):
    """The scheduled tick hard-codes auto-kill off and runs outside any request."""
    _, _, _, spy, app = stack
    arm(monkeypatch, ops_file, "enforce")
    out = app.state.tick()
    assert out.get("ok") is True and spy.calls == []
