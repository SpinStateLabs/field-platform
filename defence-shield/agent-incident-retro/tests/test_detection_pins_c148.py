"""C-148 (reviewer C-141 F-C141-3/-4): the detection logic's negative cases and boundaries.

* `_allowlisted` (clauses.py) downgrades ESCALATE to AUTHORIZED, and `scan` exits 2 only on ESCALATE,
  so a wrong match silences the scheduled alert: every near-miss must still ESCALATE, and an
  AUTHORIZED session must not exit 2;
* the pivot, escalate-on-block, cadence, campaign, session-gap and grade boundaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_incident_retro.clauses import (Session, campaigns, evaluate, features, grade_for, s_cadence,
                                          s_escalate_on_block, s_pivot, sessionize, verdict_for)
from agent_incident_retro.cli import app
from agent_incident_retro.models import Grade, LineRef, Request, RetroConfig, Verdict
from agent_incident_retro.signatures import classify

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
SQLI = "q=%27%20OR%20%271%27%3D%271"
XSS = "q=%3Cscript%3Ealert(1)%3C/script%3E"
HOSTILE_IP = "203.0.113.5"


def req(n, secs, path, query="", status=200, ua="Mozilla/5.0", ip=HOSTILE_IP):
    fam, fps = classify(path, query)
    return Request(
        ref=LineRef(input="x", line=n, sha256=f"{n:064x}"), ts=T0 + timedelta(seconds=secs),
        client_ip=ip, method="GET", path=path, query=query, status=status, user_agent=ua,
        raw=f"line{n}", families=fam, fingerprints=fps)


def sess(reqs):
    return Session(reqs[0].client_ip, reqs[0].user_agent, reqs)


def hostile_session(ip=HOSTILE_IP, ua="Mozilla/5.0"):
    """Benign use of /search then a tampered SQLi request: S.inject + S.pivot -> ESCALATE."""
    return sess([req(1, 0, "/search", "q=books", ip=ip, ua=ua), req(2, 30, "/search", SQLI, ip=ip, ua=ua)])


def verdict_of(session, **cfg):
    findings, _, counts = evaluate([session], RetroConfig(**cfg))
    return findings[0].verdict, findings[0].authorized_by


# --- F-C141-3: the allowlist -------------------------------------------------------------


def test_the_baseline_session_escalates():
    assert verdict_of(hostile_session()) == (Verdict.ESCALATE, None)


@pytest.mark.parametrize("cfg", [
    {"allow_ips": ["198.51.100.0/24"]},                      # another CIDR
    {"allow_ips": ["198.51.100.7"]},                         # another bare IP
    {"allow_ips": ["not-an-ip"]},                            # not an address at all
    {"allow_ips": ["203.0.113.5/33"]},                       # an impossible prefix
    {"allow_ips": ["203.0.113.6"]},                          # the neighbouring address
    {"allow_ips": ["203.0.114.0/24"]},                       # the neighbouring network
    {"allow_ua_substrings": ["curl"]},                       # a non-matching substring
    {"allow_ua_substrings": [""]},                           # an empty substring matches nothing
    {"allow_ips": [], "allow_ua_substrings": []},
], ids=repr)
def test_a_near_miss_allowlist_entry_still_escalates(cfg):
    assert verdict_of(hostile_session(), **cfg) == (Verdict.ESCALATE, None)


@pytest.mark.parametrize(("cfg", "by"), [
    ({"allow_ips": ["203.0.113.0/24"]}, "allow_ips 203.0.113.0/24"),
    ({"allow_ips": ["203.0.113.5"]}, "allow_ips 203.0.113.5"),
    ({"allow_ips": ["203.0.113.5/32"]}, "allow_ips 203.0.113.5/32"),
    ({"allow_ips": ["203.0.113.77/24"]}, "allow_ips 203.0.113.77/24"),   # host bits set: still the /24
    ({"allow_ips": ["::ffff:203.0.113.5"]}, "allow_ips ::ffff:203.0.113.5"),
    ({"allow_ips": ["198.51.100.0/24", "203.0.113.0/24"]}, "allow_ips 203.0.113.0/24"),
    ({"allow_ua_substrings": ["mozilla"]}, "allow_ua_substrings 'mozilla'"),
    ({"allow_ua_substrings": ["curl", "ZILLA"]}, "allow_ua_substrings 'ZILLA'"),
])
def test_a_matching_allowlist_entry_authorizes_and_says_which(cfg, by):
    assert verdict_of(hostile_session(), **cfg) == (Verdict.AUTHORIZED, by)


def test_a_client_that_is_not_an_ip_is_never_allowlisted():
    """Pinned as found (clauses.py `_allowlisted`): a client the log wrote as a non-address (a proxy
    log's "unknown", a hostname) has no `ip`, so no entry is tried and the `except ValueError`
    literal-match branch is not reachable for it: the session stays ESCALATE, never silenced."""
    odd = hostile_session(ip="unknown")
    for entry in ("unknown", "other", "0.0.0.0/0", "::/0"):
        assert verdict_of(odd, allow_ips=[entry]) == (Verdict.ESCALATE, None), entry
    assert verdict_of(odd, allow_ua_substrings=["mozilla"])[0] is Verdict.AUTHORIZED   # the UA path still works


def test_a_clear_session_is_never_marked_authorized():
    clear = sess([req(1, 0, "/about"), req(2, 5, "/contact")])
    findings, _, counts = evaluate([clear], RetroConfig(allow_ips=[HOSTILE_IP]))
    assert findings == [] and counts["CLEAR"] == 1 and counts["AUTHORIZED"] == 0


LOG = ('{ip} - - [01/Sep/2026:00:00:{s:02d} +0000] "GET {target} HTTP/1.1" 200 5 "-" "Mozilla/5.0"\n')


def hostile_log(tmp_path: Path) -> Path:
    log = tmp_path / "hostile.log"
    log.write_text(LOG.format(ip=HOSTILE_IP, s=0, target="/search?q=books")
                   + LOG.format(ip=HOSTILE_IP, s=30, target="/search?" + SQLI), encoding="utf-8")
    return log


def scan(tmp_path, *extra):
    tmp_path.mkdir(exist_ok=True)
    runner = CliRunner()
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    return runner.invoke(app, ["scan", str(hostile_log(tmp_path)), "--out", str(tmp_path / "o"),
                               "--key", str(tmp_path / "k"), *extra])


def test_the_scan_exits_2_for_the_hostile_log_and_0_when_every_session_is_authorized(tmp_path):
    r = scan(tmp_path / "plain")
    assert r.exit_code == 2 and "ESCALATE 1" in r.output
    r = scan(tmp_path / "allowed", "--allow-ip", "203.0.113.0/24")
    assert r.exit_code == 0 and "AUTHORIZED 1" in r.output and "ESCALATE 0" in r.output


def test_a_near_miss_allow_ip_does_not_silence_the_exit_code(tmp_path):
    r = scan(tmp_path / "nearmiss", "--allow-ip", "198.51.100.0/24")
    assert r.exit_code == 2 and "ESCALATE 1" in r.output


# --- F-C141-4: S.pivot ---------------------------------------------------------------------


@pytest.mark.parametrize(("gap", "fires"), [(299.999, True), (300.0, True), (300.001, False)])
def test_the_pivot_window_is_inclusive(gap, fires):
    s = sess([req(1, 0, "/search", "q=books"), req(2, gap, "/search", SQLI)])
    assert (s_pivot(s, 300.0) is not None) is fires


def test_a_pivot_needs_the_tampered_value_to_differ_from_the_benign_one():
    s = sess([req(1, 0, "/search", SQLI), req(2, 30, "/search", SQLI)])
    assert s_pivot(s, 300.0) is None


def test_a_pivot_counts_each_tampered_request_once():
    s = sess([req(1, 0, "/search", "q=books"), req(2, 10, "/search", SQLI), req(3, 20, "/search", XSS)])
    hit = s_pivot(s, 300.0)
    assert hit is not None and hit.detail.startswith("2 benign")


# --- F-C141-4: S.escalate-on-block ---------------------------------------------------------


@pytest.mark.parametrize(("gap", "fires"), [(299.999, True), (300.0, True), (300.001, False)])
def test_the_escalate_on_block_window_is_inclusive(gap, fires):
    s = sess([req(1, 0, "/x", "a=1", status=404), req(2, gap, "/x", XSS, status=200)])
    assert (s_escalate_on_block(s, 300.0) is not None) is fires


def test_a_hostile_request_on_the_same_path_but_another_query_is_an_escalation_not_a_retry():
    s = sess([req(1, 0, "/x", "a=1", status=404), req(2, 10, "/x", "a=1&" + XSS, status=200)])
    assert s_escalate_on_block(s, 300.0) is not None


def test_a_hostile_request_on_another_path_with_the_same_query_is_an_escalation_not_a_retry():
    s = sess([req(1, 0, "/x", "a=1", status=404), req(2, 10, "/.env", "a=1", status=200)])
    assert s_escalate_on_block(s, 300.0) is not None


def test_plain_retries_are_skipped_when_looking_for_the_follow_up_and_a_later_new_family_still_counts():
    s = sess([req(1, 0, "/x", SQLI, status=403), req(2, 10, "/x", SQLI, status=403),
              req(3, 20, "/x", XSS, status=200)])
    hit = s_escalate_on_block(s, 300.0)
    assert hit is not None and hit.detail.startswith("2 block")      # each block escalates to the XSS
    assert {r.line for r in hit.lines} == {1, 2, 3}


def test_a_hostile_block_followed_by_the_same_family_elsewhere_is_not_an_escalation():
    s = sess([req(1, 0, "/x", SQLI, status=403), req(2, 10, "/y", SQLI, status=200)])
    assert s_escalate_on_block(s, 300.0) is None


@pytest.mark.parametrize("status", [200, 301, 399, 500, 503])
def test_only_a_4xx_answer_counts_as_a_block(status):
    s = sess([req(1, 0, "/x", "a=1", status=status), req(2, 10, "/y", XSS, status=200)])
    assert s_escalate_on_block(s, 300.0) is None


@pytest.mark.parametrize("status", [400, 404, 499])
def test_a_4xx_answer_is_a_block(status):
    s = sess([req(1, 0, "/x", "a=1", status=status), req(2, 10, "/y", XSS, status=200)])
    assert s_escalate_on_block(s, 300.0) is not None


def test_a_benign_block_followed_by_any_hostile_request_is_an_escalation():
    s = sess([req(1, 0, "/x", "a=1", status=403), req(2, 10, "/y", SQLI, status=200)])
    assert s_escalate_on_block(s, 300.0) is not None


# --- F-C141-4: S.cadence -------------------------------------------------------------------


def regular(n, step=1.0, **kw):
    return sess([req(i, i * step, f"/p{i}", **kw) for i in range(n)])


def cadence(s, **cfg):
    return s_cadence(s, features(s), RetroConfig(**cfg))


def test_cadence_needs_the_minimum_number_of_requests():
    assert cadence(regular(20)) is not None                    # exactly the default minimum
    assert cadence(regular(19)) is None
    assert cadence(regular(3), cadence_min_requests=3) is not None
    assert cadence(regular(2), cadence_min_requests=2) is None  # one gap: no CV to judge


def test_cadence_needs_a_regular_enough_rhythm_and_the_threshold_is_exclusive():
    gaps = [1, 3, 1, 3, 1, 3]
    t, reqs = 0.0, [req(0, 0.0, "/p0")]
    for i, g in enumerate(gaps, 1):
        t += g
        reqs.append(req(i, t, f"/p{i}"))
    s = sess(reqs)
    cv = features(s).interarrival_cv
    assert cv is not None and 0.4 < cv < 0.6
    assert cadence(s, cadence_min_requests=3, cadence_cv_max=cv) is None            # cv >= max: no hit
    assert cadence(s, cadence_min_requests=3, cadence_cv_max=cv + 1e-9) is not None
    assert cadence(s, cadence_min_requests=3, cadence_cv_max=0.35) is None


def test_the_cadence_hit_cites_the_first_and_last_request():
    hit = cadence(regular(20))
    assert {r.line for r in hit.lines} == {0, 19} and "20 requests" in hit.detail


def test_features_inter_arrival_statistics():
    f = features(sess([req(0, 0, "/a"), req(1, 1, "/b"), req(2, 4, "/c")]))      # gaps 1 and 3
    assert f.interarrival_median_s == 2.0
    assert f.interarrival_cv == pytest.approx(0.5)             # pstdev 1 / mean 2
    one = features(sess([req(0, 0, "/a"), req(1, 7, "/b")]))
    assert one.interarrival_median_s == 7.0 and one.interarrival_cv is None
    alone = features(sess([req(0, 0, "/a")]))
    assert alone.interarrival_median_s is None and alone.interarrival_cv is None
    simultaneous = features(sess([req(0, 0, "/a"), req(1, 0, "/b"), req(2, 0, "/c")]))
    assert simultaneous.interarrival_cv is None                 # mean 0: no ratio


# --- F-C141-4: campaigns and sessions ------------------------------------------------------


def test_a_campaign_needs_the_same_payload_from_at_least_two_ips():
    one_ip = [sess([req(1, 0, "/x", SQLI, ip="192.0.2.1")]), sess([req(2, 5000, "/x", SQLI, ip="192.0.2.1")])]
    assert campaigns(one_ip) == []
    two_ips = [sess([req(1, 0, "/x", SQLI, ip="192.0.2.1")]), sess([req(2, 5, "/x", SQLI, ip="192.0.2.2")])]
    [c] = campaigns(two_ips)
    assert c.client_ips == ["192.0.2.1", "192.0.2.2"] and c.family == c.fingerprint.split(":", 1)[0]
    assert len(c.session_ids) == 2


@pytest.mark.parametrize(("gap", "sessions"), [(1800.0, 1), (1800.001, 2)])
def test_the_session_gap_is_inclusive(gap, sessions):
    reqs = [req(1, 0, "/a"), req(2, gap, "/b")]
    assert len(sessionize(reqs, RetroConfig())) == sessions


def test_the_session_gap_comes_from_the_config():
    reqs = [req(1, 0, "/a"), req(2, 10, "/b")]
    assert len(sessionize(reqs, RetroConfig(session_gap_s=9.0))) == 2
    assert len(sessionize(reqs, RetroConfig(session_gap_s=10.0))) == 1


# --- F-C141-4: attribution grade -----------------------------------------------------------


def test_a_plain_hostile_session_is_g0_and_behaviour_or_automation_makes_it_g1():
    plain = {"S.inject"}
    assert grade_for(sess([req(1, 0, "/x", SQLI)]), plain)[0] is Grade.G0
    assert grade_for(sess([req(1, 0, "/x", SQLI)]), {"S.inject", "S.pivot"})[0] is Grade.G1
    assert grade_for(sess([req(1, 0, "/x", SQLI)]), {"S.inject", "S.escalate-on-block"})[0] is Grade.G1
    assert grade_for(sess([req(1, 0, "/x", SQLI)]), {"S.inject", "S.cadence"})[0] is Grade.G1
    assert grade_for(sess([req(1, 0, "/x", SQLI, ua="python-requests/2.31")]), plain)[0] is Grade.G1
    assert grade_for(sess([req(1, 0, "/x", SQLI)]), {"S.inject", "S.silent-200"})[0] is Grade.G0


def test_the_verdict_table():
    assert verdict_for({"S.inject", "S.pivot"}) is Verdict.ESCALATE
    assert verdict_for({"S.debug-probe", "S.escalate-on-block"}) is Verdict.ESCALATE
    assert verdict_for({"S.inject"}) is Verdict.REVIEW
    assert verdict_for({"S.launder"}) is Verdict.REVIEW
    assert verdict_for({"S.pivot"}) is Verdict.CLEAR
    assert verdict_for(set()) is Verdict.CLEAR
