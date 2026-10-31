"""C-642b: the SDK transport bounds the reply bytes it reads; the refusal text is fixed and carries no body."""
from __future__ import annotations

import httpx
import pytest

from field_agent import _transport as t
from field_agent.errors import HeartbeatUnreachable, UsageReportError
from field_agent.liveness import LivenessClient
from field_agent.usage import UsageClient

MARK = "CANARY-4c19-wk"
CAP = t.MAX_RESPONSE_BYTES


class Streaming:
    """Real httpx client over a mock transport: exercises the streaming path."""

    def __init__(self, body: bytes, headers=None, status=200):
        def handler(request):
            return httpx.Response(status, content=body, headers=headers or {})
        self.inner = httpx.Client(transport=httpx.MockTransport(handler))

    def __getattr__(self, name):
        return getattr(self.inner, name)


class NoStream:
    def __init__(self, body: bytes):
        self.body = body

    def get(self, url, **kw):
        return httpx.Response(200, content=self.body, request=httpx.Request("GET", url))

    post = get


def body(n: int) -> bytes:
    return (MARK.encode() + b"x" * n)[:n]


def chain(exc):
    seen, todo = [], [exc]
    while todo:
        e = todo.pop()
        if e is None or any(e is x for x in seen):
            continue
        seen.append(e)
        todo += [e.__cause__, e.__context__]
    return seen


def test_exactly_cap_accepted_and_cap_plus_one_refused():
    ok = t.AuthedClient(Streaming(body(CAP))).get("http://u/x")
    assert len(ok.content) == CAP
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Streaming(body(CAP + 1))).get("http://u/x")


def test_normal_body_and_status_unchanged():
    r = t.AuthedClient(Streaming(b'{"a": 1}', status=201, headers={"x-k": "v"})).post("http://u/x", json={})
    assert (r.status_code, r.json(), r.headers["x-k"]) == (201, {"a": 1}, "v")


def test_lying_content_length_does_not_bypass():
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Streaming(body(CAP + 10), headers={"content-length": "5"})).get("http://u/x")


def test_compressed_bomb_counted_decoded():
    import gzip
    bomb = gzip.compress(b"\0" * (CAP + 1))
    assert len(bomb) < CAP
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Streaming(bomb, headers={"content-encoding": "gzip"})).get("http://u/x")


def test_no_stream_fallback_checks_size():
    assert t.AuthedClient(NoStream(body(CAP))).get("http://u/x").status_code == 200
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(NoStream(body(CAP + 1))).get("http://u/x")


def test_refusal_carries_no_body_bytes():
    with pytest.raises(t.ResponseTooLarge) as ei:
        t.AuthedClient(Streaming(body(CAP + 1))).get("http://u/x")
    text = "".join(repr(e) + str(e) for e in chain(ei.value))
    assert str(CAP) in text
    assert MARK not in text and "CANARY" not in text


def test_heartbeat_wraps_refusal_without_body():
    c = LivenessClient(client=Streaming(body(CAP + 1)), base_url="http://u")
    with pytest.raises(HeartbeatUnreachable) as ei:
        c.heartbeat("a1")
    assert MARK not in "".join(str(e) for e in chain(ei.value))


def test_usage_wraps_refusal_without_body():
    c = UsageClient(client=Streaming(body(CAP + 1)), base_url="http://u")
    with pytest.raises(UsageReportError) as ei:
        c.report("a1", "m", 1, 1)
    assert MARK not in "".join(str(e) for e in chain(ei.value))
