"""B-GL-incident-replay-503: a replay waits out a busy ledger's 503 + Retry-After within a bounded budget.

PR 1089 gives the ledger one whole-ledger slot: a second GET /verify (or unfiltered GET /events) answers 503 with a
Retry-After. Inside ``ReplayEngine.replay`` that answer is waited out and the call repeated (each wait at most
RETRY_AFTER_CAP_S, MAX_RETRIES_PER_CALL retries per call, FIELD_REPLAY_RETRY_BUDGET_S seconds in all, default 20,
0 = never). When the budget runs out, /verify becomes the existing "ledger busy:" result (INTEGRITY NOT VERIFIED: never
intact, never broken) and the events read raises LedgerBusyError, which the API answers 503 + Retry-After. Outside a replay
nothing is retried. No real sleeping: ``engine._sleep`` is replaced.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from field_core.clients import AgentNotRegisteredError
from incident_replay import engine as eng
from incident_replay.api import create_app
from incident_replay.engine import LedgerBusyError, LedgerQueryClient, ReplayEngine, ReplayRequest

ENV = "FIELD_REPLAY_RETRY_BUDGET_S"
REQ = {"agent_id": "invoicing-agent", "since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}
OK_VERIFY = {"ok": True, "length": 4, "first_break_index": None, "reason": None, "segments": 1,
             "archived_segments": 0, "verified_events": 4, "break_segment": None}


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Fake:
    """Scripted ledger: path -> list of Resp (the last repeats). Records every call."""

    def __init__(self, verify=None, events=None):
        self.script = {"/verify": list(verify or [Resp(200, OK_VERIFY)]), "/events": list(events or [Resp(200, [])])}
        self.calls: list[str] = []

    def get(self, url, params=None):
        path = "/" + url.rsplit("/", 1)[-1]
        self.calls.append(path)
        q = self.script[path]
        return q.pop(0) if len(q) > 1 else q[0]


class NoRegistry:
    def get_agent(self, agent_id):
        raise AgentNotRegisteredError(agent_id)


class NoTokens:
    def tokens(self, agent_id):
        return []


class NoManifests:
    def resolve_detail(self, ref):
        return None, "no_ref"


def engine_for(fake):
    return ReplayEngine(ledger=LedgerQueryClient(client=fake, base_url="http://t"), registry=NoRegistry(),
                        delegation=NoTokens(), manifests=NoManifests())


@pytest.fixture()
def sleeps(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    waited: list[float] = []
    monkeypatch.setattr(eng, "_sleep", lambda s: waited.append(s))
    return waited


BUSY = Resp(503, None, {"Retry-After": "2"})


def calls_of(fake, path):
    return [c for c in fake.calls if c == path]


def test_a_busy_verify_is_waited_out_and_the_replay_is_intact(sleeps):
    fake = Fake(verify=[BUSY, BUSY, Resp(200, OK_VERIFY)])
    pm = engine_for(fake).replay(ReplayRequest(**REQ))
    assert sleeps == [2, 2] and len(calls_of(fake, "/verify")) == 3
    assert pm.ledger_integrity_status == "intact" and pm.ledger_integrity_ok is True


def test_a_verify_that_stays_busy_is_not_verified_never_intact_never_broken(sleeps):
    fake = Fake(verify=[BUSY])
    pm = engine_for(fake).replay(ReplayRequest(**REQ))
    assert pm.ledger_integrity_status == "unverified" and pm.ledger_integrity_ok is False
    assert "INTEGRITY NOT VERIFIED" in pm.ledger_integrity_detail and "ledger busy:" in pm.ledger_integrity_detail
    assert len(calls_of(fake, "/verify")) == 1 + eng.MAX_RETRIES_PER_CALL


def test_a_busy_events_read_is_waited_out(sleeps):
    fake = Fake(events=[BUSY, Resp(200, [])])
    pm = engine_for(fake).replay(ReplayRequest(**REQ))
    assert sleeps == [2] and len(calls_of(fake, "/events")) == 2 and pm.timeline == []


def test_an_events_read_that_stays_busy_raises_ledger_busy(sleeps):
    fake = Fake(events=[Resp(503, None, {"Retry-After": "7"})])
    with pytest.raises(LedgerBusyError) as exc:
        engine_for(fake).replay(ReplayRequest(**REQ))
    assert str(exc.value).startswith("ledger busy:") and exc.value.retry_after == 7


def test_the_api_answers_503_with_retry_after_when_the_events_read_stays_busy(sleeps):
    client = TestClient(create_app(engine=engine_for(Fake(events=[Resp(503, None, {"Retry-After": "7"})]))))
    for path in ("/replay", "/replay/markdown"):
        r = client.post(path, json=REQ)
        assert r.status_code == 503 and r.json()["detail"].startswith("ledger busy:")
        assert r.headers["retry-after"] == "7"


def test_the_refusal_retry_after_is_capped_and_defaulted(sleeps):
    for header, want in (("3600", eng.RETRY_AFTER_CAP_S), ("", eng.DEFAULT_REFUSAL_RETRY_AFTER_S)):
        fake = Fake(events=[Resp(503, None, {"Retry-After": header} if header else {})])
        with pytest.raises(LedgerBusyError) as exc:
            engine_for(fake).replay(ReplayRequest(**REQ))
        assert exc.value.retry_after == want


def test_a_503_without_a_usable_retry_after_is_not_retried(sleeps):
    for headers in ({}, {"Retry-After": "soon"}, {"Retry-After": "-5"}, {"Retry-After": "1.5"},
                    {"Retry-After": "Wed, 21 Nov 2026 12:00:00 GMT"}):
        fake = Fake(verify=[Resp(503, None, headers), Resp(200, OK_VERIFY)])
        pm = engine_for(fake).replay(ReplayRequest(**REQ))
        assert sleeps == [] and len(calls_of(fake, "/verify")) == 1
        assert pm.ledger_integrity_status == "unverified"


@pytest.mark.parametrize("status", [500, 502, 429, 401, 404])
def test_no_other_status_is_retried_and_it_is_still_an_error(sleeps, status):
    fake = Fake(verify=[Resp(status, None, {"Retry-After": "2"})])
    with pytest.raises(RuntimeError):
        engine_for(fake).replay(ReplayRequest(**REQ))
    assert sleeps == [] and len(calls_of(fake, "/verify")) == 1


def test_a_200_ok_false_ledger_busy_verify_is_unchanged(sleeps):
    busy = {"ok": False, "length": 0, "reason": "ledger busy: no consistent snapshot after 10 attempts"}
    pm = engine_for(Fake(verify=[Resp(200, busy)])).replay(ReplayRequest(**REQ))
    assert pm.ledger_integrity_status == "unverified" and sleeps == []


def test_each_wait_is_capped(sleeps):
    fake = Fake(verify=[Resp(503, None, {"Retry-After": "3600"}), Resp(200, OK_VERIFY)])
    engine_for(fake).replay(ReplayRequest(**REQ))
    assert sleeps == [eng.RETRY_AFTER_CAP_S]


def test_the_replay_budget_bounds_the_total_waiting(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "5")
    fake = Fake(verify=[BUSY], events=[BUSY])
    with pytest.raises(LedgerBusyError):
        engine_for(fake).replay(ReplayRequest(**REQ))
    assert 4 <= sum(sleeps) <= 5


def test_a_budget_of_zero_never_retries(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "0")
    pm = engine_for(Fake(verify=[BUSY, Resp(200, OK_VERIFY)])).replay(ReplayRequest(**REQ))
    assert sleeps == [] and pm.ledger_integrity_status == "unverified"


@pytest.mark.parametrize("raw", ["abc", "-3", "", "1.5", "9" * 5000])
def test_a_bad_budget_is_the_default_twenty(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert eng.retry_budget_s() == 20


def test_the_budget_is_per_replay(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "2")
    for _ in range(2):
        engine_for(Fake(verify=[BUSY, Resp(200, OK_VERIFY)])).replay(ReplayRequest(**REQ))
    assert sleeps == [2, 2]


def test_the_ledger_client_outside_a_replay_never_retries(sleeps):
    fake = Fake(verify=[BUSY, Resp(200, OK_VERIFY)])
    out = LedgerQueryClient(client=fake, base_url="http://t").verify()
    assert sleeps == [] and len(fake.calls) == 1 and out["ok"] is False and out["reason"].startswith("ledger busy:")
