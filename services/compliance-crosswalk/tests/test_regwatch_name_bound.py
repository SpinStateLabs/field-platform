"""S9-30 (the regwatch half): `--fetched-by` is bounded.

`regwatch._named_human` checked blank, control, format and no-alphanumeric but never length, and `check_file` stores the name as
`via = "manual:<NAME>"`, in the source record, and in the flag reason. A 1 MB name therefore landed in the stale-flags JSON, every later
GET /staleness and the evidence pack. A name is now at most MAX_NAME_CHARS (200, the kill-switch operator bound) characters after
stripping: exactly that is accepted, one more is a `ManualFileRefused` (the CLI turns it into exit 2) with the same style of message,
the name is not echoed, and nothing is written. The character rules are unchanged. (The reviewer half, `staleness._plain_reviewer_name`,
is open PR 694's MAX_REVIEWER_CHARS = 200.)"""

import pytest

from compliance_crosswalk import regwatch
from compliance_crosswalk.regwatch import ManualFileRefused, _named_human
from compliance_crosswalk.staleness import StaleStore

LIMIT = regwatch.MAX_NAME_CHARS


def test_the_limit_is_200():
    assert LIMIT == 200


def test_exactly_the_limit_is_accepted_and_one_more_is_refused():
    assert _named_human("a" * LIMIT) == "a" * LIMIT
    with pytest.raises(ManualFileRefused, match=f"{LIMIT} characters") as caught:
        _named_human("a" * (LIMIT + 1))
    assert "a" * 20 not in str(caught.value)             # the name is never echoed


def test_the_bound_counts_the_stripped_name_not_the_padding():
    assert _named_human("  " + "a" * LIMIT + " \n") == "a" * LIMIT
    with pytest.raises(ManualFileRefused):
        _named_human("  " + "a" * (LIMIT + 1) + "  ")


def test_a_megabyte_name_is_refused():
    with pytest.raises(ManualFileRefused):
        _named_human("b" * (1024 * 1024))


@pytest.mark.parametrize("name", ["Don H", "Ana María", "李雷", "x", "Dr. J. R. R. O'Neil-Smith III"])
def test_ordinary_names_still_pass(name):
    assert _named_human(name) == name


@pytest.mark.parametrize("bad", ["", "   ", "\t", "ab\ncd", "ab\x00cd", "ab​cd", "!!!", "• •"],
                         ids=["empty", "blank", "tab", "newline", "nul", "zero-width", "punctuation", "bullets"])
def test_the_character_rules_are_unchanged(bad):
    with pytest.raises(ManualFileRefused):
        _named_human(bad)


def test_an_overlong_name_writes_nothing_through_check_file(tmp_path):
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><html><body>x</body></html>", encoding="utf-8")
    store = StaleStore(tmp_path / "flags.json")
    framework = next(iter(regwatch.inventory()))
    with pytest.raises(ManualFileRefused, match="characters"):
        regwatch.check_file(framework, page, "n" * (LIMIT + 1), store=store)
    assert not (tmp_path / "flags.json").exists()
    assert store.active() == []
