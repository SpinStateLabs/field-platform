"""C2 — lifecycle RetentionFinding: the ledger's /retention/check on the sweep.

Every claim here has a test that fails when the code behind it is removed:
- a violation / no-policy / unresolvable / unavailable answer becomes
  ``SweepReport.retention_policy`` and exit 3 (``is not None``, never truthiness);
- ``ok`` and "not configured" are ``None`` and leave the exit code alone;
- a ledger that is down never crashes the sweep: ``unavailable``;
- the finding writes NO ledger event (``escalations_written`` unchanged);
- it is persisted in ``/findings``; a ``last_sweep.json`` written before C2 still validates;
- ``lifecycle serve`` wires a LedgerClient; ``create_app`` builds none on its own.

The existing suites are unmodified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.clients import LedgerClient, LedgerUnreachableError
from lifecycle_manager.api import create_app
from lifecycle_manager.engine import LifecycleEngine, SweepReport, render_markdown
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner\nAP Team Lead\n"

VIOLATION = {
    "ok": False, "status": "violation", "estate_retention_days": 365,
    "max_manifest_retention_days": 2555, "offending": [{"agent_id": "inv", "retention_days": 2555}],
    "unresolvable": [], "agents_without_manifest": 1, "detail": None,
}
OK = {"ok": True, "status": "ok", "estate_retention_days": 2555, "offending": [], "unresolvable": []}


class FakeRegistry:
    def __init__(self, agents):
        self.agents = agents

    def list_agents(self, *a, **k):
        return [dict(a) for a in self.agents]


class NoTokens:
    def get(self, path, *a, **k):
        assert path == "/tokens"
        return []


class RecordingLedger:
    """Append-only stand-in: no retention_check (a pre-C2 client shape)."""

    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, agent_id, payload or {}))


class RetentionLedger(RecordingLedger):
    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.checks = 0

    def retention_check(self):
        self.checks += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _agents(*owners):
    return [{"agent_id": f"agent-{i}", "owner": o, "status": "active", "created_at": NOW.isoformat()}
            for i, o in enumerate(owners)]


def _sweep(retention, owners=("AP Team Lead",)):
    ledger = RecordingLedger()
    engine = LifecycleEngine(registry=FakeRegistry(_agents(*owners)), delegation=NoTokens(),
                             ledger=ledger, retention=retention)
    return engine.sweep(ROSTER, now=NOW), ledger


# --- the engine -------------------------------------------------------------


@pytest.mark.parametrize("answer", [
    VIOLATION,
    {"ok": False, "status": "no_estate_policy", "estate_retention_days": None,
     "detail": "no estate policy (FIELD_LEDGER_RETENTION_DAYS unset)"},
    {"ok": False, "status": "unresolvable", "estate_retention_days": 2555,
     "unresolvable": [{"agent_id": "a9", "manifest_ref": "/data/manifests/a9.yaml", "reason": "missing"}]},
    {"ok": False, "status": "unavailable", "estate_retention_days": 2555,
     "detail": "registry unavailable: ConnectError"},
])
def test_every_non_ok_answer_is_a_finding_and_writes_no_ledger_event(answer):
    report, ledger = _sweep(RetentionLedger(answer))
    finding = report.retention_policy
    assert finding is not None and finding.status == answer["status"]
    assert finding.estate_retention_days == answer.get("estate_retention_days")
    assert finding.unresolvable == answer.get("unresolvable", [])
    assert report.orphans == [] and report.escalations_written == 0 and ledger.events == []


def test_ok_and_not_configured_are_none():
    assert _sweep(RetentionLedger(OK))[0].retention_policy is None
    assert _sweep(None)[0].retention_policy is None
    # ok:true with a status that is not "ok" is not ok
    odd = _sweep(RetentionLedger({"ok": True, "status": "violation"}))[0].retention_policy
    assert odd is not None and odd.status == "violation"


@pytest.mark.parametrize("answer,detail", [
    (LedgerUnreachableError("ledger retention check returned 401: unauthorized"), "LedgerUnreachableError"),
    (RuntimeError("boom"), "RuntimeError: boom"),
    ([1, 2], "returned list"),
    ({"ok": False, "status": "tampered"}, "answered status 'tampered'"),
    ({"ok": False, "status": "violation", "agents_without_manifest": "many"}, "unreadable"),
])
def test_a_ledger_that_cannot_answer_is_unavailable_and_the_sweep_carries_on(answer, detail):
    report, ledger = _sweep(RetentionLedger(answer), owners=("AP Team Lead", "Departed Employee"))
    assert report.retention_policy.status == "unavailable" and detail in report.retention_policy.detail
    assert [o.agent_id for o in report.orphans] == ["agent-1"]  # the rest of the sweep ran
    assert [e[0] for e in ledger.events] == ["lifecycle.orphan"]


def test_real_ledger_client_end_to_end_and_ledger_down(tmp_path, monkeypatch):
    """The real LedgerClient against the real ledger app's /retention/check."""
    from pathlib import Path

    import field_core

    templates = Path(field_core.__file__).resolve().parent / "templates"
    manifest = tmp_path / "inv.yaml"  # the financial template declares retention_days 2555
    manifest.write_text((templates / "field-manifest-financial-agent.yaml").read_text(encoding="utf-8"),
                        encoding="utf-8")
    monkeypatch.setenv("FIELD_LEDGER_RETENTION_DAYS", "365")
    ledger_app = TestClient(create_ledger_app(
        store=LedgerStore(tmp_path / "events.jsonl"),
        registry=FakeRegistry([{"agent_id": "inv", "manifest_ref": str(manifest)}]),
    ))
    client = LedgerClient(client=ledger_app, base_url="http://t")
    engine = LifecycleEngine(registry=FakeRegistry(_agents("Departed Employee")), delegation=NoTokens(),
                             ledger=client, retention=client)
    report = engine.sweep(ROSTER, now=NOW)
    assert report.retention_policy.status == "violation"
    assert report.retention_policy.offending == [{"agent_id": "inv", "retention_days": 2555}]
    assert report.escalations_written == 1  # the orphan only
    types = [e["event_type"] for e in ledger_app.get("/events").json()]
    assert types == ["lifecycle.orphan"]  # no retention event

    class Down:
        def get(self, *a, **k):
            raise ConnectionError("connection refused")

        def post(self, *a, **k):
            raise ConnectionError("connection refused")

    down = LedgerClient(client=Down(), base_url="http://127.0.0.1:9")
    report = LifecycleEngine(registry=FakeRegistry(_agents("AP Team Lead")), delegation=NoTokens(),
                             ledger=down, retention=down).sweep(ROSTER, now=NOW)
    assert report.retention_policy.status == "unavailable"
    assert "connection refused" in report.retention_policy.detail


