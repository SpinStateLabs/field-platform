"""C-1165 (SPEC R-D4): the SYNTHETIC calibration corpus and what the detector does with it today.

``corpus/calibration.log`` holds 15 made-up actors whose ground truth (``rogue``, ``benign``, ``authorized``) is
written in ``corpus/labels.json`` by the generator, never read back from the detector. These tests pin, by counts, how
the detector's verdicts line up with that truth at the default thresholds and at the changed thresholds that matter,
so a change to a threshold or a clause turns a test red and the change is a decision. They are a characterisation of
v0.1.1, not a claim that the thresholds are right: the numbers below are what makes "uncalibrated" measurable.

Nothing here is real traffic. Every address is an RFC 5737 documentation address."""

from __future__ import annotations

import importlib.util
import ipaddress
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from agent_incident_retro.engine import run_retro
from agent_incident_retro.models import RetroConfig, Verdict

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
LOG = CORPUS / "calibration.log"
LABELS = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
ACTORS = LABELS["actors"]
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def _scan(**cfg):
    return run_retro([LOG], fmt="clf", config=RetroConfig(**cfg))


def _verdicts(result):
    """ip -> the set of verdicts its findings carry; no finding at all means the actor was CLEAR."""
    out: dict[str, set] = {ip: set() for ip in ACTORS}
    for f in result.findings:
        out[f.client_ip].add(f.verdict)
    return out


def _flagged(v):  # REVIEW or ESCALATE: a person would be asked to look
    return bool(v & {Verdict.REVIEW, Verdict.ESCALATE})


def _ips(truth):
    return sorted(ip for ip, a in ACTORS.items() if a["truth"] == truth)


# ---- the corpus is synthetic, and the committed files are what the generator writes ------------------------------


def test_the_labels_and_the_readme_say_the_corpus_is_synthetic():
    assert LABELS["synthetic"] is True
    readme = (CORPUS / "README.md").read_text(encoding="utf-8")
    assert "synthetic" in readme.lower() and "no real traffic" in readme.lower()


def test_every_address_in_the_log_is_a_documentation_address():
    ips = {line.split(" ", 1)[0] for line in LOG.read_text(encoding="utf-8").splitlines() if line}
    assert ips == set(ACTORS)                                              # the labels cover exactly the log
    for ip in ips:
        assert any(ipaddress.ip_address(ip) in net for net in DOC_NETS), ip


def test_the_committed_files_are_what_the_generator_writes():
    spec = importlib.util.spec_from_file_location("make_calibration_corpus", CORPUS / "make_calibration_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    log, labels = mod.build()
    assert log == LOG.read_text(encoding="utf-8")
    assert labels == LABELS


def test_the_corpus_has_the_shape_the_counts_below_assume():
    assert Counter(a["truth"] for a in ACTORS.values()) == {"benign": 6, "rogue": 8, "authorized": 1}
    assert _scan().inputs[0].unparsed == 0 and _scan().requests_total == 103


# ---- how the detector lines up with the truth at the default thresholds -----------------------------------------


def test_no_benign_actor_is_flagged_at_the_default_thresholds():
    v = _verdicts(_scan())
    assert [ip for ip in _ips("benign") if _flagged(v[ip])] == []
    assert _scan().counts["verdicts"]["CLEAR"] == 6


def test_every_rogue_actor_is_flagged_for_review_at_the_default_thresholds():
    v = _verdicts(_scan())
    assert [ip for ip in _ips("rogue") if not _flagged(v[ip])] == []        # recall at REVIEW: 8 of 8


def test_a_monitoring_poller_with_a_fixed_cadence_raises_no_finding():
    """Weak automation (S.cadence) is an attribution marker, not a finding on its own."""
    assert [f for f in _scan().findings if f.client_ip == "192.0.2.20"] == []


def test_only_the_fast_pivot_and_the_unlisted_scanner_reach_escalate_at_the_default_thresholds():
    """The calibration gap in one line: 1 of 8 rogue actors is ESCALATE at the default window."""
    v = _verdicts(_scan())
    assert sorted(ip for ip, vs in v.items() if Verdict.ESCALATE in vs) == ["192.0.2.77", "203.0.113.50"]


def test_the_slow_pivot_is_review_not_escalate_until_the_window_is_widened():
    """203.0.113.51 pivots after 430 s: outside the 300 s default window, inside 900 s."""
    slow = "203.0.113.51"
    assert _verdicts(_scan())[slow] == {Verdict.REVIEW}
    assert _verdicts(_scan(pivot_window_s=900.0))[slow] == {Verdict.ESCALATE}
    assert _verdicts(_scan(pivot_window_s=900.0))["203.0.113.50"] == {Verdict.ESCALATE}   # the fast one stays


def test_widening_the_pivot_window_flags_no_benign_actor_in_this_corpus():
    v = _verdicts(_scan(pivot_window_s=900.0))
    assert [ip for ip in _ips("benign") if _flagged(v[ip])] == []
    assert _scan(pivot_window_s=900.0).counts["verdicts"] == {"ESCALATE": 3, "REVIEW": 10, "AUTHORIZED": 0, "CLEAR": 6}


def test_a_low_and_slow_actor_becomes_five_findings_until_the_session_gap_is_widened():
    """One address, one payload every two hours: each is its own session (the 1800 s gap), so five REVIEW findings
    and no ESCALATE; a gap longer than the interval joins them into one finding. Both are still REVIEW."""
    ip = "203.0.113.90"
    five = [f for f in _scan().findings if f.client_ip == ip]
    assert len(five) == 5 and {f.verdict for f in five} == {Verdict.REVIEW}
    one = [f for f in _scan(session_gap_s=8000.0).findings if f.client_ip == ip]
    assert len(one) == 1 and one[0].verdict is Verdict.REVIEW


def test_three_rotated_addresses_replaying_one_payload_are_linked_as_a_campaign():
    r = _scan()
    assert r.counts["campaigns"] == 3
    rotated = [f for f in r.findings if f.client_ip.startswith("198.51.100.1")]
    assert len(rotated) == 3 and all("S.campaign" in {c.clause for c in f.clauses} for f in rotated)


def test_the_spoofed_marker_is_grade_g2_a_claim_not_proof():
    spoof = [f for f in _scan().findings if f.client_ip == "203.0.113.77"]
    assert len(spoof) == 1 and spoof[0].grade.value == "G2" and spoof[0].verdict is Verdict.REVIEW


# ---- an authorised actor is listed, never suppressed ----------------------------------------------------------------


def test_the_authorised_scanner_is_escalate_until_listed_then_authorized_and_never_clear():
    ip = "192.0.2.77"
    assert _verdicts(_scan())[ip] == {Verdict.ESCALATE}
    listed = _scan(allow_ips=[ip])
    assert _verdicts(listed)[ip] == {Verdict.AUTHORIZED}
    assert any(f.client_ip == ip for f in listed.findings)                  # still reported
    assert listed.counts["verdicts"]["ESCALATE"] == 1                       # only the fast pivot remains


# ---- the counts, so any change of a threshold or clause is visible ----------------------------------------------


def test_the_verdict_counts_at_the_default_thresholds():
    r = _scan()
    assert r.counts["verdicts"] == {"ESCALATE": 2, "REVIEW": 11, "AUTHORIZED": 0, "CLEAR": 6}
    assert r.sessions_total == 19 and r.counts["findings"] == 13


@pytest.mark.parametrize("actor", sorted(ACTORS))
def test_every_labelled_actor_has_a_scenario_text(actor):
    assert ACTORS[actor]["truth"] in {"benign", "rogue", "authorized"} and len(ACTORS[actor]["scenario"]) > 20
