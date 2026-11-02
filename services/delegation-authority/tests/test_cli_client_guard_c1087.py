"""C-1087 (reviewer Q-42, 20261101-0715-reviewer-q37-q42.md F-Q42-1, F-Q42-2): the delegation CLI client keeps its own
copy of the operator-pair guard, so what the guard does is pinned here, on the client the verbs really build.

Every request carries the perimeter header; the operator pair rides only a guarded (method, path) on the base URL's own
origin and never a read, an unlisted path, a path that merely starts like a guarded one, or another origin. Values are
made up; nothing leaves the process (a MockTransport answers).
"""
from __future__ import annotations

import httpx
import pytest

from delegation_authority import cli

PAIR = ("svc-made-up", "made-up-key")
SECRET = "made-up-perimeter-secret"
BASE = "http://da.invalid"


@pytest.fixture
def sent(monkeypatch):
    """Requests the CLI client sends, as the transport saw them."""
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


def test_a_guarded_post_to_another_origin_carries_no_operator_pair(sent):
    """F-Q42-1: another host, another port and another scheme each get nothing, whatever the path; the same origin
    gets the pair (so the test cannot pass by the pair never being sent)."""
    client = cli._client(PAIR)
    assert client.post(BASE + "/tokens").status_code == 200
    assert _pair_of(sent[-1]) == PAIR
    for other in ("http://elsewhere.invalid/tokens", BASE + ":9999/tokens", "https://da.invalid/tokens"):
        assert client.post(other).status_code == 200
        assert _pair_of(sent[-1]) == (None, None), other

