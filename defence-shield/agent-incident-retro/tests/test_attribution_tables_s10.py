"""B-S10-32 (scout S10-8): pin the attribution tables and the S.marker / S.launder clauses (tests only).

Before this file ``markers_for`` and ``intermediary_for`` were exercised through one row of each table, so a deleted
or mistyped row would pass the suite. The tables are data a customer engagement is expected to tune (signatures.py
header); this pins every row so a tuning edit that drops one is a red test, not a silent loss."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_incident_retro.clauses import Session, s_launder, s_marker
from agent_incident_retro.models import LineRef, Request
from agent_incident_retro.signatures import (
    AGENT_MARKERS,
    INTERMEDIARY_UA,
    MAX_MATCH_LEN,
    classify,
    intermediary_for,
    is_automation_ua,
    markers_for,
)

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
HOSTILE_QUERY = "q=%27%20OR%20%271%27%3D%271"


def test_the_tables_have_the_rows_the_scout_counted():
    assert len(AGENT_MARKERS) == 14
    assert len(INTERMEDIARY_UA) == 6


@pytest.mark.parametrize("token,label", list(AGENT_MARKERS.items()))
def test_every_agent_marker_returns_exactly_its_label_in_mixed_case(token, label):
    ua = f"Mozilla/5.0 (compatible; {token.upper()}/1.0; +https://example.invalid)"
    assert markers_for(ua) == [label]
    assert markers_for(token.title()) == [label]


@pytest.mark.parametrize("token,label", list(INTERMEDIARY_UA.items()))
def test_every_intermediary_returns_exactly_its_label_in_mixed_case(token, label):
    assert intermediary_for(f"Mozilla/5.0 {token.upper()}/2.0") == label


def test_two_markers_in_one_ua_return_both_labels_in_table_order():
    ua = "ClaudeBot GPTBot"                       # UA order is the reverse of the table order
    assert markers_for(ua) == [AGENT_MARKERS["gptbot"], AGENT_MARKERS["claudebot"]]


def test_no_marker_in_an_empty_or_ordinary_ua():
    assert markers_for("") == []
    assert markers_for("Mozilla/5.0") == []
    assert intermediary_for("") is None
    assert intermediary_for("Mozilla/5.0") is None


def test_the_first_intermediary_row_wins_when_two_appear():
    ua = "urlscan archive.org_bot"                # UA order is the reverse of the table order
    assert intermediary_for(ua) == INTERMEDIARY_UA["archive.org_bot"]


def test_matching_is_substring_not_word_current_behaviour():
    # CURRENT BEHAVIOUR, possibly a false-positive source: a token inside a longer word still matches.
    # Recorded here and in the PR, not fixed (tests-only card).
    assert markers_for("xgptbotx") == [AGENT_MARKERS["gptbot"]]
    assert intermediary_for("notwaybackmachine") == INTERMEDIARY_UA["wayback"]


def test_marker_and_intermediary_matchers_do_not_cap_their_input():
    # signatures.bounded()'s docstring says every public matcher caps its input; these two do not (plain substring
    # tests), so a token past MAX_MATCH_LEN is still found. Pinned as current behaviour.
    ua = "a" * (MAX_MATCH_LEN + 10) + "gptbot"
    assert markers_for(ua) == [AGENT_MARKERS["gptbot"]]
    assert intermediary_for("a" * (MAX_MATCH_LEN + 10) + "urlscan") == INTERMEDIARY_UA["urlscan"]


@pytest.mark.parametrize("ua,expected", [("python-requests/2.31", True), ("curl/8.4", True), ("Mozilla/5.0", False)])
def test_is_automation_ua(ua, expected):
    assert is_automation_ua(ua) is expected


def test_is_automation_ua_is_bounded_on_a_100_kb_ua():
    assert is_automation_ua("x" * 100_000) is False
    # a library token placed past the cap is not seen (bounded by MAX_MATCH_LEN)
    assert is_automation_ua("x" * MAX_MATCH_LEN + "curl/8.4") is False
    assert is_automation_ua("x" * (MAX_MATCH_LEN - 7) + "curl/8.4") is True


# ---------------------------------------------------------------- clauses


def _req(n, secs, query="", ua="ua"):
    fam, fps = classify("/search", query)
    return Request(
        ref=LineRef(input="x", line=n, sha256=f"{n:064x}"),
        ts=T0 + timedelta(seconds=secs),
        client_ip="203.0.113.1",
        method="GET",
        path="/search",
        query=query,
        status=200,
        user_agent=ua,
        raw=f"line{n}",
        families=fam,
        fingerprints=fps,
    )


def _sess(reqs):
    return Session(reqs[0].client_ip, reqs[0].user_agent, reqs)


def test_s_marker_cites_only_the_first_request_and_names_every_label():
    ua = "GPTBot ClaudeBot"
    s = _sess([_req(1, 0, ua=ua), _req(2, 5, ua=ua), _req(3, 9, ua=ua)])
    hit = s_marker(s)
    assert hit is not None and hit.clause == "S.marker"
    assert hit.detail == (f"self-declared marker(s) in user-agent: {AGENT_MARKERS['gptbot']}; "
                          f"{AGENT_MARKERS['claudebot']} — a claim by the client, spoofable")
    assert [r.line for r in hit.lines] == [1]


def test_s_marker_is_none_without_a_marker():
    assert s_marker(_sess([_req(1, 0, ua="Mozilla/5.0")])) is None


def test_s_launder_cites_only_the_hostile_requests_and_names_the_intermediary():
    ua = "archive.org_bot"
    s = _sess([_req(1, 0, "q=books", ua), _req(2, 5, HOSTILE_QUERY, ua), _req(3, 9, "q=more", ua)])
    assert [r.is_hostile for r in s.requests] == [False, True, False]
    hit = s_launder(s)
    assert hit is not None and hit.clause == "S.launder"
    assert hit.detail == (f"hostile requests arrived through a fetch intermediary ({INTERMEDIARY_UA['archive.org_bot']}); "
                          "the client IP is the intermediary's, not the originator's")
    assert [r.line for r in hit.lines] == [2]


def test_s_launder_is_none_for_an_intermediary_with_no_hostile_request():
    assert s_launder(_sess([_req(1, 0, "q=books", "archive.org_bot")])) is None


def test_s_launder_is_none_for_hostile_requests_not_through_an_intermediary():
    assert s_launder(_sess([_req(1, 0, HOSTILE_QUERY, "Mozilla/5.0")])) is None
