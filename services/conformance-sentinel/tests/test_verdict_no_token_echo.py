"""The sentinel's verdict never echoes the delegation token id back to the caller (backlog 2026-11-13).

POST /check used to return ``context.token_id`` = the id the caller presented. git-post-agent quoted a ledger-adjacent
verdict verbatim and wrote the live token id into its report file. The verdict now carries ``token_ref`` (first 12 hex of
sha256(token_id): correlatable, not the token) and ``token_presented``; the id itself is in no response body. The
delegation-authority /introspect call still receives the real id (that is the credential check)."""

import hashlib

import pytest

from conformance_sentinel.mode import SentinelMode
from tests.conftest import AGENT_ID


def ref(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _post(stack, action, token, **extra):
    body = {"agent_id": AGENT_ID, "action": action, "token_id": token, "irreversible": False, **extra}
    r = stack.sentinel.post("/check", json=body)
    assert r.status_code == 200, r.text
    return r


def _assert_clean(r, token):
    assert token not in r.text, "the response repeats the token id"
    ctx = r.json()["context"]
    assert "token_id" not in ctx
    assert len(ctx["token_ref"]) == 12 and ctx["token_ref"] == ref(token) and ctx["token_presented"] is True


def test_allow_verdict_has_no_token_id(stack):
    stack.set_cap()
    token = stack.mint_token()
    r = _post(stack, "draft invoices", token)
    assert r.json()["decision"] == "ALLOW"
    _assert_clean(r, token)


@pytest.mark.parametrize("action,decision", [("transfer funds", "BLOCK"), ("send invoice email", "ESCALATE")])
def test_block_and_escalate_verdicts_have_no_token_id(stack, action, decision):
    stack.set_cap()
    token = stack.mint_token()
    r = _post(stack, action, token)
    assert r.json()["decision"] == decision
    _assert_clean(r, token)


def test_log_only_shadow_verdict_has_no_token_id(stack):
    stack.set_cap()
    token = stack.mint_token()
    stack.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY
    r = _post(stack, "transfer funds", token)
    assert r.json()["context"]["shadowed"] is True
    _assert_clean(r, token)


def test_failed_allow_record_block_has_no_token_id(stack, monkeypatch):
    stack.set_cap()
    token = stack.mint_token()
    engine = stack.sentinel.app.state.engine

    def boom(*a, **k):
        raise RuntimeError("socket closed mid-append")

    monkeypatch.setattr(engine.ledger, "append", boom)
    r = _post(stack, "draft invoices", token)
    assert r.json()["clause_id"] == "L.unreachable"
    _assert_clean(r, token)


def test_no_token_presented_is_reported_as_such(stack):
    r = stack.sentinel.post("/check", json={"agent_id": AGENT_ID, "action": "draft invoices"})
    assert r.status_code == 200, r.text
    ctx = r.json()["context"]
    assert "token_id" not in ctx
    assert ctx["token_presented"] is False and ctx["token_ref"] is None


def test_a_forged_token_id_is_not_repeated_either(stack):
    forged = "FORGED-TOKEN-ID-0123456789"
    r = _post(stack, "draft invoices", forged)
    assert r.json()["decision"] == "BLOCK"
    assert forged not in r.text
