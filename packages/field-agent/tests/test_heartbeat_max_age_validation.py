"""Scout S-2-4: FieldAgent(heartbeat_max_age=NaN) silently switched the liveness gate off. The gate re-checks the
kill-switch when `monotonic() - alive_at > max_age`; every comparison with NaN is False, so after the first check the
kill-switch was never asked again, with no error. The value is now validated at construction: None (gate off) or a
finite number >= 0 that is not a bool."""
from __future__ import annotations

import pytest

from field_agent import AgentKilled, FieldAgent
from tests.conftest import AGENT_ID, DownClient


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1, -0.001, True, False, "x", "30", [1], b"1"])
def test_a_bad_heartbeat_max_age_is_refused_naming_the_parameter(bad):
    with pytest.raises(ValueError, match="heartbeat_max_age"):
        FieldAgent(AGENT_ID, sentinel_client=DownClient(), governor_client=DownClient(),
                   killswitch_client=DownClient(), heartbeat_max_age=bad)


@pytest.mark.parametrize("ok", [None, 0, 0.0, 30, 30.0, 1e-9, 86400.0])
def test_none_and_a_finite_non_negative_number_are_accepted(ok):
    agent = FieldAgent(AGENT_ID, sentinel_client=DownClient(), governor_client=DownClient(),
                       killswitch_client=DownClient(), heartbeat_max_age=ok)
    assert agent is not None


def test_zero_rechecks_the_kill_switch_on_every_call_and_a_kill_halts_the_second_check(stack):
    stack.set_cap()
    token = stack.mint_token()
    agent = stack.make_agent(token_id=token, heartbeat_max_age=0.0)
    calls = []
    real = agent.heartbeat
    agent.heartbeat = lambda: (calls.append(1), real())[1]
    assert agent.check("draft invoices")["decision"] == "ALLOW"
    assert agent.check("draft invoices")["decision"] == "ALLOW"
    assert len(calls) == 2                      # 0.0: asked again on the second call, not cached
    stack.kill()
    with pytest.raises(AgentKilled):
        agent.check("draft invoices")


def test_a_long_max_age_asks_once_then_trusts_the_answer(stack):
    stack.set_cap()
    token = stack.mint_token()
    agent = stack.make_agent(token_id=token, heartbeat_max_age=3600.0)
    calls = []
    real = agent.heartbeat
    agent.heartbeat = lambda: (calls.append(1), real())[1]
    agent.check("draft invoices")
    agent.check("draft invoices")
    assert len(calls) == 1


def test_none_never_asks_the_kill_switch(stack):
    stack.set_cap()
    token = stack.mint_token()
    agent = stack.make_agent(token_id=token)
    calls = []
    agent.heartbeat = lambda: calls.append(1)
    agent.check("draft invoices")
    assert calls == []
