"""S7-21 — a failed crossing ledger append is counted, logged by class and decision only,
shown in /health, and never changes the verdict (best-effort delivery)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, CrossingRequest
from field_core.conformance import Decision

SECRET_SCOPE = "SCOPE-TEXT-MUST-NOT-LEAK"
EXC_TEXT = "EXC-TEXT-MUST-NOT-LEAK"


class FailingLedger:
    def append(self, *a, **k):
        raise RuntimeError(EXC_TEXT)


class GoodLedger:
    def __init__(self):
        self.calls = 0

    def append(self, *a, **k):
        self.calls += 1


def _req(scope=SECRET_SCOPE):
    return CrossingRequest(counterparty_org="Org B", counterparty_agent_id="b-agent",
                           counterparty_manifest={}, scope=scope, data_class="x")


def _engine(tmp_path, ledger):
    return BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=ledger)


@pytest.mark.parametrize("decision", [Decision.ALLOW, Decision.BLOCK])
def test_the_verdict_is_the_same_with_a_failing_ledger(tmp_path, decision):
    good, bad = GoodLedger(), FailingLedger()
    a = _engine(tmp_path, good)._verdict(_req(), decision, "F.x", ["r"])
    b = _engine(tmp_path, bad)._verdict(_req(), decision, "F.x", ["r"])
    assert good.calls == 1
    assert a.model_dump(exclude={"checked_at"}) == b.model_dump(exclude={"checked_at"})


def test_the_failure_is_counted_and_logged_without_exception_or_scope_text(tmp_path, caplog):
    eng = _engine(tmp_path, FailingLedger())
    with caplog.at_level(logging.WARNING, logger="federation_broker.engine"):
        eng._verdict(_req(), Decision.BLOCK, "F.x", ["r"])
        eng._verdict(_req(), Decision.ALLOW, "F.x", ["r"])
    assert eng.ledger_append_failures == 2
    text = caplog.text
    assert "RuntimeError" in text and "BLOCK" in text and "ALLOW" in text
    assert EXC_TEXT not in text and SECRET_SCOPE not in text


def test_a_working_ledger_counts_nothing(tmp_path):
    eng = _engine(tmp_path, GoodLedger())
    eng._verdict(_req(), Decision.ALLOW, "F.x", [])
    assert eng.ledger_append_failures == 0


def test_health_shows_the_count_and_keeps_its_other_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    client = TestClient(create_app(engine=_engine(tmp_path, FailingLedger())))
    before = client.get("/health").json()
    assert before["ledger_append_failures"] == 0
    r = client.post("/crossing", json={
        "counterparty_org": "Org B", "counterparty_agent_id": "b",
        "counterparty_manifest": {}, "scope": SECRET_SCOPE, "data_class": "x"})
    assert r.status_code == 200, r.text
    after = client.get("/health").json()
    assert after["ledger_append_failures"] >= 1
    assert {k: v for k, v in after.items() if k != "ledger_append_failures"} == \
           {k: v for k, v in before.items() if k != "ledger_append_failures"}
