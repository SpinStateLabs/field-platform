"""S2-14: curly and straight apostrophes count the same; the confidence forms are pinned.

The patterns hold the ASCII apostrophe only, and models write U+2019, so "I’d be happy to" went uncounted and
clean_of_flattery stayed True. The text is normalised on a local copy before matching."""

import pytest

from force_gateway.telemetry import analyze


@pytest.mark.parametrize("phrase", ["I'd be happy to", "I’d be happy to", "I‘d be happy to"])
def test_flattery_counts_the_same_with_any_apostrophe(phrase):
    r = analyze(f"{phrase} look.")
    assert r.flattery_hits == 1 and r.clean_of_flattery is False


@pytest.mark.parametrize("phrase", ["I don't know", "I don’t know"])
def test_source_honesty_counts_the_same_with_any_apostrophe(phrase):
    assert analyze(f"{phrase} the figure.").source_honesty_markers == 1


@pytest.mark.parametrize("text", ["Great question", "Excellent question", "Happy to help", "Hope this helps",
                                  "Certainly!", "Let me know if"])
def test_each_flattery_phrase_counts_once(text):
    assert analyze(text).flattery_hits == 1


def test_clean_text_is_clean():
    r = analyze("The figure is 4.")
    assert r.flattery_hits == 0 and r.clean_of_flattery is True


@pytest.mark.parametrize("text, n", [("**HIGH** and [LOW]", 2), ("**MEDIUM**", 1), ("[MEDIUM]", 1),
                                     ("HIGH — directly verified", 0), ("HIGH: x", 0), ("**high**", 0)])
def test_confidence_tags_are_bold_or_bracketed_uppercase_only(text, n):
    r = analyze(text)
    assert r.confidence_tags == n and r.has_confidence_tags is (n > 0)


def test_the_text_is_normalised_on_a_copy_only():
    text = "I’d be happy to."
    analyze(text)
    assert text == "I’d be happy to."
