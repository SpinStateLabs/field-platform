"""S3-23: S.pivot re-parsed the query of every benign request inside the loop over hostile requests (hostile x benign
parse_qsl calls on attacker-controlled strings), and compared values that param_values did NOT cap while
hostile_params did (signatures.py: bounded() is applied before any matcher). Now each request's query is parsed at
most once, and param_values caps keys and values with the same bounded()."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_incident_retro import clauses
from agent_incident_retro.clauses import Session, s_pivot
from agent_incident_retro.models import LineRef, Request
from agent_incident_retro.signatures import MAX_MATCH_LEN, classify, param_values

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
SQLI = "%27%20OR%20%271%27%3D%271"      # a payload in the first bytes of a value


def req(n, secs, path, query):
    fam, fps = classify(path, query)
    return Request(ref=LineRef(input="x", line=n, sha256=f"{n:064x}"), ts=T0 + timedelta(seconds=secs),
                   client_ip="203.0.113.1", method="GET", path=path, query=query, status=200, user_agent="ua",
                   raw=f"line{n}", families=fam, fingerprints=fps)


def sess(reqs):
    return Session(reqs[0].client_ip, reqs[0].user_agent, reqs)


# ---- (a) cost -------------------------------------------------------------------------------------------------


def test_the_number_of_query_parses_is_linear_not_hostile_times_benign(monkeypatch):
    n = 2000
    benign = [req(i, i * 0.1, "/search", f"q=book{i}") for i in range(n)]                    # all inside the 300 s window
    hostile = [req(n + i, 250 + i * 0.01, "/search", f"id={SQLI}{i}") for i in range(n)]    # param `id` is in NO benign query
    s = sess(benign + hostile)
    assert all(not b.is_hostile for b in benign) and all(h.is_payload for h in hostile)
    calls = []
    real = clauses.param_values

    def counting(q):
        calls.append(q)
        return real(q)

    monkeypatch.setattr(clauses, "param_values", counting)
    assert s_pivot(s, 300.0) is None                      # no shared parameter, so every benign request is scanned
    assert len(calls) <= 2 * n                            # once per request at most; before: about n * n = 4,000,000
    assert len(calls) == len(set(calls))


def test_a_repeated_query_is_still_parsed_once_per_request_and_the_verdict_is_unchanged():
    s = sess([req(1, 0, "/search", "q=books"), req(2, 10, "/search", "q=books"),
              req(3, 20, "/search", f"q={SQLI}"), req(4, 30, "/search", f"q={SQLI}")])
    hit = s_pivot(s, 300.0)
    assert hit is not None and hit.detail.startswith("2 benign→tampered pivot(s)")


# ---- (b) caps -------------------------------------------------------------------------------------------------


def test_param_values_caps_keys_and_values_like_the_matchers():
    long_v, long_k = "v" * (MAX_MATCH_LEN + 500), "k" * (MAX_MATCH_LEN + 500)
    got = param_values(f"{long_k}={long_v}&a=b")
    assert got == {"k" * MAX_MATCH_LEN: "v" * MAX_MATCH_LEN, "a": "b"}


def test_an_over_long_parameter_name_is_compared_capped_on_both_sides():
    """hostile_params names the tampered parameter CAPPED; the benign request's keys were looked up UNCAPPED, so a
    parameter name over the cap never matched itself and the search-then-tamper pivot was missed."""
    key = "k" * (MAX_MATCH_LEN + 900)
    benign = req(1, 0, "/search", f"{key}=books")
    hostile = req(2, 30, "/search", f"{key}={SQLI}")
    assert hostile.is_payload and not benign.is_hostile
    hit = s_pivot(sess([benign, hostile]), 300.0)
    assert hit is not None and hit.detail.startswith("1 benign→tampered pivot(s)")


def test_a_value_longer_than_the_cap_is_compared_on_its_head_only():
    """Values are capped like the matchers see them. (A benign request equal to a hostile one's capped form would
    itself classify as hostile, so this cannot flip a verdict; it bounds what is held and compared.)"""
    benign = req(1, 0, "/search", "q=" + "A" * (MAX_MATCH_LEN + 100) + "1")
    other = req(2, 5, "/search", "q=" + "A" * (MAX_MATCH_LEN + 100) + "2")
    assert param_values(benign.query) == param_values(other.query)       # differ only after the cap
    hostile = req(3, 30, "/search", f"q={SQLI}")
    assert s_pivot(sess([benign, other, hostile]), 300.0) is not None   # a difference inside the cap still pivots


def test_a_difference_inside_the_cap_still_fires():
    benign = req(1, 0, "/search", "q=" + "A" * 100)
    hostile = req(2, 30, "/search", "q=" + "' OR 1=1 --" + "A" * 100)
    assert s_pivot(sess([benign, hostile]), 300.0) is not None


@pytest.mark.parametrize("cap", [MAX_MATCH_LEN])
def test_the_cap_is_the_one_in_signatures(cap):
    assert cap == 8192
