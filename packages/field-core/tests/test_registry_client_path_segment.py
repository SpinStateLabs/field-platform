"""``RegistryClient`` puts an agent id into the URL as ONE percent-encoded segment: a ``?``, ``#``, ``/`` or dot segment
in it cannot change which record is read or written. An id in the registry's id rule is sent exactly as before."""

from __future__ import annotations

import httpx
import pytest

from field_core.clients import AgentNotRegisteredError, RegistryClient

CASES = [
    ("invoicing-agent.v2_x", "invoicing-agent.v2_x"),
    ("a..b", "a..b"),
    ("a1?status=killed", "a1%3Fstatus%3Dkilled"),
    ("a1#frag", "a1%23frag"),
    ("a1/attest", "a1%2Fattest"),
    ("x/../health", "x%2F..%2Fhealth"),
    ("..", "%2E%2E"),
    (".", "%2E"),
    ("a b", "a%20b"),
    ("a\nb", "a%0Ab"),
    ("a%3F", "a%253F"),
    ("a" * 300, "a" * 300),
]


def _client(seen: list, status: int = 200) -> RegistryClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode("ascii")))
        return httpx.Response(status, json={"agent_id": "a1", "status": "active"})

    return RegistryClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://registry")


@pytest.mark.parametrize("agent_id,segment", CASES)
def test_get_agent_sends_one_segment(agent_id, segment):
    seen: list = []
    _client(seen).get_agent(agent_id)
    assert seen == [("GET", f"/agents/{segment}")]


@pytest.mark.parametrize("agent_id,segment", CASES)
def test_set_status_sends_one_segment(agent_id, segment):
    seen: list = []
    _client(seen).set_status(agent_id, "killed")
    assert seen == [("PATCH", f"/agents/{segment}")]


def test_the_error_for_an_unknown_id_still_names_the_id_asked_for():
    with pytest.raises(AgentNotRegisteredError) as caught:
        _client([], status=404).get_agent("a1?x")
    assert caught.value.args == ("a1?x",)
