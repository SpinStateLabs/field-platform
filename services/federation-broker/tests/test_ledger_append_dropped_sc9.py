"""A crossing verdict whose ledger append fails still stands, but the loss is no longer
silent (scout round 3 note, S-C9). `BrokerEngine._verdict` caught every exception with a bare
`pass`: a lost federation.allow/block/escalate audit event left no log line, no counter and no
trace in /health (spend-governor already counts its own as `ledger_appends_dropped`). Now the
drop is counted, logged (exception TYPE only) and shown in /health. The verdict is unchanged."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, CrossingRequest
from field_core.conformance import Decision

MARK = "zz-marker-do-not-echo"


class _Ledger:
    def __init__(self, raises: Exception | None = None):
        self.raises, self.events = raises, []

    def append(self, event_type, payload=None, agent_id=None):
        if self.raises is not None:
            raise self.raises
        self.events.append((event_type, payload, agent_id))


def _req():
    # The manifest is not read by `_verdict` (it only builds the verdict and appends); the
    # request model just requires one for an outbound crossing.
    return CrossingRequest(direction="outbound", counterparty_org="Borealis Example Corp",
                           agent_id="invoicing-agent", scope="exchange invoice status",
                           data_class="invoice metadata", manifest={"placeholder": True})


def _engine(tmp_path, ledger):
    return BrokerEngine(ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)


def _verdict(engine):
    return engine._verdict(_req(), Decision.BLOCK, "F.peer", ["not allowed"])


def test_a_failed_append_is_counted_and_the_verdict_is_unchanged(tmp_path):
    ok = _verdict(_engine(tmp_path / "a", _Ledger()))
    eng = _engine(tmp_path / "b", _Ledger(raises=ConnectionError(MARK)))
    v = _verdict(eng)
    assert eng.ledger_appends_dropped == 1
    assert (v.decision, v.clause_id, v.reasons, v.agent_id, v.action) == (
        ok.decision, ok.clause_id, ok.reasons, ok.agent_id, ok.action)


def test_every_failed_append_is_counted(tmp_path):
    eng = _engine(tmp_path, _Ledger(raises=TimeoutError()))
    for _ in range(3):
        _verdict(eng)
    assert eng.ledger_appends_dropped == 3


@pytest.mark.parametrize("ledger", [None, _Ledger()], ids=["no-ledger", "working-ledger"])
def test_nothing_dropped_when_there_is_no_ledger_or_it_works(tmp_path, ledger):
    eng = _engine(tmp_path, ledger)
    _verdict(eng)
    assert eng.ledger_appends_dropped == 0


def test_the_working_ledger_still_gets_the_event(tmp_path):
    led = _Ledger()
    _verdict(_engine(tmp_path, led))
    assert [e[0] for e in led.events] == ["federation.block"]


def test_the_drop_is_logged_with_the_event_type_and_exception_type_never_the_message(tmp_path, caplog):
    eng = _engine(tmp_path, _Ledger(raises=ConnectionError(MARK)))
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        _verdict(eng)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "federation.block" in text and "ConnectionError" in text and "dropped" in text
    assert MARK not in text


def test_health_shows_the_counter_zero_then_the_drops(tmp_path):
    eng = _engine(tmp_path, _Ledger(raises=OSError()))
    c = TestClient(create_app(engine=eng))
    assert c.get("/health").json()["ledger_appends_dropped"] == 0
    _verdict(eng)
    _verdict(eng)
    assert c.get("/health").json()["ledger_appends_dropped"] == 2


def test_health_keeps_its_existing_fields(tmp_path):
    h = TestClient(create_app(engine=_engine(tmp_path, None))).get("/health").json()
    for key in ("ok", "service", "version", "home_org", "build_sha"):
        assert key in h
    assert h["ledger_appends_dropped"] == 0
