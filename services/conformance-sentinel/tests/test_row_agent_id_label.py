"""A verdict row is keyed by the request's agent id only inside the registry's id rule; otherwise by a short printable
label of it, or by none. The verdict still answers for the id as sent."""

from __future__ import annotations

import pytest

from field_core.operator_health import NOT_SHOWN
from tests.conftest import AGENT_ID

#: sent id -> the id its row is keyed by
CASES = [("Org/agent", "Org/agent"), ("ABC", "ABC"), ("a?b=1", None), ("a b", None), ("a" + chr(10) + "b", None),
         ("a" + chr(0x202E) + "b", None), ("A" * 65, None), ("a" * 129, None),
         # inside the rule and longer than a printable label may be: keyed by the id itself
         ("a" * 65, "a" * 65), ("a" * 128, "a" * 128)]


def _check(stack, agent_id):
    return stack.sentinel.post("/check", json={"agent_id": agent_id, "action": "draft invoices", "token_id": "t"})


def _blocks(stack):
    return stack.ledger.get("/events", params={"event_type": "conformance.block"}).json()


@pytest.mark.parametrize("sent,keyed", CASES)
def test_the_row_of_a_block_for_an_id_outside_the_rule(stack, sent, keyed):
    verdict = _check(stack, sent).json()
    assert verdict["decision"] == "BLOCK" and verdict["clause_id"] == "R.unregistered"
    assert verdict["agent_id"] == sent
    row = _blocks(stack)[-1]
    assert row.get("agent_id") == keyed
    assert verdict["reasons"] == row["payload"]["reasons"]
    quoted = keyed if keyed is not None else NOT_SHOWN
    assert verdict["reasons"][0] == f"agent '{quoted}' is not in the registry"


def test_a_valid_id_keys_its_row_unchanged(stack):
    _check(stack, AGENT_ID)
    rows = stack.ledger.get("/events", params={"agent_id": AGENT_ID}).json()
    assert rows and rows[-1]["agent_id"] == AGENT_ID
