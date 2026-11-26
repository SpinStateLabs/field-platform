"""`Governor.check` and `@governed` must fail CLOSED on a verdict that is not exactly
ALLOW, BLOCK or ESCALATE (scout S-C1). Before: only the exact strings "BLOCK" and
"ESCALATE" raised; any other value ("block", "DENY", "ALLOW " ...) was returned as if
it were an allow and the wrapper RAN the governed function. A missing key or a non-object
body leaked KeyError/TypeError instead of a block."""
from __future__ import annotations

import pytest

from conformance_sentinel.governed import (
    ActionBlocked,
    ActionEscalated,
    Governor,
    governed,
)


class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self):
        return self._b


class _Client:
    def __init__(self, body):
        self.body, self.posts = body, 0

    def post(self, url, json=None, **kw):
        self.posts += 1
        return _Resp(self.body)


def _gov(body):
    return Governor("agent-1", token_id="t", sentinel_url="http://sentinel.invalid", client=_Client(body))


UNKNOWN = [
    {"decision": "block"}, {"decision": "Block"}, {"decision": "DENY"}, {"decision": "allow"},
    {"decision": "ALLOW "}, {"decision": " ALLOW"}, {"decision": ""}, {"decision": None},
    {"decision": 1}, {"decision": ["ALLOW"]}, {"decision": True}, {}, {"verdict": "ALLOW"},
    None, [], [1], "ALLOW", 5, True,
]


@pytest.mark.parametrize("body", UNKNOWN)
def test_check_blocks_on_an_unknown_decision(body):
    with pytest.raises(ActionBlocked) as exc:
        _gov(body).check("some action")
    v = exc.value.verdict
    assert v["decision"] == "BLOCK" and v["clause_id"] == "E.kill_switch"


@pytest.mark.parametrize("body", UNKNOWN)
def test_the_decorator_never_runs_the_function_on_an_unknown_decision(monkeypatch, body):
    ran = []
    monkeypatch.setattr("conformance_sentinel.governed.httpx.Client",
                        lambda **kw: _Client(body))

    @governed("agent-1", "some action", sentinel_url="http://sentinel.invalid")
    def act():
        ran.append(1)

    with pytest.raises(ActionBlocked):
        act()
    assert ran == []


def test_the_block_reason_is_fixed_text_and_does_not_echo_the_body():
    marker = "zz-marker-do-not-echo"
    with pytest.raises(ActionBlocked) as exc:
        _gov({"decision": marker}).check("a")
    assert marker not in str(exc.value) and marker not in repr(exc.value.verdict)


def test_allow_still_returns_the_verdict_and_runs_the_function(monkeypatch):
    body = {"decision": "ALLOW", "clause_id": None, "reasons": ["ok"]}
    assert _gov(body).check("a") == body
    ran = []
    monkeypatch.setattr("conformance_sentinel.governed.httpx.Client", lambda **kw: _Client(body))

    @governed("agent-1", "a", sentinel_url="http://sentinel.invalid")
    def act():
        ran.append(1)
        return "done"

    assert act() == "done" and ran == [1]


def test_block_and_escalate_still_raise_their_own_exceptions():
    with pytest.raises(ActionBlocked):
        _gov({"decision": "BLOCK", "clause_id": "E.x", "reasons": ["no"]}).check("a")
    with pytest.raises(ActionEscalated):
        _gov({"decision": "ESCALATE", "clause_id": "E.y", "reasons": ["ask"]}).check("a")
