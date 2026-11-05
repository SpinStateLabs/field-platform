"""S8-5: a non-ALLOW verdict whose `reasons` is not a list of strings is still a CrossingBlocked.

`cross()` built its message with `'; '.join(str(r) for r in verdict.get('reasons') or [])`: an int raised TypeError out of
the except-handling path (an agent written `except CrossingBlocked` crashed instead of refusing), and a string was joined
character by character. The fail-closed contract is that anything but an exact ALLOW is a CrossingBlocked that keeps the
verdict and its clause_id. A broker that is a pydantic model cannot emit these; the cases are a proxy or a version skew."""

import pytest

from field_agent.federation import CrossingBlocked, FederationClient

from test_federation_sdk import COUNTERPARTY, DATA_CLASS, OUR_AGENT, SCOPE, Canned, our_manifest


def blocked(reasons, decision="BLOCK", clause="F.peer", **extra):
    body = {"decision": decision, "agent_id": "x", "action": SCOPE, "clause_id": clause, "reasons": reasons, **extra}
    client = FederationClient(client=Canned(200, body), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    return caught.value, body


@pytest.mark.parametrize("reasons", [7, 1.5, True, None, {"a": 1}, "because", "x" * 10_000, ["ok", 3, None, {"k": 1}]],
                         ids=["int", "float", "bool", "null", "dict", "str", "long-str", "mixed-list"])
@pytest.mark.parametrize("decision", ["BLOCK", "ESCALATE"])
def test_odd_reasons_still_raise_crossing_blocked_keeping_the_verdict_and_clause(reasons, decision):
    exc, body = blocked(reasons, decision=decision)
    assert exc.clause_id == "F.peer" and exc.verdict == body
    assert str(exc).startswith(f"crossing {decision} by F.peer:")
    assert len(str(exc)) < 700                                  # the joined reasons are bounded


def test_a_string_reasons_is_one_reason_not_its_characters():
    exc, _ = blocked("because")
    assert str(exc) == "crossing BLOCK by F.peer: because"


def test_non_list_non_string_reasons_are_empty():
    for reasons in (7, None, {"a": 1}):
        exc, _ = blocked(reasons)
        assert str(exc) == "crossing BLOCK by F.peer: "


def test_a_mixed_list_keeps_only_its_string_items():
    """Reviewer C1 (PR 764): non-string list items are dropped, not str()-ed (kills the mutant that keeps them)."""
    exc, _ = blocked(["ok", 3, None, {"k": 1}])
    assert str(exc) == "crossing BLOCK by F.peer: ok"
    exc, _ = blocked([3, "a", 4.5, "b", True])
    assert str(exc) == "crossing BLOCK by F.peer: a; b"


def test_a_list_of_strings_joins_as_before():
    exc, _ = blocked(["no contract", "scope not allowed"])
    assert str(exc) == "crossing BLOCK by F.peer: no contract; scope not allowed"


def test_a_missing_reasons_key_and_an_empty_list_are_empty():
    body = {"decision": "BLOCK", "clause_id": "F.peer"}
    client = FederationClient(client=Canned(200, body), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert str(caught.value) == "crossing BLOCK by F.peer: "


@pytest.mark.parametrize("body", [["BLOCK"], "BLOCK", 5, None], ids=["list", "str", "int", "null"])
def test_a_verdict_that_is_not_an_object_is_no_verdict(body):
    client = FederationClient(client=Canned(200, body), base_url="http://t")
    with pytest.raises(CrossingBlocked) as caught:
        client.cross(OUR_AGENT, COUNTERPARTY, SCOPE, DATA_CLASS, our_manifest())
    assert caught.value.verdict is None and "failing closed" in str(caught.value)
