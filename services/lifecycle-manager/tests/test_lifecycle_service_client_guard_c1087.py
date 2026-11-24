"""C-1087 (reviewer Q-42, 20261101-0715-reviewer-q37-q42.md F-Q42-3; closes Q-21 F-Q21-2): what the lifecycle CLI's
``_service_client`` puts on a request is pinned on the client the verbs really build.

Two controls survived the whole suite: L2 (``headers=_perimeter()`` dropped) and L4 (the pair dropped from the guard).
Values are made up; nothing leaves the process (a MockTransport answers).
"""
from __future__ import annotations

import httpx
import pytest

from lifecycle_manager import cli as lcli

PAIR = ("svc-made-up", "made-up-key")
SECRET = "made-up-perimeter-secret"
BASE = "http://da.invalid"


@pytest.fixture
def sent(monkeypatch):
    """Requests the client sends, as the transport saw them."""
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={})

    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: real(*a, transport=httpx.MockTransport(handler), **k))
    monkeypatch.setenv("FIELD_DELEGATION_URL", BASE)
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    return seen


def _pair_of(req: httpx.Request):
    return req.headers.get("x-field-operator"), req.headers.get("x-field-operator-key")


def test_the_service_client_sends_the_perimeter_header_on_a_read_and_no_pair(sent):
    """F-Q42-3 L2: ``headers=_perimeter()`` dropped means a read leaves without x-field-auth."""
    _, client = lcli._service_client("delegation", PAIR)
    assert client.get("/tokens/t-1").status_code == 200
    assert sent[-1].headers.get("x-field-auth") == SECRET
    assert _pair_of(sent[-1]) == (None, None)


def test_the_service_client_sends_the_pair_on_a_guarded_post_and_not_on_an_unlisted_one(sent):
    """F-Q42-3 L4: the pair dropped from the guard means a guarded write loses its identity. POST /tokens carries it;
    POST /introspect, not a guarded route, does not."""
    _, client = lcli._service_client("delegation", PAIR)
    client.post("/tokens")
    assert _pair_of(sent[-1]) == PAIR
    assert sent[-1].headers.get("x-field-auth") == SECRET
    client.post("/introspect")
    assert _pair_of(sent[-1]) == (None, None)
