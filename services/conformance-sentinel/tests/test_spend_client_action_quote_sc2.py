"""PR 524 reviewer condition: SpendStatusClient.status(action=...) is the third URL-building
branch and was unpinned. Same TRICKY agent ids as the other methods: the id stays one encoded
`/status/<seg>` segment and the only query is the caller's own `action`."""
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
        self.requests.append(httpx.Client().build_request("GET", url, params=params))
        return _Resp()


@pytest.mark.parametrize("agent_id", TRICKY)
def test_status_with_action_keeps_the_id_in_one_segment(agent_id):
    fake = _Client()
    SpendStatusClient(client=fake, base_url="http://governor.invalid").status(agent_id, action="deploy")
    req = fake.requests[0]
    raw_path = req.url.raw_path.split(b"?")[0]
    assert raw_path.startswith(b"/status/") and raw_path.count(b"/") == 2
    assert not req.url.fragment
    assert dict(req.url.params) == {"action": "deploy"}      # nothing smuggled in from the id
