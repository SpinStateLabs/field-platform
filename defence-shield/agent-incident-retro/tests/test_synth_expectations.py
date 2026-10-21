"""The synthetic fixture pins the detector's behaviour: each labelled actor
must get the verdict and grade the SPEC promises."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_incident_retro.engine import run_retro
from agent_incident_retro.models import Grade, RetroConfig, Verdict
from agent_incident_retro.synth import (
    AGENT_A_IP,
    AGENT_B_IP,
    ARCHIVE_IP,
    ROTATED_IPS,
    SCANNER_IP,
    generate,
)


@pytest.fixture
def scanned(tmp_path: Path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    return run_retro([log], fmt="clf"), log


def _by_ip(result, ip):
    return [f for f in result.findings if f.client_ip == ip]


def test_two_malformed_lines_counted_not_fatal(scanned):
    result, _ = scanned
    assert result.inputs[0].unparsed == 2
    assert result.inputs[0].parsed > 100


def test_humans_are_clear(scanned):
    result, _ = scanned
    human_ips = {f"192.0.2.{100 + h}" for h in range(30)}
    assert not [f for f in result.findings if f.client_ip in human_ips]
    assert result.counts["verdicts"]["CLEAR"] >= 30


def test_agent_a_escalate_g1_with_pivot_and_escalate_on_block(scanned):
    result, _ = scanned
    hits = _by_ip(result, AGENT_A_IP)
    assert len(hits) == 1
    f = hits[0]
    assert f.verdict is Verdict.ESCALATE
    assert f.grade is Grade.G1  # browser UA, no marker
    clauses = {c.clause for c in f.clauses}
    assert {"S.pivot", "S.escalate-on-block", "S.inject", "S.debug-probe"} <= clauses
    assert "S.silent-200" in clauses  # some payloads answered 2xx


def test_agent_b_review_g2_spoofed_marker(scanned):
    result, _ = scanned
    hits = _by_ip(result, AGENT_B_IP)
    assert len(hits) == 1
    f = hits[0]
    assert f.verdict is Verdict.REVIEW  # payloads but no escalation sequence
    assert f.grade is Grade.G2
    assert f.markers  # a self-declared marker was observed
    assert "spoofable" in f.grade_basis


def test_rotated_ips_form_one_union_campaign(scanned):
    result, _ = scanned
    union_campaigns = [c for c in result.campaigns if set(ROTATED_IPS) <= set(c.client_ips)]
    assert len(union_campaigns) == 1
    for ip in ROTATED_IPS:
        hits = _by_ip(result, ip)
        assert hits and hits[0].verdict is Verdict.REVIEW
        assert hits[0].campaign_ids


def test_archive_fetcher_is_launder_review(scanned):
    result, _ = scanned
    hits = _by_ip(result, ARCHIVE_IP)
    assert len(hits) == 1
    assert hits[0].verdict is Verdict.REVIEW
    assert any(c.clause == "S.launder" for c in hits[0].clauses)


def test_scanner_escalates_unless_allowlisted(scanned):
    result, log = scanned
    assert _by_ip(result, SCANNER_IP) and _by_ip(result, SCANNER_IP)[0].verdict is Verdict.ESCALATE

    allow = run_retro([log], fmt="clf", config=RetroConfig(allow_ips=[SCANNER_IP]))
    hit = [f for f in allow.findings if f.client_ip == SCANNER_IP]
    assert hit and hit[0].verdict is Verdict.AUTHORIZED
    assert hit[0].authorized_by  # listed, not suppressed
    assert hit[0].clauses  # clauses still recorded


def test_g3_is_never_emitted(scanned):
    result, _ = scanned
    assert all(f.grade is not Grade.G3 for f in result.findings)


def test_slow_and_low_evades_pivot_a_known_limit(tmp_path: Path):
    """Spacing the escalation beyond the pivot window is a documented miss:
    the severity clause still fires (REVIEW) but the A6 behaviour does not."""
    from agent_incident_retro.synth import _clf

    t0 = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    ua = "slowbot/1.0"
    lines = [
        _clf("203.0.113.90", t0, "GET", "/search?q=records", 200, 500, ua),
        # tamper 20 minutes later — far outside the 300 s pivot window
        _clf("203.0.113.90", t0.replace(minute=25), "GET", "/search?q=%27%20OR%20%271%27%3D%271", 200, 500, ua),
    ]
    log = tmp_path / "slow.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = run_retro([log], fmt="clf")
    f = [x for x in result.findings if x.client_ip == "203.0.113.90"][0]
    assert f.verdict is Verdict.REVIEW  # payload seen
    assert {c.clause for c in f.clauses}.isdisjoint({"S.pivot", "S.escalate-on-block"})
