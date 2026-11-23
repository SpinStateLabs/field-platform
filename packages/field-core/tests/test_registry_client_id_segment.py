"""RegistryClient refuses a non-registry agent id before any request and encodes the segment (S12-7)."""
from __future__ import annotations

import httpx
import pytest

from field_core.clients import AgentNotRegisteredError, RegistryClient

BAD = ["..", ".", "%2e%2e", "%2E", "a%2fb", "a%25b", "x?y", "x/y", "x/attest", "", "A1", "a b", "a\nb"]


def _client():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"agent_id": "ok", "status": "active"})

    return RegistryClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://t"), seen


@pytest.mark.parametrize("agent_id", BAD)
def test_get_agent_sends_nothing_for_a_bad_id(agent_id):
    reg, seen = _client()
    with pytest.raises(AgentNotRegisteredError):
        reg.get_agent(agent_id)
    assert seen == []


@pytest.mark.parametrize("agent_id", BAD)
def test_set_status_sends_nothing_for_a_bad_id(agent_id):
    reg, seen = _client()
    with pytest.raises(AgentNotRegisteredError):
        reg.set_status(agent_id, "killed")
    assert seen == []


@pytest.mark.parametrize("agent_id", ["agent-1", "a.b_c-2", "a1"])
def test_good_ids_go_out_unchanged(agent_id):
    reg, seen = _client()
    reg.get_agent(agent_id)
    reg.set_status(agent_id, "killed")
    assert [r.url.path for r in seen] == [f"/agents/{agent_id}"] * 2
    assert [r.method for r in seen] == ["GET", "PATCH"]
