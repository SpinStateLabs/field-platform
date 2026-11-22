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


def test_the_cap_is_one_mebibyte():
    # reviewer-7 on fdc2ec8 (mutant T1): the tests import the constant, so its value was unpinned
    assert t.MAX_RESPONSE_BYTES == 1_048_576


@pytest.mark.parametrize("verb", ["get", "post", "patch"])
def test_every_verb_enforces_the_cap_directly(verb):
    # reviewer-7 on fdc2ec8 (mutants T16, T17): only GET was pinned; the wrapper tests swallow a parse failure
    call = getattr(t.AuthedClient(Streaming(body(CAP))), verb)
    assert len(call("http://u/x").content) == CAP
    big = getattr(t.AuthedClient(Streaming(body(CAP + 1))), verb)
    with pytest.raises(t.ResponseTooLarge):
        big("http://u/x")


def test_normal_body_and_status_unchanged():
    r = t.AuthedClient(Streaming(b'{"a": 1}', status=201, headers={"x-k": "v"})).post("http://u/x", json={})
    assert (r.status_code, r.json(), r.headers["x-k"]) == (201, {"a": 1}, "v")


def test_lying_content_length_does_not_bypass():
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Streaming(body(CAP + 10), headers={"content-length": "5"})).get("http://u/x")


def test_compressed_bomb_is_refused_never_decoded():
    """R2/roley C1: iter_bytes() decodes each raw read in full before it can be counted, so a gzip reply could expand
    far past the cap in memory. A compressed reply is now refused before any body byte is read."""
    import gzip
    bomb = gzip.compress(b"\0" * (CAP + 1))
    assert len(bomb) < CAP
    with pytest.raises(t.UnexpectedContentEncoding):
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


class Chunked:
    """Real httpx client over a mock transport whose body arrives in several chunks, each below the cap."""

    def __init__(self, sizes, pulled=None):
        def gen():
            for i, n in enumerate(sizes):
                if pulled is not None:
                    pulled.append(i)
                yield b"x" * n

        def handler(request):
            return httpx.Response(200, content=gen())
        self.inner = httpx.Client(transport=httpx.MockTransport(handler))

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_chunks_each_below_the_cap_but_over_it_in_total_are_refused():
    # a running total reset per chunk would pass this: real httpx streams in chunks well under the cap
    sizes = [CAP // 4] * 4 + [1]
    assert max(sizes) < CAP and sum(sizes) == CAP + 1
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Chunked(sizes)).get("http://u/x")


def test_chunks_totalling_exactly_the_cap_are_accepted():
    r = t.AuthedClient(Chunked([CAP // 4] * 4)).get("http://u/x")
    assert len(r.content) == CAP


def test_the_stream_is_not_read_past_the_cap():
    pulled: list[int] = []
    sizes = [CAP // 2, CAP // 2, 1] + [1024] * 50
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(Chunked(sizes, pulled)).get("http://u/x")
    assert max(pulled) <= 3                    # refused at the chunk that crosses the cap, the other 49 never pulled


# --- C1 (R2 / roley): the cap bounds memory for compressed replies too ------------------------------------------------

class Recorded:
    """Real httpx client over a mock transport that records what was asked and what was handed out."""

    def __init__(self, chunks, headers=None):
        self.requests, self.pulled = [], []

        def gen():
            for i, c in enumerate(chunks):
                self.pulled.append(i)
                yield c

        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, content=gen(), headers=headers or {})
        self.inner = httpx.Client(transport=httpx.MockTransport(handler))

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _gzip_bomb(decoded: int) -> bytes:
    import gzip
    return gzip.compress(b"\0" * decoded, compresslevel=9)


@pytest.mark.parametrize("encoding", ["gzip", "GZIP", "deflate", "br", "zstd", "gzip, identity", " x-unknown "])
def test_a_gzip_bomb_or_any_other_encoding_is_refused_before_a_byte_is_read(encoding):
    bomb = _gzip_bomb(16 * CAP)                 # 16 MiB of zeros in about 16 KiB: decoded it would be 16x the cap
    assert len(bomb) < CAP // 8
    rec = Recorded([bomb[i:i + 4096] for i in range(0, len(bomb), 4096)], headers={"content-encoding": encoding})
    with pytest.raises(t.UnexpectedContentEncoding) as ei:
        t.AuthedClient(rec).get("http://u/x")
    assert rec.pulled == []                    # not one chunk was pulled, so nothing was decoded
    assert isinstance(ei.value, t.ResponseTooLarge)       # every caller that handles the cap handles this
    assert "Content-Encoding" in str(ei.value) and len(str(ei.value)) < 120


@pytest.mark.parametrize("encoding", [None, "identity", "IDENTITY", " identity "])
def test_an_identity_reply_is_read(encoding):
    rec = Recorded([b"ok"], headers={"content-encoding": encoding} if encoding else None)
    r = t.AuthedClient(rec).get("http://u/x")
    assert r.content == b"ok" and "content-encoding" not in r.headers


@pytest.mark.parametrize("verb", ["get", "post", "patch"])
def test_every_request_asks_for_identity_even_when_the_caller_asked_for_gzip(verb):
    rec = Recorded([b"ok"])
    getattr(t.AuthedClient(rec), verb)("http://u/x", headers={"ACCEPT-ENCODING": "gzip"})
    (req,) = rec.requests
    assert req.headers.get_list("accept-encoding") == ["identity"]


def test_the_cap_counts_raw_bytes_on_the_wire():
    """One byte over the cap is refused, and the chunk after the crossing one is never pulled."""
    rec = Recorded([b"x" * (CAP // 2), b"x" * (CAP // 2), b"x", b"x" * 1024])
    with pytest.raises(t.ResponseTooLarge):
        t.AuthedClient(rec).get("http://u/x")
    assert rec.pulled == [0, 1, 2]


def test_a_compressed_body_sent_without_a_content_encoding_header_is_kept_raw_not_decoded():
    """A peer that compresses but does not say so: nothing decodes it, so memory stays bounded by the raw count."""
    bomb = _gzip_bomb(8 * CAP)
    r = t.AuthedClient(Recorded([bomb])).get("http://u/x")
    assert r.content == bomb                   # the bytes as sent, never expanded
