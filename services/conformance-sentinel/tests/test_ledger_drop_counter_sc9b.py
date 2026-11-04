"""A lost sentinel audit append (log-only shadow, judge record, metering gap)
is counted, logged by exception type only, shown in /health, and never
changes the verdict."""

import logging

from conformance_sentinel.judge import MockJudgeClient
from conformance_sentinel.mode import SentinelMode
from tests.test_judge import _arm

CANARY = "CANARY-secret-9f3a"


class _Boom(Exception):
    pass


def _fail_appends(engine, monkeypatch, types=None):
    def boom(event_type, *a, **k):
        if types is None or event_type in types:
            raise _Boom(CANARY)
        return None

    monkeypatch.setattr(engine.ledger, "append", boom)


def _health(stack):
    return stack.sentinel.get("/health").json()


def test_health_starts_at_zero(stack):
    assert _health(stack)["ledger_appends_dropped"] == 0
    assert stack.sentinel.app.state.engine.ledger_appends_dropped == 0


def test_log_only_shadow_drop_counted_verdict_unchanged(stack, monkeypatch, caplog):
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine
    engine.mode = SentinelMode.LOG_ONLY
    _fail_appends(engine, monkeypatch)
    with caplog.at_level(logging.WARNING):
        v = stack.check("transfer funds", token_id=token)
    assert v["decision"] == "ALLOW" and v["context"]["shadowed"] is True
    assert v["context"]["would_be"] == {"decision": "BLOCK", "clause_id": "D.scope"}
    assert _health(stack)["ledger_appends_dropped"] >= 1
    assert "_Boom" in caplog.text
    assert CANARY not in caplog.text


def test_judge_record_drop_counted_verdict_unchanged(stack, monkeypatch, caplog):
    _arm(stack, rules={"read the new timesheets": (True, 0.95, "ok")})
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine
    _fail_appends(engine, monkeypatch, types={"sentinel.judge"})
    with caplog.at_level(logging.WARNING):
        v = stack.check("read the new timesheets", token_id=token)
    assert v["decision"] == "ALLOW"
    assert engine.ledger_appends_dropped == 1
    assert _health(stack)["ledger_appends_dropped"] == 1
    assert "_Boom" in caplog.text and CANARY not in caplog.text


def test_metering_gap_drop_counted_verdict_unchanged(stack, monkeypatch, caplog):
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine

    def gov_boom(*a, **k):
        raise ConnectionError("governor /spend returned 500")

    monkeypatch.setattr(engine.governor, "record_action", gov_boom)
    _fail_appends(engine, monkeypatch, types={"sentinel.metering_gap"})
    with caplog.at_level(logging.WARNING):
        v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and v["context"]["reason"] == "metering_gap"
    assert engine.ledger_appends_dropped == 1
    assert _health(stack)["ledger_appends_dropped"] == 1
    assert "_Boom" in caplog.text and CANARY not in caplog.text


def test_successful_appends_do_not_count(stack):
    stack.set_cap()
    token = stack.mint_token()
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW"
    assert _health(stack)["ledger_appends_dropped"] == 0
