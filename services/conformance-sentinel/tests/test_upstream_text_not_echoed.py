"""S11-24: another service's exception text and an unbounded upstream model name never reach a verdict, a ledger row or an
exception message.

`{exc}` of a failed upstream call (httpx text can carry the URL, userinfo included) was interpolated into verdict reasons
that POST /check returns and the ledger records; the judge took `model` from the upstream body with no type or length
check and it went to the governor's /usage, the ledger and a BLOCK reason; `Governor.check` put the exception text in
the ActionBlocked reason. Now: the exception class only (the judge's own fixed-text JudgeError keeps its text, which is
built from a class name or a status), `model` only when it is a short printable string, `cited_scope` a string or None.
"""
from __future__ import annotations

import httpx
import pytest

from conformance_sentinel.governed import ActionBlocked, Governor
from conformance_sentinel.judge import AnthropicJudgeClient
from tests.conftest import AGENT_ID  # noqa: F401
from tests.test_judge import _arm

LEAK = "https://user:pw@h.example.test/x?token=t0k"
KEY = "sk-ant-DUMMY-S1124-KEY-0123456789"
PARAPHRASE = "draft the march invoices"


def _engine(stack):
    return stack.sentinel.app.state.engine


def _no_leak(text):
    for piece in ("user:pw", "t0k", "h.example.test", "https://"):
        assert piece not in text, piece


def _ledger_text(stack):
    return str(stack.ledger.get("/events").json())


# -- (1) the three judge-gate reasons --------------------------------------------------------------------------------


def test_a_governor_status_failure_names_the_class_only(stack, monkeypatch):
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setattr(_engine(stack).governor, "status",
                        lambda agent_id, **kw: (_ for _ in ()).throw(RuntimeError(f"down {LEAK}")))
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert v["decision"] == "ESCALATE" and v["clause_id"] == "D.semantic"
    assert "RuntimeError" in v["reasons"][0] and "unverifiable" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))
    _no_leak(_ledger_text(stack))


def test_a_judge_failure_names_the_class_only(stack, monkeypatch):
    mock = _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setattr(mock, "judge", lambda *a, **k: (_ for _ in ()).throw(ConnectionError(f"boom {LEAK}")))
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert v["decision"] == "ESCALATE" and v["clause_id"] == "D.semantic"
    assert "ConnectionError" in v["reasons"][0] and "judge failed" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))
    _no_leak(_ledger_text(stack))


def test_the_judges_own_fixed_text_error_keeps_its_text(stack, monkeypatch):
    from conformance_sentinel.judge import JudgeError
    mock = _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setattr(mock, "judge", lambda *a, **k: (_ for _ in ()).throw(JudgeError("judge upstream returned 503")))
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert "judge upstream returned 503" in v["reasons"][0]


def test_an_unmeterable_judgment_names_the_class_only(stack, monkeypatch):
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setattr(_engine(stack).governor, "report_usage",
                        lambda *a, **k: (_ for _ in ()).throw(OSError(f"usage {LEAK}")))
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert v["decision"] == "ESCALATE" and "OSError" in v["reasons"][0] and "unmeterable" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))
    _no_leak(_ledger_text(stack))


# -- the other upstream-failure reasons the same way -----------------------------------------------------------------


def test_a_totals_failure_names_the_class_only(stack, monkeypatch):
    from tests.test_fail_closed_pins_c168 import OK_SPEND, Http, engine, intro, use_governor
    stack.mint_token()
    engine(stack).delegation._client = Http({("POST", "/introspect"): (
        200, intro(max_spend_usd=100, issued_at="2026-01-01T00:00:00+00:00"))})
    use_governor(stack, {("GET", "/status/"): (200, OK_SPEND), ("POST", "/spend"): (201, {})})
    monkeypatch.setattr(engine(stack).governor, "totals_since",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"totals {LEAK}")))
    v = stack.sentinel.post("/check", json={"agent_id": AGENT_ID, "action": "draft invoices", "token_id": "tok",
                                            "irreversible": False}).json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert "RuntimeError" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))


def test_a_registry_outage_names_the_class_only(stack, monkeypatch):
    from field_core.clients import RegistryUnreachableError
    def boom(agent_id):
        try:
            raise OSError(f"connect {LEAK}")
        except OSError as inner:       # field-core's transport path: RegistryUnreachableError(str(exc)) from exc
            raise RegistryUnreachableError(str(inner)) from inner
    monkeypatch.setattr(_engine(stack).registry, "get_agent", boom)
    v = stack.check("draft invoices", token_id="whatever")
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.unregistered"
    assert "RegistryUnreachableError" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))


def test_a_delegation_outage_names_the_class_only(stack, monkeypatch):
    token = stack.mint_token()
    monkeypatch.setattr(_engine(stack).delegation, "introspect",
                        lambda token_id: (_ for _ in ()).throw(RuntimeError(f"deleg {LEAK}")))
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "D.token"
    assert "RuntimeError" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))


def test_a_governor_outage_in_the_budget_check_names_the_class_only(stack, monkeypatch):
    token = stack.mint_token()
    monkeypatch.setattr(_engine(stack).governor, "status",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"gov {LEAK}")))
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.spend_cap"
    assert "RuntimeError" in v["reasons"][0]
    _no_leak(" ".join(v["reasons"]))


