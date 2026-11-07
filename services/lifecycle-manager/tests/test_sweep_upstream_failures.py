"""S9-10: a registry or delegation failure during a sweep is a named refusal, and a dropped ledger note is counted.

`LifecycleEngine.sweep` read `registry.list_agents()` and `delegation.get('/tokens')` bare. A 502 body is `{"detail": ...}`, so iterating it
gave the str 'detail' and `.get` raised AttributeError (a 500 at POST /sweep, an `ErrorType: text` in the tick); a 200 `{}` silently
reported 0 tokens, i.e. "nothing expires"; an unreachable registry was a 500. `_ledger_note` swallowed every append failure with no log and no
count. Now: each failure raises `LifecycleError` naming the step with the status or the exception TYPE only (never response text), POST /sweep
answers 502 with that fixed text, `scheduled_tick` records `{ok: False, error: <the same text>}`, nothing is ledgered or killed in the failing cases,
and a failed note is logged (type only) and counted in `SweepReport.ledger_notes_dropped` (default 0, additive)."""

import logging
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from field_core.clients import RegistryUnreachableError
from lifecycle_manager.api import create_app, scheduled_tick
from lifecycle_manager.engine import LifecycleEngine, LifecycleError, render_markdown

from test_roster_aliases import FakeRegistry, NoTokens, RecordingLedger, agent

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
ROSTER = "owner\nVerifier\n"
MARK = "UPSTREAM-BODY-MARKER-3308"


class Resp:
    def __init__(self, status, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError(MARK)
        return self._body


class Delegation:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc = resp, exc

    def get(self, path):
        if self.exc:
            raise self.exc
        return self.resp


class DownRegistry:
    def list_agents(self):
        raise RegistryUnreachableError(f"connection refused {MARK}")


class Kill:
    def __init__(self):
        self.calls = []

    def post(self, *a, **k):
        self.calls.append(a)
        return Resp(200)


class FailingLedger:
    def __init__(self):
        self.attempts = 0

    def append(self, *a, **k):
        self.attempts += 1
        raise ConnectionError(f"ledger down {MARK}")


def engine(registry=None, delegation=None, ledger=None, kill=None):
    return LifecycleEngine(registry=registry or FakeRegistry([agent("orphan-1", "Nobody")]),
                           delegation=delegation or NoTokens(), ledger=ledger, killswitch=kill)


BAD_DELEGATION = {
    "502-dict": (Delegation(Resp(502, {"detail": MARK})), "delegation token listing failed: HTTP 502"),
    "401": (Delegation(Resp(401, {"detail": MARK})), "delegation token listing failed: HTTP 401"),
    "200-empty-dict": (Delegation(Resp(200, {})), "delegation token listing failed: the answer is not a list of objects"),
    "200-list-of-str": (Delegation(Resp(200, ["a", "b"])), "delegation token listing failed: the answer is not a list of objects"),
    "200-not-json": (Delegation(Resp(200, bad_json=True)), "delegation token listing failed: the answer is unreadable (ValueError)"),
    "transport": (Delegation(exc=ConnectionError(f"refused {MARK}")), "delegation token listing failed: unreachable (ConnectionError)"),
}


@pytest.mark.parametrize("name", list(BAD_DELEGATION))
def test_a_bad_delegation_answer_is_a_named_refusal_with_no_write_and_no_kill(name):
    delegation, text = BAD_DELEGATION[name]
    ledger, kill = RecordingLedger(), Kill()
    with pytest.raises(LifecycleError) as caught:
        LifecycleEngine(registry=FakeRegistry([agent("o", "Nobody")]), delegation=delegation, ledger=ledger,
                        killswitch=kill).sweep(ROSTER, now=NOW)
    assert str(caught.value) == text and MARK not in str(caught.value)
    assert ledger.events == [] and kill.calls == []


def test_an_unreachable_registry_is_a_named_refusal_with_no_write():
    ledger = RecordingLedger()
    with pytest.raises(LifecycleError) as caught:
        LifecycleEngine(registry=DownRegistry(), delegation=NoTokens(), ledger=ledger).sweep(ROSTER, now=NOW)
    assert str(caught.value) == "registry listing failed: unreachable" and MARK not in str(caught.value)
    assert ledger.events == []


def test_a_good_answer_is_unchanged_a_plain_list_and_a_200_response_both_work():
    assert engine(delegation=Delegation(Resp(200, []))).sweep(ROSTER, now=NOW).tokens_scanned == 0
    assert engine().sweep(ROSTER, now=NOW).agents_scanned == 1


@pytest.mark.parametrize("name", list(BAD_DELEGATION))
def test_post_sweep_answers_502_with_the_fixed_text(tmp_path, monkeypatch, name):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    delegation, text = BAD_DELEGATION[name]
    served = create_app(registry=FakeRegistry([agent("o", "Nobody")]), delegation=delegation, ledger=RecordingLedger(), every=0)
    r = TestClient(served, raise_server_exceptions=False).post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 502 and r.json() == {"detail": text} and MARK not in r.text


def test_post_sweep_with_an_unreachable_registry_is_502(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    served = create_app(registry=DownRegistry(), delegation=NoTokens(), ledger=RecordingLedger(), every=0)
    r = TestClient(served, raise_server_exceptions=False).post("/sweep", json={"roster_csv": ROSTER})
    assert r.status_code == 502 and r.json() == {"detail": "registry listing failed: unreachable"}


def test_the_scheduled_tick_records_the_fixed_text_and_survives(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    roster = tmp_path / "owners.csv"
    roster.write_text(ROSTER, encoding="utf-8")
    monkeypatch.setenv("FIELD_LIFECYCLE_ROSTER", str(roster))
    delegation, text = BAD_DELEGATION["502-dict"]
    served = create_app(registry=FakeRegistry([agent("o", "Nobody")]), delegation=delegation, ledger=RecordingLedger(), every=0)
    assert scheduled_tick(served) == {"ok": False, "error": text}


def test_failed_ledger_notes_are_counted_logged_by_type_and_do_not_stop_the_sweep(caplog):
    ledger = FailingLedger()
    agents = [agent("o1", "Nobody"), agent("o2", "Nobody Else")]
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        report = engine(registry=FakeRegistry(agents), ledger=ledger).sweep(ROSTER, now=NOW)
    assert report.ledger_notes_dropped == ledger.attempts == 2
    assert report.escalations_written == 0 and len(report.orphans) == 2
    assert "ConnectionError" in caplog.text and MARK not in caplog.text


def test_the_dropped_count_is_zero_by_default_and_with_a_working_ledger_and_shown_only_when_nonzero():
    ledger = RecordingLedger()
    ok = engine(ledger=ledger).sweep(ROSTER, now=NOW)
    assert ok.ledger_notes_dropped == 0 and ok.escalations_written == 1
    assert "dropped" not in render_markdown(ok)
    bad = engine(ledger=FailingLedger()).sweep(ROSTER, now=NOW)
    assert "Ledger notes dropped:* 1" in render_markdown(bad)


def test_no_ledger_at_all_is_not_a_drop():
    assert engine(ledger=None).sweep(ROSTER, now=NOW).ledger_notes_dropped == 0
