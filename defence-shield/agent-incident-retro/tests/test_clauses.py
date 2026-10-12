"""Unit tests for individual clauses, including false-positive guards."""

from datetime import datetime, timedelta, timezone

from agent_incident_retro.clauses import (
    Session,
    evaluate,
    s_escalate_on_block,
    s_pivot,
    sessionize,
)
from agent_incident_retro.models import LineRef, Request, RetroConfig, Verdict

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def req(n, secs, path, query="", status=200, ua="ua", ip="203.0.113.1"):
    from agent_incident_retro.signatures import classify

    fam, fps = classify(path, query)
    return Request(
        ref=LineRef(input="x", line=n, sha256=f"{n:064x}"),
        ts=T0 + timedelta(seconds=secs),
        client_ip=ip,
        method="GET",
        path=path,
        query=query,
        status=status,
        user_agent=ua,
        raw=f"line{n}",
        families=fam,
        fingerprints=fps,
    )


def sess(reqs):
    return Session(reqs[0].client_ip, reqs[0].user_agent, reqs)


def test_pivot_needs_same_path_and_param():
    s = sess([req(1, 0, "/search", "q=books"), req(2, 30, "/search", "q=%27%20OR%20%271%27%3D%271")])
    assert s_pivot(s, 300.0) is not None


def test_pivot_different_path_does_not_fire():
    s = sess([req(1, 0, "/a", "q=books"), req(2, 30, "/b", "q=%27%20OR%20%271%27%3D%271")])
    assert s_pivot(s, 300.0) is None


def test_pivot_outside_window_does_not_fire():
    s = sess([req(1, 0, "/search", "q=books"), req(2, 9999, "/search", "q=%27%20OR%20%271%27%3D%271")])
    assert s_pivot(s, 300.0) is None


def test_escalate_on_block_requires_new_family_after_hostile_block():
    # a plain retry of the same blocked hostile target is not an escalation
    s = sess([
        req(1, 0, "/x", "q=%27%20OR%20%271%27%3D%271", status=403),
        req(2, 10, "/x", "q=%27%20OR%20%271%27%3D%271", status=403),
    ])
    assert s_escalate_on_block(s, 300.0) is None


def test_escalate_on_block_fires_on_new_family_after_block():
    s = sess([
        req(1, 0, "/x", "q=books", status=404),
        req(2, 10, "/x", "q=%3Cscript%3Ealert(1)%3C/script%3E", status=200),
    ])
    assert s_escalate_on_block(s, 300.0) is not None


def test_human_404s_do_not_escalate():
    reqs = [req(i, i * 30, "/missing", status=404) for i in range(5)]
    s = sess(reqs)
    assert s_escalate_on_block(s, 300.0) is None  # no hostile follow-up


def test_sessionize_splits_on_idle_gap():
    reqs = [req(1, 0, "/"), req(2, 100, "/"), req(3, 5000, "/")]
    sessions = sessionize(reqs, RetroConfig(session_gap_s=1800))
    assert len(sessions) == 2


def test_sessionize_separates_distinct_ua():
    reqs = [req(1, 0, "/", ua="a"), req(2, 10, "/", ua="b")]
    assert len(sessionize(reqs, RetroConfig())) == 2


def test_benign_only_session_is_clear():
    reqs = [req(i, i * 20, "/page", "q=news") for i in range(6)]
    findings, _, counts = evaluate(sessionize(reqs, RetroConfig()), RetroConfig())
    assert not findings
    assert counts["CLEAR"] == 1


def test_empty_query_apostrophe_is_not_sqli():
    # a legitimate search for O'Brien must not trip the SQLi pattern
    s = sess([req(1, 0, "/search", "q=O%27Brien")])
    findings, _, _ = evaluate([s], RetroConfig())
    assert not findings


def test_grade_never_returns_g3_on_any_clause_set():
    """G3 (verified identity) is Declared-only in v0.1: grade_for must never
    emit it, for any user-agent or combination of clauses."""
    from itertools import combinations

    from agent_incident_retro.clauses import grade_for
    from agent_incident_retro.models import Grade

    uas = ["", "curl/8.4", "Mozilla/5.0", "GPTBot/1.0", "archive.org_bot"]
    all_clauses = ["S.inject", "S.debug-probe", "S.pivot", "S.escalate-on-block", "S.cadence", "S.marker", "S.launder"]
    for ua in uas:
        s = sess([req(1, 0, "/x", "q=1", ua=ua)])
        for k in range(len(all_clauses) + 1):
            for combo in combinations(all_clauses, k):
                grade, _, _ = grade_for(s, set(combo))
                assert grade is not Grade.G3


def test_benign_queries_do_not_false_escalate():
    """The false-positive classes the review found must not ESCALATE."""
    cases = [
        ("/search", "q=graduation+gifts", "/search", "q=students%27+%231+gift+picks"),  # ' then #1
        ("/search", "q=soldiers+monuments", "/search", "q=Soldiers%27--Canada"),  # LCSH subdivision
        ("/search", "q=dog+food", "/search", "q=dog+%26+cat+food"),  # & cat
    ]
    for p1, q1, p2, q2 in cases:
        s = sess([req(1, 0, p1, q1), req(2, 30, p2, q2)])
        findings, _, _ = evaluate([s], RetroConfig())
        assert not findings, (p2, q2, [c.clause for f in findings for c in f.clauses])
