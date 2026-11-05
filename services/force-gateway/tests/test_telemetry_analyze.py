"""S8-24-style direct pins (S8-28) for force_gateway.telemetry.analyze: one case per marker, current
behaviour only. A regex bug found while pinning is recorded in the PR and in a comment here, not fixed
(the card says no engine change)."""

from __future__ import annotations

import pytest

from force_gateway import telemetry
from force_gateway.telemetry import METHOD_LABEL, analyze


def n(text, field):
    return getattr(analyze(text), field)


# --- confidence tags ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    ("**HIGH**", 1), ("**MEDIUM**", 1), ("**LOW**", 1),
    ("[HIGH]", 1), ("[MEDIUM]", 1), ("[LOW]", 1),
    ("**HIGH** and [LOW] and [MEDIUM]", 3),
    ("**HIGH**[LOW]", 2),
    ("HIGH", 0), ("HIGHER", 0), ("HIGH confidence", 0), ("**HIGHER**", 0), ("[HIGHER]", 0),
    ("[high]", 0), ("**High**", 0), ("*HIGH*", 0), ("(HIGH)", 0), ("**HIGH]", 0), ("[HIGH**", 0),
    ("**HIGH** and [HIGH] and HIGH and HIGHER", 2),
])
def test_confidence_tags_count_bold_and_bracket_forms_only(text, want):
    r = analyze(text)
    assert r.confidence_tags == want
    assert r.has_confidence_tags is (want > 0)


# --- corrections -------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Correction: the figure is 5", "CORRECTION: x", "that is incorrect", "That is incorrect.",
    "the premise is wrong", "The premise is flawed", "the premise is false",
    "I need to correct this", "this is not correct", "This is not accurate",
])
def test_each_correction_phrase_counts_once(text):
    assert n(text, "corrections") == 1


def test_that_apostrophe_s_incorrect_is_not_counted_as_written():
    """REGEX BUG, pinned not fixed: the pattern is ``that (is|'s) incorrect`` so the alternative needs a
    space before the apostrophe (``that 's incorrect``); the natural ``that's incorrect`` does not match."""
    assert n("that's incorrect", "corrections") == 0
    assert n("that 's incorrect", "corrections") == 1


@pytest.mark.parametrize("text", ["incorrect", "the premise is fine", "I corrected it", "not correct", "correction"])
def test_non_matches_for_corrections(text):
    assert n(text, "corrections") == 0


def test_corrections_are_counted_per_occurrence():
    assert n("Correction: a. Correction: b. that is incorrect", "corrections") == 3


# --- flattery ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Great question", "great question!", "Excellent question", "I'd be happy to help", "Happy to help",
    "Hope this helps", "Certainly!", "Let me know if you need more",
])
def test_each_flattery_phrase_counts_and_unclean(text):
    r = analyze(text)
    assert r.flattery_hits >= 1 and r.clean_of_flattery is False


@pytest.mark.parametrize("text", ["Hopefully this helps", "certainly", "Certainly?", "a great answer",
                                  "happy with it", "let me know"])
def test_flattery_non_matches_stay_clean(text):
    r = analyze(text)
    assert r.flattery_hits == 0 and r.clean_of_flattery is True


def test_flattery_hits_are_counted_per_non_overlapping_match():
    # "I'd be happy to help" is ONE hit: "i'd be happy to" consumes the words "happy to", so "happy to help"
    # cannot also match there.
    assert n("Great question! I'd be happy to help. Hope this helps.", "flattery_hits") == 3
    assert n("Great question. Great question.", "flattery_hits") == 2


# --- chain-of-thought structure ----------------------------------------------------------------------

FULL = "ASSUMPTIONS:\n- a\nREASONING:\n1. b\nCONCLUSION:\nc"


def test_cot_structure_true_when_all_three_start_a_line():
    assert analyze(FULL).cot_structure is True
    assert analyze("intro\n" + FULL).cot_structure is True


@pytest.mark.parametrize("text", [
    "ASSUMPTIONS:\nREASONING:",                                   # no CONCLUSION
    "REASONING:\nCONCLUSION:",                                    # no ASSUMPTIONS
    "ASSUMPTIONS:\nCONCLUSION:",                                  # no REASONING
    "x ASSUMPTIONS:\nREASONING:\nCONCLUSION:",                    # one marker mid-line
    "ASSUMPTIONS:\nREASONING:\nso CONCLUSION: c",
    " ASSUMPTIONS:\nREASONING:\nCONCLUSION:",                     # leading space is not a line start
    "assumptions:\nreasoning:\nconclusion:",                      # case-sensitive
    "ASSUMPTIONS\nREASONING\nCONCLUSION",                         # colon required
    "",
])
def test_cot_structure_false_otherwise(text):
    assert analyze(text).cot_structure is False


# --- objections and source honesty -------------------------------------------------------------------

@pytest.mark.parametrize("text, want", [
    ("Objection: x", 1), ("objections", 1), ("failure condition", 1), ("Failure mode", 1),
    ("failure scenario", 1), ("failure modes", 1), ("would break", 1), ("This would break here", 1),
    ("objection and objection", 2), ("failure", 0), ("it will break", 0), ("rejection", 0),
])
def test_objection_markers(text, want):
    assert n(text, "objection_markers") == want


@pytest.mark.parametrize("text, want", [
    ("not in source", 1), ("NOT IN SOURCE", 1), ("I don't know", 1), ("general knowledge", 1),
    ("General Knowledge", 1), ("training data", 1), ("not in source, training data", 2),
    ("training  data", 0), ("I do not know", 0), ("in the source", 0),
])
def test_source_honesty_markers(text, want):
    assert n(text, "source_honesty_markers") == want


# --- empty and the method label ----------------------------------------------------------------------

def test_empty_text_is_all_zero_and_clean():
    r = analyze("")
    assert (r.confidence_tags, r.has_confidence_tags, r.corrections, r.flattery_hits, r.cot_structure,
            r.objection_markers, r.source_honesty_markers) == (0, False, 0, 0, False, 0, 0)
    assert r.clean_of_flattery is True


def test_the_method_label_rides_every_report():
    assert analyze("").method == analyze(FULL).method == METHOD_LABEL
    assert "regex heuristic" in METHOD_LABEL and "no LLM" in METHOD_LABEL


def test_the_report_fields():
    assert set(analyze("").model_dump()) == {
        "confidence_tags", "has_confidence_tags", "corrections", "flattery_hits", "clean_of_flattery",
        "cot_structure", "objection_markers", "source_honesty_markers", "method"}


def test_a_full_protocol_shaped_answer_scores_every_marker():
    text = ("Objection: this would break.\nASSUMPTIONS:\n- a\nREASONING:\n1. b **HIGH**\nCONCLUSION:\nc [LOW]\n"
            "Correction: x. general knowledge. Great question")
    r = analyze(text)
    assert (r.confidence_tags, r.corrections, r.flattery_hits, r.cot_structure, r.objection_markers,
            r.source_honesty_markers) == (2, 1, 1, True, 2, 1)
