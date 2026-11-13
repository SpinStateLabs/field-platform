"""Regression-only: the larger synthetic corpus runs through the sweep and pins the defaults' behaviour.
It is NOT calibration (todo 287); real labelled logs are still required."""

from agent_incident_retro.calibrate import sweep
from agent_incident_retro.synth_corpus import generate_corpus


def test_corpus_is_deterministic_and_labelled():
    a, la = generate_corpus(seed=11)
    b, lb = generate_corpus(seed=11)
    assert a == b and la == lb
    assert generate_corpus(seed=12)[0] != a
    assert sum(v == "rogue" for v in la.values()) == 20 and sum(v == "benign" for v in la.values()) == 300


def test_defaults_on_the_corpus_are_pinned(tmp_path):
    text, labels = generate_corpus(seed=11)
    log = tmp_path / "corpus.log"
    log.write_text(text, encoding="utf-8")
    p = sweep([log], labels, {"pivot_window_s": [300.0], "session_gap_s": [1800.0],
                              "cadence_min_requests": [20], "cadence_cv_max": [0.35]})[0]
    assert (p.tp, p.fp, p.fn, p.tn) == (20, 0, 0, 300)


def test_flagged_set_is_insensitive_to_the_four_thresholds(tmp_path):
    """Pins a limitation the sweep inherits, not a goal: FLAGGED = ESCALATE or REVIEW, and any hostile
    request already yields REVIEW (clauses.verdict_for), so the thresholds only move ESCALATE vs REVIEW.
    If calibrate ever scores ESCALATE separately this test must change with it."""
    text, labels = generate_corpus(seed=11)
    log = tmp_path / "corpus.log"
    log.write_text(text, encoding="utf-8")
    grid = {"pivot_window_s": [15.0, 300.0], "cadence_min_requests": [10, 60], "cadence_cv_max": [0.05, 0.5]}
    pts = sweep([log], labels, grid)
    assert len(pts) == 8
    assert {(p.tp, p.fp, p.fn, p.tn) for p in pts} == {(20, 0, 0, 300)}
