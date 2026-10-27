"""Sentinel side of P30 item 5: a caller's allow-listed correlation ids
(the claude-approver's source / console_session_id / ...) are on the
conformance ledger rows, so a Console session correlates by id. Visibility
only: the verdict and the decision are unchanged."""

from conformance_sentinel.mode import SentinelMode
from tests.conftest import AGENT_ID

APPROVER_CONTEXT = {
    "source": "claude-approver",
    "console_session_id": "sesn_01LYJ1mZ5RtNnD7hmAoyVY6V",
    "console_agent_id": "agent_01abc",
    "tool_name": "bash",
    "event_id": "sevt_01xyz",
    "event_type": "agent.tool_use",
}
EXPECTED = {
    "source": "claude-approver",
    "console_session_id": "sesn_01LYJ1mZ5RtNnD7hmAoyVY6V",
    "console_agent_id": "agent_01abc",
    "event_id": "sevt_01xyz",
}


def _check(stack, action, token, context=None):
    body = {"agent_id": AGENT_ID, "action": action, "token_id": token, "irreversible": False}
    if context is not None:
        body["context"] = context
    r = stack.sentinel.post("/check", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _events(stack, event_type):
    return stack.ledger.get("/events", params={"event_type": event_type}).json()


def test_allow_row_carries_the_callers_correlation_ids(stack):
    stack.set_cap()
    token = stack.mint_token()
    v = _check(stack, "draft invoices", token, APPROVER_CONTEXT)
    assert v["decision"] == "ALLOW"
    (row,) = _events(stack, "conformance.allow")
    assert row["payload"]["caller_context"] == EXPECTED
    assert row["payload"]["action"] == "draft invoices"
    # the verdict does not echo it (ledger visibility only)
    assert "caller_context" not in v["context"]


def test_block_and_escalate_rows_carry_them_too(stack):
    stack.set_cap()
    token = stack.mint_token()
    assert _check(stack, "transfer funds", token, APPROVER_CONTEXT)["decision"] == "BLOCK"
    assert _check(stack, "send invoice email", token, APPROVER_CONTEXT)["decision"] == "ESCALATE"
    (block,) = _events(stack, "conformance.block")
    (esc,) = _events(stack, "conformance.escalate")
    assert block["payload"]["caller_context"] == EXPECTED
    assert block["payload"]["clause_id"] == "D.scope"
    assert esc["payload"]["caller_context"] == EXPECTED


def test_log_only_shadow_rows_carry_them(stack):
    stack.set_cap()
    token = stack.mint_token()
    stack.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY
    v = _check(stack, "transfer funds", token, APPROVER_CONTEXT)
    assert v["decision"] == "ALLOW" and v["context"]["shadowed"] is True
    (row,) = _events(stack, "conformance.shadow_block")
    assert row["payload"]["caller_context"] == EXPECTED
    assert row["payload"]["would_block"] == "D.scope"


def test_metering_gap_row_carries_them(stack, monkeypatch):
    stack.set_cap()
    engine = stack.sentinel.app.state.engine

    def boom(*a, **k):
        raise ConnectionError("governor /spend returned 500")

    monkeypatch.setattr(engine.governor, "record_action", boom)
    token = stack.mint_token()
    v = _check(stack, "draft invoices", token, {"source": "my-agent", "session_id": "s-42"})
    assert v["decision"] == "ALLOW" and v["context"]["reason"] == "metering_gap"
    (gap,) = _events(stack, "sentinel.metering_gap")
    assert gap["payload"]["caller_context"] == {"source": "my-agent", "session_id": "s-42"}


def test_no_or_irrelevant_context_adds_no_key(stack):
    stack.set_cap()
    token = stack.mint_token()
    _check(stack, "draft invoices", token)
    _check(stack, "draft invoices", token, {"tool_name": "bash", "source": 7, "session_id": ""})
    rows = _events(stack, "conformance.allow")
    assert len(rows) == 2
    assert all("caller_context" not in r["payload"] for r in rows)


def test_untrusted_values_are_cleaned_and_bounded(stack):
    stack.set_cap()
    token = stack.mint_token()
    _check(stack, "draft invoices", token,
           {"source": "line1\nline2", "console_session_id": "s" * 1000,
            "secret_key": "must-not-reach-the-ledger"})
    (row,) = _events(stack, "conformance.allow")
    assert row["payload"]["caller_context"] == {"source": "line1 line2",
                                                "console_session_id": "s" * 200}
    assert "must-not-reach-the-ledger" not in str(row)


def test_context_never_changes_the_decision(stack):
    stack.set_cap()
    token = stack.mint_token()
    for action, decision in (("draft invoices", "ALLOW"), ("transfer funds", "BLOCK")):
        bare = _check(stack, action, token)
        with_ctx = _check(stack, action, token, APPROVER_CONTEXT)
        assert (bare["decision"], bare["clause_id"]) == (with_ctx["decision"], with_ctx["clause_id"])
        assert bare["decision"] == decision
