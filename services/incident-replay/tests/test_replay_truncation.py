"""S3-12: a replay reads at most MAX_TIMELINE_EVENTS ledger events and SAYS when it was
cut. Before, `replay` asked the ledger for every matching event with no limit, so one
long window loaded an agent's whole history into one response. The ledger's `limit` keeps
the LAST N matches, so a cut drops the EARLIEST events; that could hide the real
first_failure, hence the integrity note (also shown by render_markdown)."""
from __future__ import annotations

import pytest

from incident_replay import engine as engine_mod
from incident_replay.engine import ReplayEngine, ReplayRequest, render_markdown

AGENT = "trunc-agent"
REQ = ReplayRequest(agent_id=AGENT, since="2020-01-01T00:00:00+00:00",
                    until="2030-01-01T00:00:00+00:00")
MARK = "zz-do-not-echo"


class _Ledger:
    """Honours `limit` the way the sealed ledger does: keeps the LAST N matches."""

    def __init__(self, events):
        self.all, self.params = list(events), []

    def verify(self):
        return {"ok": True, "length": len(self.all)}

    def events(self, **params):
        self.params.append(params)
        limit = params.get("limit")
        return self.all[-limit:] if limit is not None else list(self.all)

    def health(self):
        return {}


class _Registry:
    def get_agent(self, agent_id):
        return {"agent_id": agent_id, "name": "T", "owner": "O", "domain": "d",
                "status": "active", "manifest_ref": None}


class _Delegation:
    def tokens(self, agent_id):
        return []


def _ev(n, event_type="conformance.allow"):
    return {"ts": f"2026-01-01T00:{n // 60:02d}:{n % 60:02d}+00:00", "event_type": event_type,
            "hash": f"h{n}", "payload": {"action": f"a{n}"}}


def _replay(events):
    led = _Ledger(events)
    return ReplayEngine(led, _Registry(), _Delegation()).replay(REQ), led


@pytest.fixture(autouse=True)
def _cap(monkeypatch):
    monkeypatch.delenv("FIELD_REPLAY_MAX_EVENTS", raising=False)


def test_default_cap_is_5000_and_the_ledger_is_asked_for_cap_plus_one():
    assert engine_mod.MAX_TIMELINE_EVENTS == 5000
    _, led = _replay([_ev(1)])
    assert led.params[0]["limit"] == 5001


def test_under_the_cap_nothing_changes(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "10")
    pm, _ = _replay([_ev(n) for n in range(10)])  # exactly the cap: not truncated
    assert len(pm.timeline) == 10
    assert pm.integrity_notes == []
    assert "timeline truncated" not in render_markdown(pm)


def test_over_the_cap_keeps_the_newest_n_and_says_so(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "10")
    pm, _ = _replay([_ev(n) for n in range(25)])
    assert [t.hash for t in pm.timeline] == [f"h{n}" for n in range(15, 25)]
    assert any("timeline truncated" in n and "first_failure may be earlier" in n
               for n in pm.integrity_notes)
    assert "timeline truncated" in render_markdown(pm)


def test_a_ledger_that_ignores_limit_is_still_cut_to_n(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "10")

    class _Deaf(_Ledger):
        def events(self, **params):
            return list(self.all)

    led = _Deaf([_ev(n) for n in range(25)])
    pm = ReplayEngine(led, _Registry(), _Delegation()).replay(REQ)
    assert len(pm.timeline) == 10 and pm.timeline[-1].hash == "h24"
    assert any("timeline truncated" in n for n in pm.integrity_notes)


def test_first_failure_comes_only_from_what_was_read(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "10")
    events = [_ev(0, "conformance.block")] + [_ev(n) for n in range(1, 24)] + [_ev(24, "conformance.block")]
    pm, _ = _replay(events)
    assert pm.first_failure is not None and pm.first_failure.hash == "h24"  # h0 was cut; the note says so
    assert any("first_failure may be earlier" in n for n in pm.integrity_notes)


@pytest.mark.parametrize("raw", ["", "abc", "nan", "inf", "-5", "0", "1.5", "10001", MARK])
def test_garbage_cap_falls_back_to_the_default(monkeypatch, raw):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", raw)
    assert engine_mod.max_timeline_events() == 5000


def test_a_good_cap_is_used_and_bounded_by_the_ledger_limit(monkeypatch):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "9999")
    assert engine_mod.max_timeline_events() == 9999
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", "1")
    assert engine_mod.max_timeline_events() == 1
