"""S10-2: ``Heartbeat.killed`` is a real JSON boolean. Lax parsing read "false", "no", "0", "off" and the integer 0 as
False (alive), while ``FieldClient`` halts on the same body; a mangled 200 answer is now ``HeartbeatUnreachable`` (liveness
unknown, halting) with the exception class only, never the body. A real False is still a live Heartbeat and a real True a
killed one (``heartbeat()`` never raises on killed=true). Fakes only."""
from __future__ import annotations

import pytest

from field_agent import AgentKilled, FieldAgent, HeartbeatUnreachable
from field_agent.liveness import Heartbeat, LivenessClient
from tests.conftest import DownClient

MARK = "MARKER-9e33"
GOOD = {"agent_id": "a1", "status": "active", "checked_at": "2026-11-07T00:00:00Z"}


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        if self._body is ValueError:
            raise ValueError(f"Expecting value {MARK}")
        return self._body


class Fake:
    def __init__(self, resp):
        self.resp = resp

    def get(self, *a, **k):
        return self.resp

    post = get


def liveness(resp) -> LivenessClient:
    return LivenessClient(client=Fake(resp), base_url="http://t")


@pytest.mark.parametrize("killed", ["false", "no", "0", 0, "off", "n", "f", "False", "true", 1, None, "", [], {}],
                         ids=repr)
def test_a_killed_value_that_is_not_a_real_bool_halts_with_no_body_text(killed):
    body = {**GOOD, "killed": killed, "note": MARK}
    with pytest.raises(HeartbeatUnreachable) as exc:
        liveness(Resp(body=body)).heartbeat("a1")
    assert "ValidationError" in str(exc.value) and "liveness unknown, halting" in str(exc.value)
    assert MARK not in str(exc.value) and repr(killed) not in str(exc.value)
    assert isinstance(exc.value, AgentKilled)


def test_the_original_error_is_not_chained_so_a_traceback_cannot_show_the_body():
    with pytest.raises(HeartbeatUnreachable) as exc:
        liveness(Resp(body={**GOOD, "killed": MARK})).heartbeat("a1")
    assert exc.value.__cause__ is None and exc.value.__suppress_context__ is True
    with pytest.raises(HeartbeatUnreachable) as exc:
        liveness(Resp(body=ValueError)).heartbeat("a1")
    assert exc.value.__cause__ is None and exc.value.__suppress_context__ is True


def test_a_missing_killed_halts():
    with pytest.raises(HeartbeatUnreachable):
        liveness(Resp(body=dict(GOOD))).heartbeat("a1")


@pytest.mark.parametrize("body", [[1, 2], "alive", 5, None, {}], ids=repr)
def test_a_200_whose_body_is_not_an_object_with_the_fields_halts(body):
    with pytest.raises(HeartbeatUnreachable) as exc:
        liveness(Resp(body=body)).heartbeat("a1")
    assert "unusable" in str(exc.value)


def test_a_200_that_is_not_json_halts_with_the_class_only():
    with pytest.raises(HeartbeatUnreachable) as exc:
        liveness(Resp(body=ValueError, text=f"<html>{MARK}</html>")).heartbeat("a1")
    assert "(ValueError)" in str(exc.value) and MARK not in str(exc.value)


def test_a_real_false_is_a_live_heartbeat_and_a_real_true_is_a_killed_one():
    alive = liveness(Resp(body={**GOOD, "killed": False})).heartbeat("a1")
    dead = liveness(Resp(body={**GOOD, "status": "killed", "killed": True})).heartbeat("a1")
    assert isinstance(alive, Heartbeat) and alive.killed is False
    assert isinstance(dead, Heartbeat) and dead.killed is True       # heartbeat() never raises on killed=true


def test_checkin_reads_the_same_strict_way():
    with pytest.raises(HeartbeatUnreachable):
        liveness(Resp(body={**GOOD, "killed": "false"})).checkin("a1")


def test_ensure_alive_halts_on_a_mangled_killed_and_passes_on_a_real_false():
    def agent(body):
        return FieldAgent("a1", sentinel_client=DownClient(), governor_client=DownClient(),
                          killswitch_client=Fake(Resp(body=body)), sentinel_url="http://t", governor_url="http://t",
                          killswitch_url="http://t")

    with pytest.raises(AgentKilled):
        agent({**GOOD, "killed": "false"}).ensure_alive()
    assert agent({**GOOD, "killed": False}).ensure_alive().killed is False
    with pytest.raises(AgentKilled):
        agent({**GOOD, "status": "killed", "killed": True}).ensure_alive()


def test_the_non_200_and_transport_paths_are_unchanged():
    with pytest.raises(HeartbeatUnreachable, match="returned 503"):
        liveness(Resp(status=503, body={})).heartbeat("a1")
    with pytest.raises(HeartbeatUnreachable, match="unreachable"):
        LivenessClient(client=DownClient(), base_url="http://t").heartbeat("a1")
