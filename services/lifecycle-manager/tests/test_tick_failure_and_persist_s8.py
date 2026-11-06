"""S8-12: a scheduled sweep that fails leaves a trace (last_tick marker + lifecycle.tick_failed note),
and a persist failure after the sweep (and any auto-kill) returns the report with persist_error set
instead of a 500 that loses it. The stack fixture is copied from test_api.py (not imported)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager import api as api_module
from lifecycle_manager.api import create_app
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



def _types(ledger):
    return [e["event_type"] for e in ledger.get("/events").json()]


def test_a_failed_scheduled_tick_leaves_a_marker_and_a_ledger_note(stack, monkeypatch):
    build, registry, ledger, _ = stack
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", "")
    client = build()

    def boom(*a, **k):
        raise RuntimeError("secret-looking message https://internal.example.test/x")
    monkeypatch.setattr(api_module, "run_sweep", boom)

    result = api_module.scheduled_tick(client.app)

    assert result["ok"] is False
    assert "lifecycle.tick_failed" in _types(ledger)
    note = [e for e in ledger.get("/events").json() if e["event_type"] == "lifecycle.tick_failed"][0]
    assert note["payload"]["error"] == "RuntimeError"
    assert "secret-looking" not in str(note) and "internal.example" not in str(note)
    r = client.get("/findings")
    marker = (r.json()["detail"] if r.status_code == 404 else r.json())["last_tick"]
    assert marker["failed"] is True and marker["error"] == "RuntimeError"
    assert "secret-looking" not in str(marker)


def test_a_failed_tick_with_an_unwritable_marker_and_a_dead_ledger_still_returns(stack, monkeypatch):
    build, _, _, _ = stack
    client = build()
    monkeypatch.setattr(api_module, "run_sweep", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(api_module, "_persist", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    client.app.state.ledger = object()           # no .append: the note is best effort
    assert api_module.scheduled_tick(client.app)["ok"] is False


def _roster_file(tmp_path, monkeypatch):
    path = tmp_path / "owners.csv"
    path.write_text(ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(path))
    return path


def test_a_registry_that_raises_is_a_failed_tick_not_a_silent_one(stack, tmp_path, monkeypatch):
    build, _, ledger, _ = stack
    _roster_file(tmp_path, monkeypatch)

    class DeadRegistry:
        def __getattr__(self, name):
            raise ConnectionError("down")
    client = build(registry=DeadRegistry())
    result = api_module.scheduled_tick(client.app)
    assert result["ok"] is False
    assert "lifecycle.tick_failed" in _types(ledger)
    r = client.get("/findings")
    assert (r.json()["detail"] if r.status_code == 404 else r.json())["last_tick"]["failed"] is True


def test_a_persist_failure_after_an_auto_kill_sweep_returns_the_report_with_persist_error(
        stack, tmp_path, monkeypatch):
    build, registry, ledger, spy = stack
    _roster_file(tmp_path, monkeypatch)
    client = build(clock=lambda: NOW)
    monkeypatch.setattr(api_module, "_persist",
                        lambda *a, **k: (_ for _ in ()).throw(PermissionError("read-only volume")))

    r = client.post("/sweep", json={"auto_kill_orphans": True})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["persist_error"] == "PermissionError"
    assert body["agents_scanned"] == 2 and body["orphans"][0]["auto_killed"] is True
    assert spy.calls, "the kill had already happened"
    assert "read-only volume" not in r.text


def test_a_persisted_sweep_has_no_persist_error_and_old_reports_still_load(stack):
    build, _, _, _ = stack
    client = build(clock=lambda: NOW)
    r = client.post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 200 and r.json()["persist_error"] is None
    from lifecycle_manager.engine import SweepReport
    older = {k: v for k, v in r.json().items() if k != "persist_error"}
    assert SweepReport.model_validate(older).persist_error is None
    assert client.get("/findings").json()["swept_at"] == r.json()["swept_at"]
