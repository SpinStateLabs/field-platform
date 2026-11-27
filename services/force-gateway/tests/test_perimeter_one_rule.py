"""The perimeter secret is judged in two places in this service: the authn middleware and the passthrough exemption.
For one header's bytes both give the same answer: ASCII and non-ASCII secrets, an absent or empty header, and a header
far longer than any secret."""
import asyncio

import pytest
from fastapi import FastAPI

from field_core import authn
from force_gateway.api import passthrough_honoured

PLAIN = "made-up-perimeter-0123456789"
ACCENTED = "made-up-p\u00e9rim\u00e8tre-0123456789"


def middleware_accepts(raw: bytes | None) -> bool:
    app = FastAPI()
    authn.install(app)

    @app.get("/data")
    def data() -> dict:
        return {}

    # the test client re-encodes header bytes, so only a raw scope reaches the middleware with exactly these bytes
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "path": "/data",
             "raw_path": b"/data", "query_string": b"", "root_path": "", "scheme": "http",
             "headers": [] if raw is None else [(b"x-field-auth", raw)],
             "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
    seen = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            seen.append(message["status"])

    asyncio.run(app(scope, receive, send))
    assert seen[0] in (200, 401)
    return seen[0] == 200


def passthrough_accepts(raw: bytes | None) -> bool:
    # a server hands a header to the route as its bytes read as latin-1
    return passthrough_honoured("judge", None if raw is None else raw.decode("latin-1"))


CASES = [
    # (configured secret, header bytes, accepted)
    (PLAIN, PLAIN.encode(), True),
    (PLAIN, b"wrong", False),
    (PLAIN, PLAIN.encode()[:-1], False),
    (PLAIN, PLAIN.encode() + b"x", False),
    (PLAIN, PLAIN.encode() + b"\xe9", False),
    (PLAIN, b"", False),
    (PLAIN, None, False),
    (PLAIN, b"a" * 10000, False),
    (PLAIN, PLAIN.encode() * 400, False),
    (ACCENTED, ACCENTED.encode("utf-8"), True),
    (ACCENTED, ACCENTED.encode("latin-1"), False),
    (ACCENTED, PLAIN.encode(), False),
    (ACCENTED, b"", False),
    (ACCENTED, None, False),
    (ACCENTED, b"\xff\xfe", False),
]


@pytest.mark.parametrize("secret, raw, accepted", CASES,
                         ids=[f"{i}-{'accented' if s == ACCENTED else 'plain'}" for i, (s, _, _) in enumerate(CASES)])
def test_both_places_give_the_same_answer(monkeypatch, secret, raw, accepted):
    monkeypatch.setenv(authn.ENV_VAR, secret)
    assert middleware_accepts(raw) is accepted
    assert passthrough_accepts(raw) is accepted


@pytest.mark.parametrize("text", ["\u0100", "made-up \ud800"], ids=["beyond-latin-1", "lone-surrogate"])
def test_a_value_no_header_can_carry_is_refused_not_raised(monkeypatch, text):
    monkeypatch.setenv(authn.ENV_VAR, PLAIN)
    assert passthrough_honoured("judge", text) is False
