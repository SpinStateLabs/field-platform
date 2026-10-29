"""C-300 (reviewer C-290): `scan` exits 2 only on ESCALATE, so a REVIEW-only log exits 0 (a mutant
`Exit(2 if ESCALATE or REVIEW else 0)` survived the suite), and the S.silent-200 clause's boundaries
(hostile AND 2xx: 200 to 299 inclusive) are pinned."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_incident_retro.clauses import evaluate, s_silent_200
from agent_incident_retro.cli import app
from agent_incident_retro.models import RetroConfig, Verdict
from test_detection_pins_c148 import SQLI, req, sess

runner = CliRunner()
CLF = '203.0.113.5 - - [01/Sep/2026:00:00:{s:02d} +0000] "GET {target} HTTP/1.1" {status} 5 "-" "Mozilla/5.0"\n'


def scan(tmp_path: Path, log_text: str):
    log = tmp_path / "x.log"
    log.write_text(log_text, encoding="utf-8")
    runner.invoke(app, ["keygen", "--out", str(tmp_path / "k"), "--pub", str(tmp_path / "p")])
    return runner.invoke(app, ["scan", str(log), "--out", str(tmp_path / "o"), "--key", str(tmp_path / "k")])


# --- finding 1: only ESCALATE exits 2 ---------------------------------------------------------


@pytest.mark.parametrize("status", [404, 200])
def test_a_review_only_scan_exits_0(tmp_path, status):
    r = scan(tmp_path, CLF.format(s=0, target="/search?" + SQLI, status=status))
    assert "ESCALATE 0 · REVIEW 1" in r.output, r.output       # it really is a REVIEW-only log
    assert r.exit_code == 0, r.output
    assert (tmp_path / "o" / "report.md").exists()


def test_a_review_plus_escalate_scan_still_exits_2(tmp_path):
    text = (CLF.format(s=0, target="/search?q=books", status=200)
            + CLF.format(s=30, target="/search?" + SQLI, status=200))
    r = scan(tmp_path, text)
    assert "ESCALATE 1" in r.output and r.exit_code == 2, r.output


# --- finding 2: S.silent-200 -------------------------------------------------------------------


def hits_for(status):
    return s_silent_200(sess([req(1, 0, "/search", SQLI, status=status)]))


@pytest.mark.parametrize(("status", "fires"), [
    (199, False), (200, True), (204, True), (299, True), (300, False), (302, False), (404, False),
    (500, False)])
def test_silent_200_fires_on_a_hostile_request_answered_2xx_only(status, fires):
    hit = hits_for(status)
    assert (hit is not None) is fires
    if fires:
        assert hit.clause == "S.silent-200"


def test_a_benign_2xx_request_is_not_a_silent_200():
    """Kills `r.is_hostile and ...` -> `or`: a benign 200 would then fire."""
    assert s_silent_200(sess([req(1, 0, "/about", "", status=200), req(2, 5, "/about", "", status=204)])) is None


def test_a_benign_2xx_does_not_join_a_hostile_non_2xx_session():
    assert s_silent_200(sess([req(1, 0, "/about", "", status=200), req(2, 5, "/search", SQLI, status=403)])) is None


def test_silent_200_cites_exactly_the_hostile_2xx_lines():
    s = sess([req(1, 0, "/about", "", status=200),            # benign 2xx
              req(2, 5, "/search", SQLI, status=403),         # hostile, refused
              req(3, 10, "/search", SQLI, status=200),
              req(4, 15, "/search", SQLI, status=204),
              req(5, 20, "/search", SQLI, status=302)])       # hostile, redirected
    hit = s_silent_200(s)
    assert [ref.line for ref in hit.lines] == [3, 4]
    assert hit.detail.startswith("2 hostile request(s) answered 2xx")


def test_the_session_feature_counts_the_same_boundary():
    """`hostile_2xx` (clauses.py features) uses the same range; the clause and the feature agree."""
    for status, expected in [(199, 0), (200, 1), (299, 1), (300, 0)]:
        findings, _, _ = evaluate([sess([req(1, 0, "/search", SQLI, status=status)])], RetroConfig())
        assert findings[0].features.hostile_2xx == expected, status
        assert ("S.silent-200" in {c.clause for c in findings[0].clauses}) is bool(expected), status


def test_silent_200_alone_does_not_escalate_the_verdict():
    findings, _, _ = evaluate([sess([req(1, 0, "/search", SQLI, status=200)])], RetroConfig())
    assert findings[0].verdict is Verdict.REVIEW
