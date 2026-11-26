"""``RegistryClient`` refuses an id outside the registry's id rule before it builds a URL or sends anything. An id
inside the rule is sent as before."""

from __future__ import annotations

import httpx
import pytest

from field_core.clients import AgentNotRegisteredError, RegistryClient
from field_core.ids import REGISTRY_ID_MAX_LENGTH, registry_id_ok

VALID = ["invoicing-agent", "invoicing-agent.v2_x", "a", "0", "a..b", "a-", "a_", "a" * 128]
INVALID = ["", "a1?status=killed", "a1#frag", "a1/attest", "x/../health", "a/../x", "..", ".", "-a", ".a", "_a", "A1",
           "a b", " a", "a ", "a\nb", "a\n", "a\x00", "a%3F", "a%2Fb", "a\u202e", "a\u200f", "a\u2028", "\ufeffa",
           "\u00e9", "Org/agent", "a" * 129, "a" * 5000]


def _client(seen: list, status: int = 200) -> RegistryClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path.decode("ascii")))
        return httpx.Response(status, json={"agent_id": "a1", "status": "active"})

    return RegistryClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://registry")


CALLS = [("GET", lambda c, i: c.get_agent(i)), ("GET", lambda c, i: c.require_active_agent(i)),
         ("PATCH", lambda c, i: c.set_status(i, "killed")),
         ("PATCH", lambda c, i: c.set_status(i, "active", if_updated_at="2026-01-01T00:00:00+00:00",
                                             extra_headers={"x-field-operator-on-behalf-of": "don"}))]
CALL_IDS = ["get_agent", "require_active_agent", "set_status", "set_status-conditional"]


@pytest.mark.parametrize("method,call", CALLS, ids=CALL_IDS)
@pytest.mark.parametrize("agent_id", VALID)
def test_a_valid_id_is_sent_unchanged(method, call, agent_id):
    seen: list = []
    call(_client(seen), agent_id)
    assert seen == [(method, f"/agents/{agent_id}")]


@pytest.mark.parametrize("method,call", CALLS, ids=CALL_IDS)
@pytest.mark.parametrize("agent_id", INVALID)
def test_an_invalid_id_is_not_registered_and_nothing_is_sent(method, call, agent_id):
    seen: list = []
    with pytest.raises(AgentNotRegisteredError) as caught:
        call(_client(seen), agent_id)
    assert seen == [] and caught.value.args == (agent_id,)


@pytest.mark.parametrize("value", [None, 7, b"a1", ["a1"]])
def test_a_value_that_is_not_text_is_not_an_id(value):
    assert registry_id_ok(value) is False


def test_the_bound():
    assert REGISTRY_ID_MAX_LENGTH == 128


def test_a_404_for_a_valid_id_is_still_not_registered():
    seen: list = []
    with pytest.raises(AgentNotRegisteredError):
        _client(seen, status=404).get_agent("ghost")
    assert seen == [("GET", "/agents/ghost")]