# -- (2) the judge's model name and cited_scope ----------------------------------------------------------------------


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


class _Client:
    def __init__(self, body):
        self.body = body

    def post(self, *a, **k):
        return _Resp(self.body)


def _judged(model=..., cited=..., monkeypatch=None):
    import json
    verdict = {"conforming": True, "confidence": 0.9, "rationale": "ok"}
    if cited is not ...:
        verdict["cited_scope"] = cited
    body = {"content": [{"type": "text", "text": json.dumps(verdict)}], "usage": {"input_tokens": 1, "output_tokens": 2}}
    if model is not ...:
        body["model"] = model
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    return AnthropicJudgeClient(client=_Client(body)).judge("do a thing", ["scope one"], "agent-1")


def test_a_short_printable_model_name_is_kept(monkeypatch):
    assert _judged(model="claude-haiku-5-5", monkeypatch=monkeypatch).model == "claude-haiku-5-5"
    assert _judged(model="m" * 100, monkeypatch=monkeypatch).model == "m" * 100


@pytest.mark.parametrize("model", ["m" * 101, "x" * 10_000, "", 5, None, ["a"], {"a": 1}, True, "bad\nline", "tab\there",
                                   "esc\x1b[31m", "bidi‮", "nul\x00x"], ids=repr)
def test_any_other_model_value_falls_back_to_the_configured_model(monkeypatch, model):
    got = _judged(model=model, monkeypatch=monkeypatch)
    assert got.model == "claude-haiku-5-5" or got.model == AnthropicJudgeClient(client=_Client({})).model
    assert len(got.model) <= 100


def test_a_missing_model_keeps_the_configured_model(monkeypatch):
    assert _judged(monkeypatch=monkeypatch).model == AnthropicJudgeClient(client=_Client({})).model


@pytest.mark.parametrize("cited", ["scope one", None])
def test_cited_scope_a_string_or_none_is_kept(monkeypatch, cited):
    assert _judged(cited=cited, monkeypatch=monkeypatch).cited_scope == cited


@pytest.mark.parametrize("cited", [5, ["scope one"], {"a": 1}, True], ids=repr)
def test_a_non_string_cited_scope_is_not_a_verdict(monkeypatch, cited):
    from conformance_sentinel.judge import JudgeError
    with pytest.raises(JudgeError):
        _judged(cited=cited, monkeypatch=monkeypatch)


def test_a_10kb_model_from_the_upstream_is_not_stored_or_metered(stack, monkeypatch):
    big = "M" * 10_240
    import json
    body = {"content": [{"type": "text", "text": json.dumps({"conforming": True, "confidence": 0.95, "rationale": "ok"})}],
            "usage": {"input_tokens": 1, "output_tokens": 1}, "model": big}
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    eng = _engine(stack)
    eng.judge = AnthropicJudgeClient(client=_Client(body))
    seen = []
    real = eng.governor.report_usage
    monkeypatch.setattr(eng.governor, "report_usage", lambda agent, model, i, o: (seen.append(model), real(agent, model, i, o))[1])
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert v["decision"] == "ALLOW"
    assert seen and big not in seen and all(len(m) <= 100 for m in seen)
    assert big not in _ledger_text(stack)


# -- (3) Governor.check ---------------------------------------------------------------------------------------------


class _Boom:
    def post(self, *a, **k):
        raise httpx.ConnectError(f"connect to {LEAK} failed")


def test_an_unreachable_sentinel_blocks_with_the_class_only():
    g = Governor("agent-1", token_id="t", sentinel_url="http://sentinel.invalid", client=_Boom())
    with pytest.raises(ActionBlocked) as e:
        g.check("act")
    reason = " ".join(e.value.verdict["reasons"])
    assert "ConnectError" in reason and "failing closed" in reason
    _no_leak(reason)
    _no_leak(str(e.value))
    assert e.value.verdict["clause_id"] == "E.kill_switch" and e.value.verdict["decision"] == "BLOCK"


def test_the_registrys_own_status_text_has_no_cause_and_keeps_its_text(stack, monkeypatch):
    from field_core.clients import RegistryUnreachableError

    def status_error(agent_id):
        raise RegistryUnreachableError("registry returned 503")      # as field-core builds it: no cause
    monkeypatch.setattr(_engine(stack).registry, "get_agent", status_error)
    v = stack.check("draft invoices", token_id="whatever")
    assert "registry returned 503" in v["reasons"][0]


def test_the_services_own_status_texts_are_kept(stack, monkeypatch):
    """`governor returned 503` is built here from a name and a status code: it stays informative."""
    from conformance_sentinel.engine import UpstreamAnswerError
    _arm(stack, rules={PARAPHRASE: (True, 0.95, "ok")})
    monkeypatch.setattr(_engine(stack).governor, "status",
                        lambda agent_id, **kw: (_ for _ in ()).throw(UpstreamAnswerError("governor returned 503")))
    v = stack.check(PARAPHRASE, token_id=stack.mint_token())
    assert "governor returned 503" in v["reasons"][0]
    assert issubclass(UpstreamAnswerError, ConnectionError)
