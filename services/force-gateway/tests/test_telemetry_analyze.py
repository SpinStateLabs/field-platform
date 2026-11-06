"""Direct tests for telemetry.analyze, one positive and one negative per marker
(scout proposal S-B1). The correction marker used to need `that 's incorrect`
(a space before the apostrophe), so "That's incorrect." was never counted."""
from __future__ import annotations

import pytest

from force_gateway.telemetry import analyze


@pytest.mark.parametrize("text", [
    "That's incorrect.",
    "That’s incorrect.",
    "That is incorrect.",
    "THAT   IS   INCORRECT",
    "Correction: the figure is 4.",
    "The premise is flawed.",
    "I need to correct this.",
    "This is not accurate.",
])
def test_a_correction_is_counted(text):
    assert analyze(text).corrections == 1


@pytest.mark.parametrize("text", [
    "That is correct.",
    "Thats incorrect",          # no apostrophe, not the protocol phrase
    "the premise is sound",
    "Nothing to fix here.",
])
def test_no_correction_is_counted_when_absent(text):
    assert analyze(text).corrections == 0


def test_two_corrections_count_two():
    assert analyze("That's incorrect. Correction: it is 4.").corrections == 2


def test_confidence_tags_both_forms_and_none():
    r = analyze("x **HIGH** y [LOW] z")
    assert (r.confidence_tags, r.has_confidence_tags) == (2, True)
    r = analyze("HIGH and low, untagged")
    assert (r.confidence_tags, r.has_confidence_tags) == (0, False)


def test_flattery_is_counted_and_clean_text_is_clean():
    r = analyze("Great question! Hope this helps.")
    assert (r.flattery_hits, r.clean_of_flattery) == (2, False)
    r = analyze("The answer is 4.")
    assert (r.flattery_hits, r.clean_of_flattery) == (0, True)


def test_cot_structure_needs_all_three_at_line_start():
    full = "ASSUMPTIONS: a\nREASONING: b\nCONCLUSION: c"
    assert analyze(full).cot_structure is True
    assert analyze("ASSUMPTIONS: a\nREASONING: b").cot_structure is False
    assert analyze("x ASSUMPTIONS: a\nREASONING: b\nCONCLUSION: c").cot_structure is False


def test_objection_markers():
    assert analyze("Objection: it would break. A failure mode.").objection_markers == 3
    assert analyze("All fine.").objection_markers == 0


def test_source_honesty_markers():
    r = analyze("Not in source. I don't know. From general knowledge and training data.")
    assert r.source_honesty_markers == 4
    assert analyze("Fully cited.").source_honesty_markers == 0
