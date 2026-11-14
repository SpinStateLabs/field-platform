"""S9-3: LivenessClient builds the heartbeat URL with the agent id as ONE encoded path segment.

`f"{base}/heartbeat/{agent_id}"` let an id such as 'x/../../kill/victim' be normalised by httpx (dot segments removed) into
POST /kill/victim for `checkin()`, and AuthedClient attaches auth_headers(), which carries the service's operator pair, to every
request. '?' and '#' changed the route too, and an empty id called GET /heartbeat/. Now the id is `quote(safe='')`; an id that is
empty, not a string, or only dots ('.' and '..' are not changed by quoting and are removed by the URL normaliser) is refused
BEFORE any request as `HeartbeatUnreachable` (fail closed: liveness unknown, halt). A real httpx client over a recording
transport is used, so the path asserted is the one httpx really sends."""

import httpx
import pytest

from field_agent.errors import HeartbeatUnreachable
from field_agent.liveness import LivenessClient

BODY = {"agent_id": "x", "killed": False, "status": "active", "checked_at": "2026-11-07T00:00:00+00:00"}


def client_with_log():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode("ascii")))
        return httpx.Response(200, json=BODY)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return LivenessClient(client=http, base_url="http://kill.invalid"), seen


IDS = [("a/b", "a%2Fb"), ("../kill/x", "..%2Fkill%2Fx"), ("x/../../kill/victim", "x%2F..%2F..%2Fkill%2Fvictim"),
       ("a?b", "a%3Fb"), ("a#b", "a%23b"), ("a b", "a%20b"), ("é", "%C3%A9"), ("a%2Fb", "a%252Fb"), ("plain-id_1.x", "plain-id_1.x")]


@pytest.mark.parametrize("raw, encoded", IDS, ids=[i for i, _ in IDS])
def test_heartbeat_is_one_get_to_the_encoded_segment(raw, encoded):
    client, seen = client_with_log()
    client.heartbeat(raw)
    assert seen == [("GET", f"/heartbeat/{encoded}")]


@pytest.mark.parametrize("raw, encoded", IDS, ids=[i for i, _ in IDS])
def test_checkin_is_one_post_to_the_encoded_segment_never_another_route(raw, encoded):
    client, seen = client_with_log()
    client.checkin(raw)
    assert seen == [("POST", f"/heartbeat/{encoded}")]
    assert seen[0][1].count("/") == 2                      # /heartbeat/<one segment>, never a second route


@pytest.mark.parametrize("bad", ["", ".", "..", None, 5, b"x", ["x"]], ids=["empty", "dot", "dotdot", "none", "int", "bytes", "list"])
@pytest.mark.parametrize("verb", ["heartbeat", "checkin"])
def test_an_unusable_id_is_refused_before_any_request_as_heartbeat_unreachable(verb, bad):
    client, seen = client_with_log()
    with pytest.raises(HeartbeatUnreachable, match="liveness unknown, halting"):
        getattr(client, verb)(bad)
    assert seen == []


def test_the_operator_pair_never_travels_to_another_route(monkeypatch):
    monkeypatch.setenv("FIELD_OPERATOR", "svc")
    monkeypatch.setenv("FIELD_OPERATOR_KEY", "fok_SYNTHETIC-0123456789abcdef")
    paths = []

    def handler(request):
        paths.append((request.url.raw_path.decode(), "x-field-operator" in {k.lower() for k in request.headers}))
        return httpx.Response(200, json=BODY)

    client = LivenessClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://kill.invalid")
    client.checkin("x/../../kill/victim")
    assert paths and all(p.startswith("/heartbeat/") for p, _ in paths)


def test_a_normal_id_and_the_response_are_unchanged():
    client, seen = client_with_log()
    hb = client.heartbeat("invoicing-agent")
    assert hb.killed is False and seen == [("GET", "/heartbeat/invoicing-agent")]
