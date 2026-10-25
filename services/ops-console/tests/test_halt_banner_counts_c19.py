"""Phase G C-19 (console part; design RT2-6, RT2-7): the halt banners report the
kill-switch's per-agent errors instead of a bare success.

The failure being made visible: when the kill-switch cannot write the registry
(S1: its own identity missing, revoked or stale under REQUIRE), a domain kill
answered 200 with ``killed: []`` and every per-agent result an error, and a
drill whose restore failed answered 200 with ``restored: false``. The console
showed both as success (``domains halted: 1/1``, ``drill: 1/1 ok``).

The upstreams here are the REAL kill-switch, registry and ledger apps; only the
kill-switch's registry client is made to fail (every status write, or only the
drill's restore). A stub upstream covers the kill-switch answering non-2xx
with the report in its body (the kill-switch side of C-19, another change),
so the counts survive either answer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient, RegistryUnreachableError
from kill_switch.api import create_app as create_kill_app
from ops_console.api import ServiceClient, create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

HALT = {"operator": "CISO", "reason": "c19", "confirm": "HALT"}
AGENTS = (("invoicing-agent", "finance"), ("payroll-agent", "finance"), ("support-agent", "support"))


class _FailingWrites(RegistryClient):
    """The kill-switch's registry client: reads work; status writes fail as a
    registry 401 would (``fail_on`` = which target statuses fail)."""

    def __init__(self, *a, fail_on: tuple[str, ...] = ("killed", "active"), **kw):
        super().__init__(*a, **kw)
        self.fail_on = fail_on

    def set_status(self, agent_id, status):
        if status in self.fail_on:
            raise RegistryUnreachableError("registry returned 401: operator credentials required")
        return super().set_status(agent_id, status)


class _Dead:
    def get(self, *a, **k):
        raise ConnectionError("down")

    def post(self, *a, **k):
        raise ConnectionError("down")


def _console(tmp_path, fail_on):
    registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    kill = TestClient(create_kill_app(
        registry=_FailingWrites(client=registry, base_url="http://t", fail_on=fail_on),
        ledger=LedgerClient(client=ledger, base_url="http://t")))
    for agent_id, domain in AGENTS:
        assert registry.post("/agents", json={"agent_id": agent_id, "name": agent_id, "owner": "Ops",
                                              "domain": domain}).status_code == 201
    wrap = lambda c: ServiceClient(client=c, base_url="http://t")  # noqa: E731
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(registry=wrap(registry), ledger=wrap(ledger), killswitch=wrap(kill),
                     delegation=dead, governor=dead, sentinel=dead, lifecycle=dead, attest=dead,
                     crosswalk=dead, federation=dead, replay=dead, gateway=dead)
    return TestClient(app), registry


def test_fleet_halt_with_every_agent_errored_is_not_reported_as_halted(tmp_path):
    console, registry = _console(tmp_path, fail_on=("killed",))
    r = console.post("/api/fleet/halt", json=HALT)
    assert r.status_code == 200
    body = r.json()
    assert body["all_ok"] is False
    assert body["agent_errors"] == 3 and body["domains_failed"] == 2
    by = {d["domain"]: d for d in body["results"]}
    assert by["finance"]["ok"] is False and by["finance"]["status"] == 200
    assert by["finance"]["counts"] == {"killed": 0, "already_killed": 0, "skipped_retired": 0, "error": 2}
    assert sorted(e["agent_id"] for e in by["finance"]["errors"]) == ["invoicing-agent", "payroll-agent"]
    assert all("502" in e["error"] for e in by["finance"]["errors"])
    assert by["support"]["counts"]["error"] == 1 and by["support"]["ok"] is False
    for agent_id, _ in AGENTS:                       # the halt really did not happen
        assert registry.get(f"/agents/{agent_id}").json()["status"] == "active"


def test_fleet_halt_that_worked_stays_green_with_zero_errors(tmp_path):
    console, registry = _console(tmp_path, fail_on=())
    body = console.post("/api/fleet/halt", json=HALT).json()
    assert body["all_ok"] is True and body["agent_errors"] == 0 and body["domains_failed"] == 0
    assert {d["domain"]: d["counts"]["killed"] for d in body["results"]} == {"finance": 2, "support": 1}
    assert all(d["errors"] == [] for d in body["results"])


def test_bulk_drill_whose_restore_failed_is_an_error_not_ok(tmp_path):
    console, registry = _console(tmp_path, fail_on=("active",))   # the kill lands, the restore fails
    r = console.post("/api/agents/bulk", json={"action": "drill", "agent_ids": ["invoicing-agent"],
                                               "operator": "CISO", "reason": "c19"})
    assert r.status_code == 200
    body = r.json()
    row = body["results"][0]
    assert row["status"] == 200 and row["result"]["restored"] is False   # the kill-switch's own answer
    assert row["ok"] is False and "restore" in row["error"]
    assert body["all_ok"] is False and body["error_count"] == 1
    assert registry.get("/agents/invoicing-agent").json()["status"] == "killed"   # left killed: the fact shown


def test_bulk_drill_that_restored_is_ok(tmp_path):
    console, _ = _console(tmp_path, fail_on=())
    body = console.post("/api/agents/bulk", json={"action": "drill", "agent_ids": ["invoicing-agent"],
                                                  "operator": "CISO", "reason": "c19"}).json()
    assert body["all_ok"] is True and body["error_count"] == 0 and body["results"][0]["ok"] is True


class _Answer:
    """A kill-switch stub: answers every POST with (status, body)."""

    def __init__(self, status, body):
        self.status, self.body = status, body

    def post(self, path, **kw):
        status, body = self.status, self.body

        class R:
            status_code = status

            def json(self):
                return body
        return R()

    def get(self, *a, **k):
        raise ConnectionError("n/a")


REPORT = {"domain": "finance", "killed": [], "already_killed": [], "skipped_retired": ["old-agent"],
          "results": [{"agent_id": "a1", "outcome": "error", "previous_status": "active",
                       "error": "502: registry unreachable"},
                      {"agent_id": "old-agent", "outcome": "skipped_retired", "previous_status": "retired"}]}


@pytest.mark.parametrize("status,body", [
    (200, REPORT),                       # today's kill-switch
    (502, {"detail": REPORT}),           # a non-2xx with the report as the detail
    (502, REPORT),                       # a non-2xx with the report as the body
])
def test_domain_counts_are_read_from_whichever_answer_the_kill_switch_gives(status, body):
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(killswitch=ServiceClient(client=_Answer(status, body), base_url="http://ks"),
                     registry=dead, ledger=dead, delegation=dead, governor=dead, sentinel=dead,
                     lifecycle=dead, attest=dead, crosswalk=dead, federation=dead, replay=dead, gateway=dead)
    out = TestClient(app).post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    d = out["results"][0]
    assert d["ok"] is False and out["all_ok"] is False and out["agent_errors"] == 1
    assert d["counts"] == {"killed": 0, "already_killed": 0, "skipped_retired": 1, "error": 1}
    assert d["errors"] == [{"agent_id": "a1", "error": "502: registry unreachable"}]


def test_a_non_2xx_without_a_report_is_a_failed_domain_with_no_counts():
    dead = ServiceClient(client=_Dead(), base_url="http://dead")
    app = create_app(killswitch=ServiceClient(client=_Answer(403, {"detail": "operator not authorised"}),
                                              base_url="http://ks"),
                     registry=dead, ledger=dead, delegation=dead, governor=dead, sentinel=dead,
                     lifecycle=dead, attest=dead, crosswalk=dead, federation=dead, replay=dead, gateway=dead)
    out = TestClient(app).post("/api/fleet/halt", json={**HALT, "domains": ["finance"]}).json()
    d = out["results"][0]
    assert d["ok"] is False and d["counts"] is None and d["errors"] == []
    assert d["error"] == {"detail": "operator not authorised"}
    assert out["all_ok"] is False and out["domains_failed"] == 1 and out["agent_errors"] == 0
