"""S6-2: a kill-switch that cannot be reached (or refuses) during --auto-kill-orphans must not
abort the sweep. Every orphan is still reported and ledgered; a failed kill is auto_killed=False
with kill_error naming the exception class or HTTP status, never a URL or exception text."""

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from lifecycle_manager.engine import LifecycleEngine, SweepConfig, render_markdown
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner,department\nAP Team Lead,finance\n"
HOST = "killswitch.internal.example.test"


class Stub:
    """Kill-switch double: per-agent behaviour, records every call."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def post(self, path, json=None):
        self.calls.append(path)
        return self.behaviour(path)


class Resp:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.fixture()
def make(tmp_path):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(create_delegation_app(
        store=TokenStore(tmp_path / "tokens.sqlite3"),
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        registry=RegistryClient(client=registry, base_url="http://t")))
    for agent_id in ("orphan-a", "orphan-b"):
        registry.post("/agents", json={"agent_id": agent_id, "name": agent_id,
                                       "owner": "Departed Employee", "domain": "growth"})

    def build(behaviour):
        stub = Stub(behaviour)
        engine = LifecycleEngine(
            registry=RegistryClient(client=registry, base_url="http://t"),
            delegation=delegation,
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            killswitch=stub)
        return engine, stub, ledger
    return build


def _sweep(engine):
    return engine.sweep(ROSTER, config=SweepConfig(auto_kill_orphans=True), now=NOW)


def test_a_transport_error_on_the_first_orphan_does_not_abort_the_sweep(make):
    def behaviour(path):
        if path.endswith("orphan-a"):
            raise httpx.ConnectError(f"cannot reach https://{HOST}{path}")
        return Resp(200)
    engine, stub, ledger = make(behaviour)

    report = _sweep(engine)

    by_id = {o.agent_id: o for o in report.orphans}
    assert set(by_id) == {"orphan-a", "orphan-b"}
    assert by_id["orphan-a"].auto_killed is False
    assert by_id["orphan-a"].kill_error == "ConnectError"
    assert by_id["orphan-b"].auto_killed is True and by_id["orphan-b"].kill_error is None
    assert sorted(stub.calls) == ["/kill/orphan-a", "/kill/orphan-b"]
    ledgered = ledger.get("/events", params={"event_type": "lifecycle.orphan"}).json()
    assert {e["agent_id"] for e in ledgered} == {"orphan-a", "orphan-b"}


def test_a_refusal_records_the_http_status(make):
    engine, _, _ = make(lambda path: Resp(403) if path.endswith("orphan-a") else Resp(200))
    by_id = {o.agent_id: o for o in _sweep(engine).orphans}
    assert by_id["orphan-a"].auto_killed is False and by_id["orphan-a"].kill_error == "HTTP 403"
    assert by_id["orphan-b"].auto_killed is True


def test_the_report_and_markdown_never_carry_the_url_or_exception_text(make):
    def behaviour(path):
        raise httpx.ReadTimeout(f"timed out talking to {HOST}")
    engine, _, _ = make(behaviour)
    report = _sweep(engine)
    assert report.orphans and all(o.kill_error == "ReadTimeout" for o in report.orphans)
    text = report.model_dump_json() + render_markdown(report)
    assert HOST not in text and "timed out talking" not in text
    assert "AUTO-KILL FAILED (ReadTimeout)" in render_markdown(report)
    assert "AUTO-KILLED" not in render_markdown(report).replace("AUTO-KILL FAILED", "")


def test_a_successful_kill_has_no_kill_error(make):
    engine, _, _ = make(lambda path: Resp(200))
    assert all(o.auto_killed and o.kill_error is None for o in _sweep(engine).orphans)
