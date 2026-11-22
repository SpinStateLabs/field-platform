"""SpendStatusClient builds governor URLs from the agent id. The id is now one encoded
path segment (scout S-C2): `a/../../caps/victim` used to reach the governor as
`/caps/victim` and `a?x=1` as `/status/a` plus a query, because httpx normalises dot
segments and splits on `?`/`#`."""
from __future__ import annotations

import httpx
import pytest

from conformance_sentinel.engine import SpendStatusClient

TRICKY = ["a/../../caps/victim", "a?x=1", "a#frag", "..", ".", "a%2Fb", "a b", "a;b", "ünï"]


class _Resp:
    status_code = 200

    def json(self):
        return {"ok": True}


class _Client:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def get(self, url, params=None, **kw):
        # build the request exactly as httpx would, so the path/query split is real
        self.requests.append(httpx.Client().build_request("GET", url, params=params))
        return _Resp()


def _client():
    fake = _Client()
    return SpendStatusClient(client=fake, base_url="http://governor.invalid"), fake


@pytest.mark.parametrize("agent_id", TRICKY)
def test_status_reaches_the_governor_as_one_status_segment(agent_id):
    c, fake = _client()
    c.status(agent_id)
    req = fake.requests[0]
    raw = req.url.raw_path
    assert raw.startswith(b"/status/") and raw.count(b"/") == 2     # raw: %2F stays inside the segment
    assert not req.url.query and not req.url.fragment


@pytest.mark.parametrize("agent_id", TRICKY)
def test_totals_reaches_the_governor_as_one_totals_segment(agent_id):
    c, fake = _client()
    c.totals_since(agent_id, "2026-01-01T00:00:00+00:00")
    req = fake.requests[0]
    path = req.url.raw_path.split(b"?")[0]
    assert path.startswith(b"/totals/") and path.count(b"/") == 2
    assert dict(req.url.params) == {"since": "2026-01-01T00:00:00+00:00"}


def test_status_with_an_action_keeps_only_its_own_query():
    c, fake = _client()
    c.status("a?x=1", action="deploy")
    req = fake.requests[0]
    assert req.url.raw_path.split(b"?")[0].count(b"/") == 2 and dict(req.url.params) == {"action": "deploy"}


@pytest.mark.parametrize("agent_id", ["invoicing-agent", "a.b_c-1", "x"])
def test_an_ordinary_slug_is_unchanged(agent_id):
    c, fake = _client()
    c.status(agent_id)
    c.totals_since(agent_id, "t")
    assert fake.requests[0].url.path == f"/status/{agent_id}"
    assert fake.requests[1].url.path == f"/totals/{agent_id}"


def test_the_encoded_form_is_what_goes_on_the_wire():
    c, fake = _client()
    c.status("a/../../caps/victim")
    assert fake.requests[0].url.raw_path == b"/status/a%2F..%2F..%2Fcaps%2Fvictim"
