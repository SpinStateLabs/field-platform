"""X4 — lifecycle witness finding: a stale or absent ``anchor.remote`` on a witnessing estate.

Every claim here has a test that fails when the code behind it is removed:
- fresh (latest anchor.remote for the watched estate within 3 x FIELD_WITNESS_EVERY) ⇒ None;
- stale (older than 3 x) ⇒ ``stale``; none at all (or only another estate's) ⇒ ``none``;
- FIELD_WITNESS_EVERY unset ⇒ None (Fly runs no witness); set but not a positive
  integer ⇒ ``misconfigured``;
- the ledger down ⇒ ``unavailable`` and the rest of the sweep still runs;
- every finding is exit 3 on the CLI and is persisted in ``/findings``; it writes no ledger event;
- ``lifecycle serve`` wires the watch from the environment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.clients import LedgerClient
from lifecycle_manager.api import create_app
from lifecycle_manager.engine import (
    LifecycleEngine,
    SweepReport,
    WitnessWatch,
    render_markdown,
    witness_watch_from_env,
)
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner\nAP Team Lead\n"
EVERY = 3600


class FakeRegistry:
    def __init__(self, owners=("AP Team Lead",)):
        self.agents = [{"agent_id": f"agent-{i}", "owner": o, "status": "active", "created_at": NOW.isoformat()}
                       for i, o in enumerate(owners)]

    def list_agents(self, *a, **k):
        return [dict(a) for a in self.agents]


class NoTokens:
    def get(self, path, *a, **k):
        return []


def _anchor(age_s: int, estate: str = "fly") -> dict:
    return {"event_type": "anchor.remote", "ts": (NOW - timedelta(seconds=age_s)).isoformat(),
            "payload": {"estate": estate, "length": 5, "head_hash": "ab" * 32,
                        "observed_at": (NOW - timedelta(seconds=age_s + 1)).isoformat()}}


class EventsLedger:
    def __init__(self, events=None, exc: Exception | None = None):
        self._events, self.exc, self.appended, self.reads = events or [], exc, [], []

    def append(self, event_type, payload=None, agent_id=None):
        self.appended.append(event_type)

    def events(self, event_type=None):
        self.reads.append(event_type)
        if self.exc is not None:
            raise self.exc
        return self._events


def _sweep(ledger, watch=WitnessWatch(every_seconds=EVERY), owners=("AP Team Lead",)):
    return LifecycleEngine(registry=FakeRegistry(owners), delegation=NoTokens(), ledger=ledger,
                           witness=watch).sweep(ROSTER, now=NOW)


# --- the engine -------------------------------------------------------------------------------


def test_fresh_is_no_finding():
    ledger = EventsLedger([_anchor(10 * EVERY), _anchor(3 * EVERY)])  # the LATEST is exactly 3 x: not older
    assert _sweep(ledger).witness is None
    assert ledger.reads == ["anchor.remote"] and ledger.appended == []


def test_stale_is_a_finding():
    report = _sweep(EventsLedger([_anchor(60), _anchor(3 * EVERY + 1)][::-1]))
    assert report.witness is None  # the latest in ledger order is 60 s old
    report = _sweep(EventsLedger([_anchor(60 * EVERY), _anchor(3 * EVERY + 1)]))
    w = report.witness
    assert w is not None and w.status == "stale" and w.age_seconds == 3 * EVERY + 1
    assert (w.max_age_seconds, w.anchors_seen, w.estate_watched) == (3 * EVERY, 2, "fly")
    assert report.escalations_written == 0


def test_none_is_a_finding_and_another_estates_anchor_does_not_count():
    assert _sweep(EventsLedger([])).witness.status == "none"
    report = _sweep(EventsLedger([_anchor(5, estate="gb10"), {**_anchor(5), "event_type": "action"}]))
    assert report.witness.status == "none" and report.witness.anchors_seen == 0
    watched_gb10 = _sweep(EventsLedger([_anchor(5, estate="gb10")]),
                          watch=WitnessWatch(every_seconds=EVERY, estate_watched="gb10"))
    assert watched_gb10.witness is None


def test_unset_is_no_finding_and_reads_nothing():
    ledger = EventsLedger([])
    assert _sweep(ledger, watch=None).witness is None and ledger.reads == []
    assert witness_watch_from_env({}) is None
    assert witness_watch_from_env({"FIELD_WITNESS_EVERY": "  "}) is None
    # the GB10 compose default ${FIELD_WITNESS_EVERY:-} before A5 / after disarm: set, but blank
    assert witness_watch_from_env({"FIELD_WITNESS_EVERY": ""}) is None
    assert witness_watch_from_env({"FIELD_WITNESS_EVERY": "3600"}) == WitnessWatch(
        every_seconds=3600, estate_watched="fly", raw_every="3600")
    assert witness_watch_from_env({"FIELD_WITNESS_EVERY": "60", "FIELD_WITNESS_ESTATE_WATCHED": "gb10"}
                                  ).estate_watched == "gb10"


@pytest.mark.parametrize("raw", ["0", "-5", "1h", "3.5"])
def test_a_set_but_unusable_interval_is_misconfigured(raw):
    watch = witness_watch_from_env({"FIELD_WITNESS_EVERY": raw})
    assert watch is not None and watch.every_seconds is None
    assert _sweep(EventsLedger([_anchor(1)]), watch=watch).witness.status == "misconfigured"


@pytest.mark.parametrize("ledger,detail", [
    (EventsLedger(exc=ConnectionError("connection refused")), "connection refused"),
    (EventsLedger(events={"detail": "x"}), "returned dict"),
    (EventsLedger([{**_anchor(1), "ts": "not a time"}]), "ts unreadable"),
    (type("AppendOnly", (), {"append": lambda self, *a, **k: None})(), "cannot read events"),
])
def test_ledger_down_is_unavailable_and_the_sweep_carries_on(ledger, detail):
    report = _sweep(ledger, owners=("AP Team Lead", "Departed Employee"))
    assert report.witness.status == "unavailable" and detail in report.witness.detail
    assert [o.agent_id for o in report.orphans] == ["agent-1"]


def test_real_ledger_client_against_the_real_ledger_app(tmp_path):
    store = LedgerStore(tmp_path / "events.jsonl")
    store.append("action", {"n": 1})
    ledger_app = TestClient(create_ledger_app(store=store))
    client = LedgerClient(client=ledger_app, base_url="http://t")
    watch = WitnessWatch(every_seconds=EVERY)
    engine = LifecycleEngine(registry=FakeRegistry(), delegation=NoTokens(), ledger=client, witness=watch)
    assert engine.sweep(ROSTER).witness.status == "none"
    store.append("anchor.remote", {"estate": "fly", "length": 1, "head_hash": "ab" * 32})
    assert engine.sweep(ROSTER).witness is None  # appended just now
    assert engine.sweep(ROSTER, now=datetime.now(timezone.utc) + timedelta(seconds=3 * EVERY + 60)
                        ).witness.status == "stale"

    class Down:
        def get(self, *a, **k):
            raise ConnectionError("connection refused")

    down = LedgerClient(client=Down(), base_url="http://127.0.0.1:9")
    report = LifecycleEngine(registry=FakeRegistry(), delegation=NoTokens(), ledger=down,
                             witness=watch).sweep(ROSTER, now=NOW)
    assert report.witness.status == "unavailable" and "connection refused" in report.witness.detail


def test_markdown_section_only_when_present():
    md = render_markdown(_sweep(EventsLedger([])))
    assert "## Witness (none)" in md and "watching anchor.remote{estate: fly} every 3600 s" in md
    assert "Witness" not in render_markdown(_sweep(EventsLedger([_anchor(1)])))


# --- the CLI: exit 3 ----------------------------------------------------------------------------


def _patch_cli(monkeypatch, ledger):
    import httpx

    import field_core.clients as clients

    monkeypatch.setattr(clients, "RegistryClient", lambda *a, **k: FakeRegistry())
    monkeypatch.setattr(clients, "LedgerClient", lambda *a, **k: ledger)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: NoTokens())


@pytest.mark.parametrize("env_every,events,exit_code,status", [
    ("3600", [_anchor(30)], 0, None),
    ("3600", [_anchor(3 * 3600 + 5)], 3, "stale"),
    ("3600", [], 3, "none"),
    (None, [], 0, None),
    ("soon", [_anchor(30)], 3, "misconfigured"),
])
def test_cli_sweep_exit_code(tmp_path, monkeypatch, env_every, events, exit_code, status):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    if env_every is None:
        monkeypatch.delenv("FIELD_WITNESS_EVERY", raising=False)
    else:
        monkeypatch.setenv("FIELD_WITNESS_EVERY", env_every)
    monkeypatch.delenv("FIELD_WITNESS_ESTATE_WATCHED", raising=False)
    # NOW is module import time; the CLI sweeps at the real now, a few seconds later at most
    _patch_cli(monkeypatch, EventsLedger(events))
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == exit_code, r.output
    report = SweepReport.model_validate_json(r.stdout)
    assert (report.witness.status if report.witness else None) == status


def test_cli_sweep_ledger_down_is_exit_3(tmp_path, monkeypatch):
    from lifecycle_manager.cli import app

    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_WITNESS_EVERY", "3600")
    _patch_cli(monkeypatch, EventsLedger(exc=ConnectionError("down")))
    r = CliRunner().invoke(app, ["sweep", "--roster", str(roster)])
    assert r.exit_code == 3
    assert SweepReport.model_validate_json(r.stdout).witness.status == "unavailable"


# --- served --------------------------------------------------------------------------------------


def test_served_sweep_persists_the_finding(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    app = create_app(registry=FakeRegistry(), delegation=NoTokens(), ledger=EventsLedger([]), every=0,
                     witness=WitnessWatch(every_seconds=EVERY))
    client = TestClient(app)
    assert client.post("/sweep", json={"roster_csv": ROSTER}).json()["witness"]["status"] == "none"
    assert client.get("/findings").json()["witness"]["status"] == "none"
    legacy = {k: v for k, v in client.get("/findings").json().items() if k not in ("witness", "last_tick")}
    assert SweepReport.model_validate(legacy).witness is None
    plain = create_app(registry=FakeRegistry(), delegation=NoTokens(), ledger=EventsLedger([]), every=0)
    assert plain.state.witness is None
    assert TestClient(plain).post("/sweep", json={"roster_csv": ROSTER}).json()["witness"] is None


def test_lifecycle_serve_wires_the_watch_from_the_environment(monkeypatch):
    import uvicorn

    from lifecycle_manager.cli import app

    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda application, **kw: captured.update(app=application))
    monkeypatch.setenv("FIELD_WITNESS_EVERY", "900")
    assert CliRunner().invoke(app, ["serve", "--every", "0"]).exit_code == 0
    assert captured["app"].state.witness == WitnessWatch(every_seconds=900, estate_watched="fly", raw_every="900")
    monkeypatch.delenv("FIELD_WITNESS_EVERY")
    assert CliRunner().invoke(app, ["serve", "--every", "0"]).exit_code == 0
    assert captured["app"].state.witness is None
