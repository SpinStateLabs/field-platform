"""The calibration sweep runs end to end. Synthetic data proves the plumbing, not the thresholds."""

import pytest

from agent_incident_retro.calibrate import sweep
from agent_incident_retro.synth import AGENT_A_IP, AGENT_B_IP, SCANNER_IP, generate


def test_sweep_scores_labelled_clients_over_a_grid(tmp_path):
    log = tmp_path / "synth.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    labels = {AGENT_A_IP: "rogue", AGENT_B_IP: "rogue", SCANNER_IP: "rogue"}
    labels.update({f"192.0.2.{100 + h}": "benign" for h in range(30)})
    grid = {"pivot_window_s": [60.0, 300.0], "cadence_min_requests": [20]}
    points = sweep([log], labels, grid)
    assert len(points) == 2
    for p in points:
        assert p.tp + p.fn == 3 and p.tp + p.fp + p.fn + p.tn == 33
        assert p.fp == 0  # the humans are CLEAR at every point of this grid
    assert points[1].tp == 3  # defaults catch all three synthetic rogues


def test_sweep_refuses_unknown_labels(tmp_path):
    with pytest.raises(ValueError):
        sweep([tmp_path / "x"], {"1.2.3.4": "maybe"})


def test_labels_are_normalised_and_validated(tmp_path):
    log = tmp_path / "x.log"
    log.write_text(generate(seed=7), encoding="utf-8")
    pts = sweep([log], {"2001:DB8:0:0:0:0:0:1": "rogue"}, {"pivot_window_s": [300.0]})
    assert pts[0].fn == 1  # absent from the logs: a miss, and canonicalisation did not raise
    with pytest.raises(ValueError):
        sweep([log], {})
    with pytest.raises(ValueError):
        sweep([log], {"1.2.3.4": ["rogue"]})
