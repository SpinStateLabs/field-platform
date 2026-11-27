"""A declared manifest value too long for its detail line is cut at 120 characters and ends in an ellipsis, also when
the value holds runs of spaces that the line collapses."""
import pytest

from compliance_crosswalk.engine import evaluate


def detail(value: str) -> str:
    report = evaluate({"identity": {"principal": value}})
    return next(c.declared_detail for c in report.controls if c.manifest_path == "identity.principal")


@pytest.mark.parametrize("gap", [" ", "  ", " " * 40], ids=["one", "two", "forty"])
def test_a_long_declared_value_is_cut_to_120_characters_and_marked(gap):
    text = detail("Ann" + gap + "Lee " + "z" * 300)
    assert text.startswith("identity.principal = 'Ann Lee zzz")
    assert len(text) == 120 and text.endswith("…")


def test_a_short_declared_value_is_whole_and_unmarked():
    assert detail("Ann  Lee") == "identity.principal = 'Ann Lee'"


KEPT_ID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"          # made up, the shape of the platform's ids


@pytest.mark.parametrize("kept", range(15, len(KEPT_ID)))
def test_the_ellipsis_follows_directly_what_the_cut_keeps_of_an_id(kept):
    printed_before = "identity.principal = 'a b "                       # the run of spaces printed as one
    value = "a  b " + "z" * (119 - kept - len(printed_before) - 1) + " " + KEPT_ID + " end"
    text = detail(value)
    assert len(text) == 120 and text.endswith(" " + KEPT_ID[:kept] + "\u2026")
