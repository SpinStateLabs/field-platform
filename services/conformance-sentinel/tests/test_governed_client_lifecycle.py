"""S3-10: the @governed wrapper built a new Governor, and so a new httpx.Client (a connection pool, never closed), on
EVERY call. One Governor per decorated function is built lazily on the first call; `token_id` stays late-bound per
call (passed to check(), not frozen in the constructor); Governor gains close() and context-manager support."""

from __future__ import annotations

import httpx
import pytest

import conformance_sentinel.governed as g
from conformance_sentinel.governed import ActionBlocked, ActionEscalated, Governor, governed


class Spy:
    """Stands in for httpx.Client: records constructions, bodies and close()."""

    constructed = 0
    bodies: list = []
    closed = 0
    reply = {"decision": "ALLOW", "clause_id": "OK", "reasons": []}
    error: Exception | None = None

    def __init__(self, *a, **kw):
        type(self).constructed += 1

    def post(self, url, json=None, **kw):
        if type(self).error:
            raise type(self).error
        type(self).bodies.append(json)
        reply = type(self).reply
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))

    def close(self):
        type(self).closed += 1


@pytest.fixture()
def spy(monkeypatch):
    Spy.constructed, Spy.bodies, Spy.closed = 0, [], 0
    Spy.reply = {"decision": "ALLOW", "clause_id": "OK", "reasons": []}
    Spy.error = None
    monkeypatch.setattr(g.httpx, "Client", Spy)
    return Spy


def test_fifty_calls_of_one_decorated_function_build_one_client(spy):
    @governed(agent_id="a", action="act", token_id="t")
    def fn():
        return 1

    assert [fn() for _ in range(50)] == [1] * 50
    assert spy.constructed == 1
    assert len(spy.bodies) == 50


def test_a_decorated_function_that_is_never_called_builds_no_client(spy):
    @governed(agent_id="a", action="act")
    def fn():
        return 1

    assert spy.constructed == 0


def test_a_rotating_callable_token_id_is_read_on_every_call(spy):
    tokens = iter(["t1", "t2", "t3"])

    @governed(agent_id="a", action="act", token_id=lambda: next(tokens))
    def fn():
        return 1

    for _ in range(3):
        fn()
    assert [b["token_id"] for b in spy.bodies] == ["t1", "t2", "t3"]
    assert spy.constructed == 1


def test_a_plain_token_id_and_none_are_sent_as_before(spy):
    @governed(agent_id="a", action="act", token_id="fixed")
    def f1():
        pass

    @governed(agent_id="a", action="act")
    def f2():
        pass

    f1()
    f2()
    assert [b["token_id"] for b in spy.bodies] == ["fixed", None]


def test_block_still_raises_and_the_function_does_not_run(spy):
    spy.reply = {"decision": "BLOCK", "clause_id": "D.scope", "reasons": ["no"]}
    ran = []

    @governed(agent_id="a", action="act")
    def fn():
        ran.append(1)

    for _ in range(2):
        with pytest.raises(ActionBlocked):
            fn()
    assert ran == [] and spy.constructed == 1


def test_escalate_still_raises(spy):
    spy.reply = {"decision": "ESCALATE", "clause_id": "E.x", "reasons": ["ask"]}

    @governed(agent_id="a", action="act")
    def fn():
        pass

    with pytest.raises(ActionEscalated):
        fn()


def test_an_unreachable_sentinel_still_fails_closed_on_every_call(spy):
    spy.error = httpx.ConnectError("down")

    @governed(agent_id="a", action="act")
    def fn():
        raise AssertionError("must not run")

    for _ in range(2):
        with pytest.raises(ActionBlocked) as e:
            fn()
        assert e.value.verdict["clause_id"] == "E.kill_switch"


def test_close_closes_the_client_and_the_context_manager_does_too(spy):
    gov = Governor(agent_id="a")
    gov.close()
    assert spy.closed == 1
    with Governor(agent_id="a") as inner:
        assert inner.check("act")["decision"] == "ALLOW"
    assert spy.closed == 2
