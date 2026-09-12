"""lifecycle-manager served API: roster resolution, findings persistence,
auto-kill discipline over HTTP, and the in-process scheduler.

The stack fixture is copied (not imported) from test_lifecycle_manager.py so the
two files stay independent — the existing suite is unmodified by Phase A.
"""

from __future__ import annotations

import inspect
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from lifecycle_manager import api as api_module
from lifecycle_manager.api import create_app, run_every
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"


class KillSpy:
    """Records every call. A zero count is the adversarial assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, json=None, **kw):  # noqa: A002 - httpx-compatible
        self.calls.append((url, json or {}))

        class _R:
            status_code = 200

        return _R()


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FIELD_LIFECYCLE_ROSTER", raising=False)

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
    TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
        )
    )
    registry.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoicing",
        "owner": "AP Team Lead", "domain": "finance"})
    registry.post("/agents", json={
        "agent_id": "rogue-experiment", "name": "Rogue",
        "owner": "Departed Employee", "domain": "growth"})
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
        "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})

    spy = KillSpy()

    def build(**over):
        kwargs = dict(
            registry=RegistryClient(client=registry, base_url="http://t"),
            delegation=delegation,
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            killswitch=spy,
        )
        kwargs.update(over)
        return TestClient(create_app(**kwargs))

    return build, registry, ledger, spy


def test_health_is_open_and_reports_roster_and_schedule(stack):
    build, _, _, _ = stack
    body = build().get("/health").json()
    assert body["ok"] is True
    assert body["service"] == "lifecycle-manager"
    assert body["roster_configured"] is False
    assert body["every"] == 0


def test_sweep_with_roster_in_body_returns_report_with_swept_at(stack):
    build, _, ledger = stack[0], stack[1], stack[2]
    r = build().post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["swept_at"]
    assert report["agents_scanned"] == 2
    assert report["roster_size"] == 2
    assert len(report["expiring"]) == 1
    # the served sweep stamps `now` after the fixture minted the token, so the
    # 10-day token reads 9 or 10 depending on where the second boundary fell
    assert report["expiring"][0]["days_left"] in (9, 10)
    assert len(report["orphans"]) == 1
    assert report["orphans"][0]["agent_id"] == "rogue-experiment"
    assert report["orphans"][0]["auto_killed"] is False
    types = [e["event_type"] for e in ledger.get("/events").json()]
    assert "lifecycle.expiring_authority" in types
    assert "lifecycle.orphan" in types


def test_sweep_uses_roster_file_when_body_omits_it(stack, tmp_path, monkeypatch):
    build, _, _, _ = stack
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(roster))
    r = build().post("/sweep", json={})
    assert r.status_code == 200, r.text
    assert r.json()["roster_size"] == 2


def test_sweep_without_any_roster_is_503_never_a_silent_empty_roster(stack):
    """An empty roster would orphan every agent — refusing is the safe answer."""
    build, _, ledger, _ = stack
    before = len(ledger.get("/events").json())
    r = build().post("/sweep", json={})
    assert r.status_code == 503
    assert "roster" in r.json()["detail"].lower()
    assert len(ledger.get("/events").json()) == before  # nothing swept, nothing ledgered


def test_findings_404_before_any_sweep_then_serves_the_last_report(stack):
    build, _, _, _ = stack
    client = build()
    assert client.get("/findings").status_code == 404
    client.post("/sweep", json={"roster_csv": ROSTER})
    body = client.get("/findings").json()
    assert body["swept_at"]
    assert body["agents_scanned"] == 2


# --- adversarial: auto-kill cannot be armed except by the literal body flag ---


def test_adversarial_sweep_without_flag_leaves_orphan_active_and_never_calls_kill(stack):
    build, registry, _, spy = stack
    r = build().post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 200
    assert r.json()["orphans"][0]["auto_killed"] is False
    assert spy.calls == []
    assert registry.get("/agents/rogue-experiment").json()["status"] == "active"


def test_adversarial_unknown_body_key_is_422(stack):
    build, _, _, spy = stack
    r = build().post(
        "/sweep", json={"roster_csv": ROSTER, "auto_kill": True, "force": True}
    )
    assert r.status_code == 422
    assert spy.calls == []


def test_adversarial_blank_roster_csv_is_rejected(stack):
    build, _, _, _ = stack
    r = build().post("/sweep", json={"roster_csv": "   "})
    assert r.status_code == 422


def test_grep_guard_no_env_var_can_arm_auto_kill(stack):
    """The scheduler and the app read no AUTO_KILL environment variable, and the
    kill-switch client is reached only under the request flag."""
    source = inspect.getsource(api_module)
    for line in source.splitlines():
        if "AUTO_KILL" in line.upper() and "os.environ" in line:
            pytest.fail(f"auto-kill is env-armable: {line.strip()}")
    assert "auto_kill_orphans" in source


def test_scheduled_tick_never_arms_auto_kill(stack, tmp_path, monkeypatch):
    build, registry, _, spy = stack
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(roster))
    monkeypatch.setenv("FIELD_LIFECYCLE_AUTO_KILL", "1")  # must be ignored
    client = build()
    api_module.scheduled_tick(client.app)
    assert spy.calls == []
    assert registry.get("/agents/rogue-experiment").json()["status"] == "active"


# --- scheduler: interval fires, a raising tick does not stop the loop ---


def test_run_every_fires_on_an_injected_clock_and_survives_a_raising_tick():
    fired: list[int] = []
    stop = threading.Event()

    def tick():
        fired.append(len(fired))
        if len(fired) == 2:
            raise RuntimeError("one bad tick must not kill the scheduler")
        if len(fired) == 3:
            stop.set()

    ticks = run_every(tick, 3600, stop, sleep=lambda _s: None)
    assert len(fired) == 3  # the raising tick did not stop the loop
    assert ticks == 3


def test_run_every_sleeps_the_interval_before_the_first_tick():
    """First tick after the interval — never at boot, so container start does
    not depend on a roster being present."""
    order: list[str] = []
    stop = threading.Event()

    def tick():
        order.append("tick")
        stop.set()

    run_every(tick, 900, stop, sleep=lambda s: order.append(f"sleep{int(s)}"))
    assert order[0] == "sleep900"
    assert order[1] == "tick"


def test_tick_without_a_roster_records_a_skip_not_a_silent_empty_sweep(stack):
    build, registry, ledger, _ = stack
    client = build()
    result = api_module.scheduled_tick(client.app)
    assert result["skipped"] is True
    assert "roster" in result["reason"].lower()
    # the skip is recorded, not silent: a ledger event and a findings marker
    assert "lifecycle.tick_skipped" in [
        e["event_type"] for e in ledger.get("/events").json()
    ]
    assert client.get("/findings").json()["skipped"] is True
    # and nothing was swept: no agent was touched
    assert registry.get("/agents/rogue-experiment").json()["status"] == "active"


# --- authn ---


def test_sweep_requires_x_field_auth_when_the_secret_is_set(stack, monkeypatch):
    build, _, _, _ = stack
    monkeypatch.setenv("FIELD_SHARED_SECRET", "s3cret")
    client = build()
    assert client.get("/health").status_code == 200  # /health stays open
    assert client.post("/sweep", json={"roster_csv": ROSTER}).status_code == 401
    assert client.post(
        "/sweep", json={"roster_csv": ROSTER}, headers={"x-field-auth": "wrong"}
    ).status_code == 401
    # A correct header clears the perimeter. Proven on /findings, which answers
    # from the local marker file: POST /sweep with a good header would clear
    # authn too, then fail downstream because the injected in-process registry
    # TestClients enforce the same secret and the engine's clients (built with
    # client=) do not forward it — a fixture limitation, not a service one.
    assert client.get("/findings").status_code == 401
    assert client.get(
        "/findings", headers={"x-field-auth": "s3cret"}
    ).status_code == 404  # past authn; no sweep has run yet
