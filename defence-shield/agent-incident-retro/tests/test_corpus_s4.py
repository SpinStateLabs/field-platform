"""The synthetic labelled corpus is deterministic and the detector scores it as constructed.

Regression only: these numbers describe the generator, not real traffic."""

from agent_incident_retro.calibrate import sweep
from agent_incident_retro.corpus import COUNTS, generate_corpus


def test_corpus_is_deterministic_and_labelled_by_class():
    log, labels = generate_corpus(seed=11)
    assert (log, labels) == generate_corpus(seed=11)
    assert log != generate_corpus(seed=12)[0]
    rogue = COUNTS["fast"] + COUNTS["slow"] + COUNTS["patient"] + COUNTS["scanner"] + 3 * COUNTS["campaign"]
    assert sum(v == "rogue" for v in labels.values()) == rogue
    assert sum(v == "benign" for v in labels.values()) == COUNTS["human"] + COUNTS["mirror"] + COUNTS["archive"]


def test_default_thresholds_behaviour_on_the_corpus(tmp_path):
    log, labels = generate_corpus(seed=11)
    path = tmp_path / "corpus.log"
    path.write_text(log, encoding="utf-8")
    default = sweep([path], labels, {"pivot_window_s": [300.0]})[0]
    wide = sweep([path], labels, {"pivot_window_s": [900.0]})[0]
    assert default.absent_benign == 0 and default.tp + default.fn == sum(v == "rogue" for v in labels.values())
    # humans and regular-cadence mirrors are not flagged; archive fetchers replaying a payload URL ARE (S.launder
    # REVIEW, by design in synth.py): the corpus labels them benign, so they are the measured false positives.
    assert default.fp == COUNTS["archive"] * 1
    assert default.fn == 0  # any hostile payload request is REVIEW at least, whatever the pivot window
    assert wide.tp >= default.tp
