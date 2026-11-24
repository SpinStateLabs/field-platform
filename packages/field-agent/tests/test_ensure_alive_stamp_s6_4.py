"""S6-4: a halt or an unknown liveness must not leave an older "alive" stamp behind.

`check()` / `cross()` skip the heartbeat while `now - _alive_at <= heartbeat_max_age`. `ensure_alive()` only set the stamp on
success, so after a caller caught `AgentKilled` from a direct `ensure_alive()` and retried inside the window, the local halt
gate was skipped. A fake clock and a scripted heartbeat; no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from field_agent import agent as agent_mod
from field_agent.agent import FieldAgent
from field_agent.errors import AgentKilled, HeartbeatUnreachable
from field_agent.liveness import Heartbeat

MAX_AGE = 60.0


class Down:
    def post(self, *a, **k):
        raise ConnectionError("down")

    get = post


def _hb(killed):
    return Heartbeat(agent_id="invoicing-agent", status="killed" if killed else "active",
                     killed=killed, checked_at="2026-01-01T00:00:00+00:00")


@pytest.fixture()
def rig(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(agent_mod.time, "monotonic", lambda: clock["now"])
    agent = FieldAgent("invoicing-agent", sentinel_client=Down(), governor_client=Down(),
                       killswitch_client=Down(), federation_client=Down(),
                       federation_url="http://t", heartbeat_max_age=MAX_AGE)
    reached = {"sentinel": 0, "federation": 0}

    def sentinel_check(*a, **k):
        reached["sentinel"] += 1
        return {"decision": "ALLOW"}

    def federation_cross(*a, **k):
        reached["federation"] += 1
        return {"decision": "ALLOW"}

    agent._sentinel = SimpleNamespace(check=sentinel_check)
    agent._federation = SimpleNamespace(cross=federation_cross)
    script = []            # each entry: a Heartbeat to return, or an exception to raise
    calls = []

    def heartbeat():
        calls.append(clock["now"])
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    agent.heartbeat = heartbeat
    return SimpleNamespace(agent=agent, clock=clock, script=script, calls=calls, reached=reached)


def _call(agent, which):
    if which == "check":
        return agent.check("draft invoices")
    return agent.cross("Borealis", "scope", "data", {"a": 1})


def _reached(rig, which):
    return rig.reached["sentinel" if which == "check" else "federation"]


@pytest.mark.parametrize("which", ["check", "cross"])
@pytest.mark.parametrize("failure", [_hb(True), HeartbeatUnreachable("liveness unknown")],
                         ids=["killed", "unreachable"])
def test_after_a_halt_or_unknown_liveness_the_next_call_forces_a_fresh_heartbeat(rig, which, failure):
    rig.script += [_hb(False), failure, failure]
    rig.agent.ensure_alive()                              # t=1000: alive, stamped
    rig.clock["now"] = 1010.0
    with pytest.raises(AgentKilled):
        rig.agent.ensure_alive()                          # t=1010: halt (or unknown)
    rig.clock["now"] = 1020.0                             # still inside heartbeat_max_age of the FIRST stamp
    with pytest.raises(AgentKilled):
        _call(rig.agent, which)
    assert rig.calls == [1000.0, 1010.0, 1020.0]          # the third heartbeat is the forced one
    assert _reached(rig, which) == 0                      # the gate halted before the sentinel / broker


@pytest.mark.parametrize("which", ["check", "cross"])
def test_a_healthy_stamp_still_skips_the_heartbeat_inside_the_window(rig, which):
    rig.script += [_hb(False)]
    rig.agent.ensure_alive()                              # t=1000
    rig.clock["now"] = 1000.0 + MAX_AGE                   # exactly at the limit: still fresh (> not >=)
    assert _call(rig.agent, which) == {"decision": "ALLOW"}
    assert rig.calls == [1000.0]
    assert _reached(rig, which) == 1


def test_the_stamp_is_cleared_on_a_halt_and_set_on_success(rig):
    rig.script += [_hb(False), _hb(True)]
    rig.agent.ensure_alive()
    assert rig.agent._alive_at == 1000.0
    rig.clock["now"] = 1010.0
    with pytest.raises(AgentKilled):
        rig.agent.ensure_alive()
    assert rig.agent._alive_at is None