# --- the CLI: exit 3 --------------------------------------------------------


def _patch_cli(monkeypatch, ledger, owners=("AP Team Lead",)):
    import httpx

    import field_core.clients as clients

    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: FakeRegistry(_agents(*owners)))
    monkeypatch.setattr(clients, "LedgerClient", lambda *a, **k: ledger)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: NoTokens())


def test_lifecycle_retention_finding_present_and_exit_3(tmp_path, monkeypatch):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    violation = RetentionLedger(VIOLATION)
    _patch_cli(monkeypatch, violation)
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == 3, r.output
    report = SweepReport.model_validate_json(r.stdout)
    assert report.retention_policy.status == "violation" and violation.checks == 1
    assert report.orphans == [] and report.escalations_written == 0 and violation.events == []

    _patch_cli(monkeypatch, RetentionLedger(OK))  # ok => None, exit unaffected
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == 0, r.output
    assert SweepReport.model_validate_json(r.stdout).retention_policy is None

    _patch_cli(monkeypatch, RecordingLedger())  # a client without the check => not checked
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == 0 and SweepReport.model_validate_json(r.stdout).retention_policy is None

    # a finding whose lists are all empty still exits 3 (`is not None`, never truthiness)
    _patch_cli(monkeypatch, RetentionLedger({"ok": False, "status": "no_estate_policy"}))
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster), "--markdown", str(tmp_path / "s.md")])
    assert r.exit_code == 3
    md = (tmp_path / "s.md").read_text(encoding="utf-8")
    assert "## Retention policy (no_estate_policy)" in md and "estate keeps no estate policy" in md

    # ledger down: unavailable, still exit 3, the sweep completed
    _patch_cli(monkeypatch, RetentionLedger(LedgerUnreachableError("connection refused")),
               owners=("AP Team Lead", "Departed Employee"))
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == 3
    report = SweepReport.model_validate_json(r.stdout)
    assert report.retention_policy.status == "unavailable" and len(report.orphans) == 1


def test_markdown_section_only_when_present():
    report, _ = _sweep(RetentionLedger(VIOLATION))
    md = render_markdown(report)
    assert "## Retention policy (violation)" in md
    assert "- estate keeps 365 d; the longest manifest retention is 2555 d" in md
    assert "- inv declares 2555 d — more than the estate keeps" in md
    assert "1 agent(s) without a manifest_ref (skipped)" in md
    assert "Retention policy" not in render_markdown(_sweep(RetentionLedger(OK))[0])


# --- served: /sweep and /findings -------------------------------------------


def test_served_sweep_persists_the_finding_and_old_reports_still_load(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    ledger = RetentionLedger(VIOLATION)
    app = create_app(registry=FakeRegistry(_agents("AP Team Lead")), delegation=NoTokens(),
                     ledger=RecordingLedger(), every=0, retention=ledger)
    client = TestClient(app)
    r = client.post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 200 and r.json()["retention_policy"]["status"] == "violation"
    findings = client.get("/findings").json()
    assert findings["retention_policy"]["offending"] == [{"agent_id": "inv", "retention_days": 2555}]
    # a report persisted before C2 has no retention_policy key
    legacy = {k: v for k, v in findings.items() if k not in ("retention_policy", "last_tick")}
    assert SweepReport.model_validate(legacy).retention_policy is None
    # create_app builds no retention client on its own
    plain = create_app(registry=FakeRegistry(_agents("AP Team Lead")), delegation=NoTokens(),
                       ledger=RecordingLedger(), every=0)
    assert plain.state.retention is None
    assert TestClient(plain).post("/sweep", json={"roster_csv": ROSTER}).json()["retention_policy"] is None


def test_lifecycle_serve_wires_a_ledger_client(monkeypatch):
    import uvicorn

    from lifecycle_manager.cli import app

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: captured.update(app=application))
    r = CliRunner().invoke(app, ["serve", "--every", "0"])
    assert r.exit_code == 0, r.output
    assert isinstance(captured["app"].state.retention, LedgerClient)
