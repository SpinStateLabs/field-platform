"""S5-4: a 200 whose body is not JSON, or JSON of the wrong shape, is HeartbeatUnreachable (fail closed, ⊂ AgentKilled),
never a raw ValueError / pydantic ValidationError. The message names the exception type only, never the body."""
from __future__ import annotations

import json

import pytest

from field_agent import FieldAgent
from field_agent.errors import AgentKilled, HeartbeatUnreachable
from field_agent.liveness import LivenessClient

MARK = "SECRET-BODY-MARKER-0f3a"
OK = {"agent_id": "agent-1", "status": "active", "killed": False, "checked_at": "2026-11-04T12:00:00Z"}


class _Resp:
    def __init__(self, text):
        self.status_code, self.text = 200, text

    def json(self):
        return json.loads(self.text)


class _Client:
    def __init__(self, text):
        self._resp = _Resp(text)

    def get(self, url, **kw):
        return self._resp

    post = get


def _lc(text):
    return LivenessClient(_Client(text), base_url="http://kswitch:8005")


BAD_BODIES = [
    "not json",
    "<html>" + MARK + "</html>",
    "",
    "[]",
    "{}",
    '{"killed": "maybe"}',
    json.dumps({**OK, "killed": MARK}),
    json.dumps({**OK, "agent_id": None}),
    json.dumps({k: v for k, v in OK.items() if k != "killed"}),
    json.dumps([OK]),
    "null",
    "42",
    '"' + MARK + '"',
]


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
@pytest.mark.parametrize("body", BAD_BODIES, ids=lambda b: b[:24] or "empty")
def test_a_bad_200_is_heartbeat_unreachable_and_never_quotes_the_body(verb, body):
    with pytest.raises(HeartbeatUnreachable) as e:
        getattr(_lc(body), verb)("agent-1")
    assert isinstance(e.value, AgentKilled)
    msg = str(e.value)
    assert MARK not in msg and "liveness unknown" in msg and "halting" in msg and "unreadable" in msg
    assert e.value.__cause__ is None


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_good_200_still_parses(verb):
    hb = getattr(_lc(json.dumps(OK)), verb)("agent-1")
    assert hb.agent_id == "agent-1" and hb.killed is False


def test_an_unknown_extra_field_is_still_ignored():
    hb = _lc(json.dumps({**OK, "new_server_field": 1})).heartbeat("agent-1")
    assert hb.killed is False


@pytest.mark.parametrize("body", ["not json", "[]", "{}"])
def test_ensure_alive_halts_with_agent_killed_on_a_bad_200(body):
    agent = FieldAgent("agent-1", killswitch_client=_Client(body), killswitch_url="http://kswitch:8005")
    with pytest.raises(AgentKilled):
        agent.ensure_alive()
