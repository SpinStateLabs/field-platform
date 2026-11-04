"""S5-13: POST /check caps what a caller can put into every verdict's ledger payload, and an agent_id the registry
could never hold is answered R.unregistered WITHOUT a registry call (the client puts the id into a URL path)."""

from __future__ import annotations

import pytest

from conformance_sentinel.engine import (
    ACTION_MAX, AGENT_ID_MAX, CONTEXT_MAX_BYTES, CONTEXT_MAX_KEYS, TOKEN_ID_MAX,
)
from conformance_sentinel.mode import SentinelMode
from tests.conftest import AGENT_ID

MARK = "MADE-UP-MARKER-0123456789"


def over(n):
    return MARK + "x" * (n - len(MARK) + 1)


def post(stack, **over_):
    body = {"agent_id": AGENT_ID, "action": "draft invoices", "token_id": "t"}
    body.update(over_)
    return stack.sentinel.post("/check", json=body)


class Spy:
    """Wraps the engine's registry and records every get_agent id."""
    def __init__(self, real):
        self.real, self.ids = real, []

    def get_agent(self, agent_id):
        self.ids.append(agent_id)
        return self.real.get_agent(agent_id)


@pytest.fixture()
def spy(stack):
    eng = stack.sentinel.app.state.engine
    s = Spy(eng.registry)
    eng.registry = s
    return s


def test_limits_are_the_card_numbers():
    assert (AGENT_ID_MAX, TOKEN_ID_MAX, ACTION_MAX, CONTEXT_MAX_KEYS, CONTEXT_MAX_BYTES) == (200, 200, 2000, 50, 16384)


# ---- bounds -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field,limit", [("agent_id", AGENT_ID_MAX), ("token_id", TOKEN_ID_MAX), ("action", ACTION_MAX)])
def test_over_limit_is_422_without_echo(stack, field, limit):
    r = post(stack, **{field: over(limit)})
    assert r.status_code == 422 and MARK not in r.text


@pytest.mark.parametrize("field,limit", [("token_id", TOKEN_ID_MAX), ("action", ACTION_MAX)])
def test_at_limit_is_accepted(stack, field, limit):
    assert post(stack, **{field: "y" * limit}).status_code == 200


def test_agent_id_at_limit_is_accepted_and_blocked_as_unregistered(stack, spy):
    r = post(stack, agent_id="a" * AGENT_ID_MAX)
    assert r.status_code == 200 and r.json()["clause_id"] == "R.unregistered"


def test_context_key_count_and_size_limits(stack):
    assert post(stack, context={f"k{i}": 1 for i in range(CONTEXT_MAX_KEYS)}).status_code == 200
    r = post(stack, context={f"k{i}": MARK for i in range(CONTEXT_MAX_KEYS + 1)})
    assert r.status_code == 422 and MARK not in r.text
    assert post(stack, context={"k": "y" * (CONTEXT_MAX_BYTES - 20)}).status_code == 200
    r = post(stack, context={"k": MARK + "y" * CONTEXT_MAX_BYTES})
    assert r.status_code == 422 and MARK not in r.text


def test_context_size_counts_bytes_not_characters(stack):
    assert post(stack, context={"k": "é" * 4000}).status_code == 200          # 8000 bytes
    assert post(stack, context={"k": "é" * 9000}).status_code == 422          # 18000 bytes, 9000 characters


def test_deeply_nested_context_is_a_422_not_a_500(stack):
    deep = "[" * 5000 + "]" * 5000
    r = stack.sentinel.post("/check", content=f'{{"agent_id":"{AGENT_ID}","action":"a","context":{{"k":{deep}}}}}',
                            headers={"content-type": "application/json"})
    assert r.status_code in (200, 422), r.text


# ---- shape-check before the registry call ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["x/../health", "a?b=1", "a#f", "A", "-a", "a b", "a/b", "a\n", "é", ".a", "a%2Fb"])
def test_a_non_registry_shaped_id_is_blocked_without_a_registry_call(stack, spy, bad):
    r = post(stack, agent_id=bad)
    assert r.status_code == 200
    v = r.json()
    assert v["decision"] == "BLOCK" and v["clause_id"] == "R.unregistered"
    assert "not in the registry" in v["reasons"][0]
    assert spy.ids == []


def test_the_block_is_ledgered_like_any_unregistered_block(stack, spy):
    post(stack, agent_id="x/../health")
    blocks = stack.ledger.get("/events", params={"event_type": "conformance.block"}).json()
    assert blocks and blocks[-1]["payload"]["clause_id"] == "R.unregistered"


def test_log_only_shadow_behaviour_is_the_same_for_a_bad_id(stack, spy):
    stack.sentinel.app.state.engine.mode = SentinelMode.LOG_ONLY
    v = post(stack, agent_id="a?b=1").json()
    assert v["decision"] == "ALLOW" and v["context"]["shadowed"] is True
    assert v["context"]["would_be"]["clause_id"] == "R.unregistered" and spy.ids == []
    shadows = stack.ledger.get("/events", params={"event_type": "conformance.shadow_block"}).json()
    assert shadows[-1]["payload"]["would_block"] == "R.unregistered"


def test_a_ledger_outage_still_wins_over_the_id_check(stack, spy):
    stack.ledger_up = False
    assert post(stack, agent_id="a?b=1").json()["clause_id"] == "L.unreachable"


def test_a_normal_id_is_unchanged(stack, spy):
    stack.set_cap()
    token = stack.mint_token()
    v = stack.check("draft invoices", token_id=token)
    assert v["decision"] == "ALLOW" and spy.ids == [AGENT_ID]
    assert post(stack, agent_id="ghost").json()["clause_id"] == "R.unregistered" and spy.ids[-1] == "ghost"
