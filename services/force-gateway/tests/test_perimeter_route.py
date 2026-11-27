"""The two places that judge the perimeter secret, through POST /v1/messages: the same header bytes sent to the app with
the authn middleware, and to the app with the middleware taken off (so the handler's own decision shows). Includes a
request that carries the header twice: both places read the first one."""
import asyncio
import json

import pytest

from test_d2_upstream_passthrough import MSG, _passthrough_app

PLAIN = b"made-up-perimeter-0123456789"
ACCENTED = "made-up-périmètre-0123456789"
WRONG = b"wrong"


def post(app, secrets: list[bytes]) -> int:
    """One judge call with these x-field-auth headers, in order, as raw bytes (a test client re-encodes them)."""
    body = json.dumps(MSG).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"x-force-passthrough", b"judge")] + [(b"x-field-auth", s) for s in secrets]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "path": "/v1/messages",
             "raw_path": b"/v1/messages", "query_string": b"", "root_path": "", "scheme": "http", "headers": headers,
             "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
    seen = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen.append(message["status"])

    asyncio.run(app(scope, receive, send))
    return seen[0]


# (configured secret, headers in order, accepted)
CASES = {
    "plain-right": (PLAIN.decode(), [PLAIN], True),
    "plain-wrong": (PLAIN.decode(), [WRONG], False),
    "plain-absent": (PLAIN.decode(), [], False),
    "plain-empty": (PLAIN.decode(), [b""], False),
    "plain-over-long": (PLAIN.decode(), [PLAIN * 400], False),
    "accented-utf-8-bytes": (ACCENTED, [ACCENTED.encode("utf-8")], True),
    "accented-latin-1-bytes": (ACCENTED, [ACCENTED.encode("latin-1")], False),
    "twice-right-then-wrong": (PLAIN.decode(), [PLAIN, WRONG], True),
    "twice-wrong-then-right": (PLAIN.decode(), [WRONG, PLAIN], False),
    "twice-empty-then-right": (PLAIN.decode(), [b"", PLAIN], False),
}


@pytest.mark.parametrize("secret, headers, accepted", CASES.values(), ids=CASES)
def test_with_the_middleware(monkeypatch, secret, headers, accepted):
    monkeypatch.setenv("FIELD_SHARED_SECRET", secret)
    app, spy, *_ = _passthrough_app()
    assert post(app, headers) == (200 if accepted else 401)
    assert spy.bodies == ([MSG] if accepted else [])
    assert app.state.coverage["passthrough"] == (1 if accepted else 0)


@pytest.mark.parametrize("secret, headers, accepted", CASES.values(), ids=CASES)
def test_the_handler_alone_decides_the_same(monkeypatch, secret, headers, accepted):
    monkeypatch.setenv("FIELD_SHARED_SECRET", secret)
    app, spy, *_ = _passthrough_app()
    app.user_middleware.clear()
    assert post(app, headers) == 200
    # accepted: forwarded untouched; not accepted: the header is ignored and the call is instrumented
    assert (spy.bodies[0] == MSG) is accepted
    assert app.state.coverage["passthrough"] == (1 if accepted else 0)
    assert app.state.coverage["instrumented"] == (0 if accepted else 1)
