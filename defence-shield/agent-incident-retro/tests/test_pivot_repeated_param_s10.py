"""S10-31: a repeated query parameter must not hide the tamper from S.pivot.

`param_values` kept the LAST value per name, so a hostile request `q=<payload>&q=cat` after a benign `q=cat`
compared equal ("cat" == "cat") and no pivot was recorded (an HTTP-parameter-pollution evasion of "search, then
tamper"). Every value is now kept, capped like `_hostile_tokens`, and a parameter is tampered when ANY value in the
hostile request is absent from ALL values the benign request gave the same name.
"""
from datetime import datetime, timedelta, timezone

import pytest

from agent_incident_retro.clauses import Session, s_pivot
from agent_incident_retro.models import LineRef, Request
from agent_incident_retro.signatures import MAX_MATCH_LEN, classify, param_values

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
PAYLOAD = "%27%20or%201%3D1--"   # ' or 1=1--


def req(n, secs, query, path="/search"):
    fam, fps = classify(path, query)
    return Request(ref=LineRef(input="x", line=n, sha256=f"{n:064x}"), ts=T0 + timedelta(seconds=secs),
                   client_ip="203.0.113.1", method="GET", path=path, query=query, status=200, user_agent="ua",
                   raw=f"line{n}", families=fam, fingerprints=fps)


def pivot(*reqs):
    return s_pivot(Session(reqs[0].client_ip, reqs[0].user_agent, list(reqs)), 300.0)


def test_param_values_keeps_every_value_in_order():
    assert param_values("a=1&a=2&b") == {"a": ["1", "2"], "b": [""]}


def test_param_values_single_values_are_one_element_lists():
    assert param_values("q=cat&n=2") == {"q": ["cat"], "n": ["2"]}


def test_param_values_caps_keys_and_values():
    big = "x" * (MAX_MATCH_LEN + 50)
    got = param_values(f"{big}={big}")
    assert list(got) == ["x" * MAX_MATCH_LEN] and got["x" * MAX_MATCH_LEN] == ["x" * MAX_MATCH_LEN]


def test_a_payload_before_a_benign_repeat_still_fires():
    """The evasion: the last value of q is the benign one."""
    hit = pivot(req(1, 0, "q=cat"), req(2, 30, f"q={PAYLOAD}&q=cat"))
    assert hit is not None and hit.clause == "S.pivot"
    assert [r.line for r in hit.lines] == [1, 2]


def test_a_payload_after_a_benign_repeat_still_fires():
    assert pivot(req(1, 0, "q=cat"), req(2, 30, f"q=cat&q={PAYLOAD}")) is not None


def test_a_benign_request_with_a_repeated_name_is_compared_against_all_its_values():
    assert pivot(req(1, 0, "q=cat&q=dog"), req(2, 30, f"q=dog&q={PAYLOAD}")) is not None


def test_a_hostile_value_equal_to_one_benign_value_is_not_a_tamper_of_that_value():
    """The payload itself was already in the benign request: nothing changed, so no pivot (unchanged rule)."""
    benign = f"q={PAYLOAD}"
    assert pivot(req(1, 0, benign), req(2, 30, f"q={PAYLOAD}&q={PAYLOAD}")) is None


def test_single_valued_cases_are_unchanged():
    assert pivot(req(1, 0, "q=books"), req(2, 30, f"q={PAYLOAD}")) is not None
    assert pivot(req(1, 0, "q=books"), req(2, 30, "q=books")) is None
    assert pivot(req(1, 0, "q=books"), req(2, 30, f"r={PAYLOAD}")) is None      # a different parameter
    assert pivot(req(1, 0, "r=books"), req(2, 30, f"q={PAYLOAD}")) is None      # the benign one lacks the name


@pytest.mark.parametrize("query", [f"q={PAYLOAD}&q=cat", f"q=cat&q={PAYLOAD}"])
def test_a_different_path_still_does_not_fire(query):
    assert pivot(req(1, 0, "q=cat", path="/a"), req(2, 30, query, path="/b")) is None
