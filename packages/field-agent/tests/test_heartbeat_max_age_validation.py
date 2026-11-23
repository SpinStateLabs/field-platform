"""S10-1: ``heartbeat_max_age`` is validated at construction (None, or a finite number >= 0 that is not a bool), and the
liveness gate of ``check`` and ``cross`` is one method. A NaN or infinite limit made ``now - alive_at > limit`` always
False, so after the first poll the kill-switch was skipped for the life of the process; a string failed on the second
call. Fakes only: no service runs."""
from __future__ import annotations

import pytest

import field_agent.agent as agent_module
from field_agent import AgentKilled, FieldAgent
from tests.conftest import DownClient

MARK = "MARKER-4c19"


class FakeKillSwitch:
    """Answers GET /heartbeat/<id> and counts the polls."""

    def __init__(self, killed=False):
        self.killed, self.polls = killed, 0

    def get(self, url, **kw):
        self.polls += 1
        outer = self

        class Resp:
            status_code = 200

            def json(self):
                return {"agent_id": "a1", "status": "killed" if outer.killed else "active",
                        "killed": outer.killed, "checked_at": "2026-11-07T00:00:00Z"}

        return Resp()


def make(max_age, ks=None):
    ks = ks or FakeKillSwitch()
    agent = FieldAgent("a1", sentinel_client=DownClient(), governor_client=DownClient(), killswitch_client=ks,
                       federation_client=DownClient(), sentinel_url="http://t", governor_url="http://t",
                       killswitch_url="http://t", federation_url="http://t", heartbeat_max_age=max_age)
    agent._sentinel.check = lambda *a, **k: {"decision": "ALLOW"}       # the gate is what is under test
    agent._federation.cross = lambda *a, **k: {"decision": "ALLOW"}
    return agent, ks


def call(agent, verb):
    if verb == "check":
        return agent.check("draft invoices")
    return agent.cross("org", "scope", "class", {"m": 1})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, False, "30", [], -1, -0.5, {}, b"3",
                                 object()], ids=repr)
def test_an_invalid_limit_is_refused_at_construction_without_echoing_it(bad):
    with pytest.raises(ValueError) as exc:
        make(bad)
    assert "heartbeat_max_age" in str(exc.value)
    assert repr(bad) not in str(exc.value)


def test_a_string_with_a_marker_is_not_echoed():
    with pytest.raises(ValueError) as exc:
        make(MARK)
    assert MARK not in str(exc.value)


@pytest.mark.parametrize("good", [0, 0.0, 30, 30.0, 0.001, 10**400, None], ids=repr)
def test_a_valid_limit_is_accepted(good):
    agent, _ = make(good)
    assert agent._heartbeat_max_age == good


@pytest.mark.parametrize("verb", ["check", "cross"])
def test_no_limit_means_no_poll(verb):
    agent, ks = make(None)
    call(agent, verb)
    call(agent, verb)
    assert ks.polls == 0


@pytest.mark.parametrize("verb", ["check", "cross"])
def test_the_first_call_polls_and_a_fresh_stamp_is_not_repolled(verb, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: now[0])
    agent, ks = make(30.0)
    call(agent, verb)
    assert ks.polls == 1
    now[0] += 29.0
    call(agent, verb)
    assert ks.polls == 1


@pytest.mark.parametrize("verb", ["check", "cross"])
def test_a_stale_stamp_is_repolled_after_31_seconds(verb, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: now[0])
    agent, ks = make(30.0)
    call(agent, verb)
    now[0] += 31.0
    call(agent, verb)
    assert ks.polls == 2


@pytest.mark.parametrize("verb", ["check", "cross"])
def test_a_kill_after_the_first_poll_halts_the_next_stale_call(verb, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(agent_module.time, "monotonic", lambda: now[0])
    agent, ks = make(30.0)
    call(agent, verb)
    ks.killed = True
    now[0] += 31.0
    with pytest.raises(AgentKilled):
        call(agent, verb)


def test_check_and_cross_share_one_gate_method():
    import inspect

    assert "_gate_liveness" in inspect.getsource(FieldAgent.check)
    assert "_gate_liveness" in inspect.getsource(FieldAgent.cross)
    assert "monotonic" not in inspect.getsource(FieldAgent.check) + inspect.getsource(FieldAgent.cross)
