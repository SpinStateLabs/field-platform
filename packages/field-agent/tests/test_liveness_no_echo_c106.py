"""C-106 follow-up (reviewer C-704 F-C704-1): the heartbeat client never echoes what it was told.

``LivenessClient._call`` put the exception text (which can carry a URL, a proxy address or an address) and the
whole response body into ``HeartbeatUnreachable``, which an agent logs. Now: the exception TYPE name and the
status code only. The read of the reply is still unbounded here (it goes through the injected client and
``AuthedClient``); that is named in the PR text as an open item, not closed by this change."""

from __future__ import annotations

import pytest

from field_agent.errors import HeartbeatUnreachable
from field_agent.liveness import LivenessClient

MARKER = "SECRET-BODY-MARKER-0f3a"


class _Resp:
    def __init__(self, status, text="", payload=None):
        self.status_code, self.text, self._payload = status, text, payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc = resp, exc

    def get(self, url, **kw):
        if self.exc is not None:
            raise self.exc
        return self.resp

    post = get


def _client(**kw):
    return LivenessClient(_Client(**kw), base_url="http://kswitch:8005")


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_non_200_names_the_status_and_never_the_body(verb):
    lc = _client(resp=_Resp(503, text=f"upstream said {MARKER}"))
    with pytest.raises(HeartbeatUnreachable) as e:
        getattr(lc, verb)("agent-1")
    msg = str(e.value)
    assert "503" in msg and MARKER not in msg and "liveness unknown" in msg


@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_a_transport_failure_names_the_type_and_never_the_text(verb):
    lc = _client(exc=ConnectionError(f"connect to http://user:{MARKER}@proxy.invalid:3128 failed"))
    with pytest.raises(HeartbeatUnreachable) as e:
        getattr(lc, verb)("agent-1")
    msg = str(e.value)
    assert "ConnectionError" in msg and MARKER not in msg and "proxy.invalid" not in msg
    assert e.value.__cause__ is None            # the original exception (and its text) is not chained either


def test_a_good_answer_still_parses():
    ok = {"agent_id": "agent-1", "status": "alive", "killed": False, "checked_at": "2026-10-30T12:00:00Z"}
    hb = _client(resp=_Resp(200, payload=ok)).heartbeat("agent-1")
    assert hb.agent_id == "agent-1" and hb.killed is False
