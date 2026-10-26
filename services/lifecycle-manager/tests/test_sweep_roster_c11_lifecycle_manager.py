"""Phase G Stage 0, guards slice, C-11 (design 2.2.1, 5.1, RT1-1), the roster half:
a served ``POST /sweep`` with ``auto_kill_orphans: true`` runs only against the
configured FIELD_LIFECYCLE_ROSTER. A body ``roster_csv`` together with auto-kill
is a 422 in EVERY mode (flags off included: RT1-1 is a universal kill with only
the shared secret while lifecycle is not armed), before anything is swept,
killed, ledgered or persisted. A body roster without auto-kill, and auto-kill
against the configured roster, work as before.

The kill-switch is a spy, so a zero call count is the adversarial assertion.
Test key values are throwaway constants."""

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
from lifecycle_manager.api import ROSTER_BODY_AUTO_KILL_DETAIL, create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"
#: what an attacker sends: a roster naming nobody who owns anything
EVIL_ROSTER = "owner,department\nNobody At All,none\n"
KEY_SK = "tkv-c11r-sk-key-0123456789abcdef"


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
    rows = [{"operator_id": "sweep-killer", "key_sha256": oa.key_sha256(KEY_SK),
             "status": "active", "scopes": ["sweep", "sweep_kill"]}]
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

    def build(**over):
        kw = dict(registry=RegistryClient(client=registry, base_url="http://t"),
                  delegation=delegation, ledger=LedgerClient(client=ledger, base_url="http://t"),
                  killswitch=spy)
        kw.update(over)
        app = create_app(**kw)
        return TestClient(app), app

    return build, registry, ledger, spy, roster


def arm(monkeypatch, ops_file, mode):
    if mode == "off":
        return
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops_file))
    if mode == "enforce":
        monkeypatch.setenv(oa.ENV_REQUIRE, "1")


@pytest.mark.parametrize("mode", ["off", "log-only", "enforce"])
@pytest.mark.parametrize("configured", [False, True])
def test_a_body_roster_with_auto_kill_is_422_in_every_mode_and_nothing_happens(
        stack, ops_file, monkeypatch, mode, configured):
    build, registry, ledger, spy, roster = stack
    arm(monkeypatch, ops_file, mode)
    client, app = build(roster_path=roster if configured else None)
    headers = {oa.HEADER_OPERATOR: "sweep-killer", oa.HEADER_KEY: KEY_SK}
    r = client.post("/sweep", json={"roster_csv": EVIL_ROSTER, "auto_kill_orphans": True},
                    headers=headers)
    assert r.status_code == 422 and r.json()["detail"] == ROSTER_BODY_AUTO_KILL_DETAIL
    assert spy.calls == []
    for agent in ("invoicing-agent", "rogue-experiment"):
        assert registry.get(f"/agents/{agent}").json()["status"] == "active"
    assert not app.state.findings_path.exists()
    types = {e["event_type"] for e in ledger.get("/events").json()}
    assert not types & {"lifecycle.orphan", "lifecycle.expiring_authority"}


def test_a_body_roster_without_auto_kill_still_sweeps(stack):
    build, _, _, spy, _ = stack
    client, _ = build()
    r = client.post("/sweep", json={"roster_csv": ROSTER, "auto_kill_orphans": False})
    assert r.status_code == 200, r.text
    assert r.json()["orphans"][0]["auto_killed"] is False and spy.calls == []


@pytest.mark.parametrize("via", ["roster_path", "env"])
def test_auto_kill_against_the_configured_roster_still_works(stack, monkeypatch, via):
    build, _, _, spy, roster = stack
    if via == "env":
        monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(roster))
        client, _ = build()
    else:
        client, _ = build(roster_path=roster)
    r = client.post("/sweep", json={"auto_kill_orphans": True})
    assert r.status_code == 200, r.text
    assert r.json()["orphans"][0]["auto_killed"] is True
    assert spy.calls and "rogue-experiment" in spy.calls[0][0]
