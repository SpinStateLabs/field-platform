"""S7-8: shown_label applies the same 40+ character unbroken-token rule as shown_id / printable_id (PG0-CORE-R2-03).

A caller-chosen label (an event type, the agent id of the refused route) is written into an operator.refused ledger row.
shown_label refused the key prefix but let a 40+ character [A-Za-z0-9_-] token through (a key pasted with its prefix
stripped, a 64-hex hash), while its sibling shown_id never echoes one. Decision (coordinator delegated to the author's
recommendation): one rule. No event type or agent id in the repository is a 40+ character unbroken string, so no real
label is hidden by it; a dotted label is not 'unbroken' (the dot is outside the token charset) and is kept."""

import pytest

from field_core import operator_health as oh

TOKEN_43 = "Tq9xWv3LkR7bN2mYc8HdZp4sGf6uJe1aXo5iKt0QwEr"


@pytest.mark.parametrize("bad", ["a" * 40, "a" * 64, "0123456789abcdef" * 4, TOKEN_43, "A1_-" * 10,
                                 "ab-" * 14])
def test_a_40_plus_character_unbroken_token_is_not_shown(bad):
    assert oh.shown_label(bad) == oh.NOT_SHOWN


@pytest.mark.parametrize("ok", ["kill.agent.v2", "x3-check", "kill.agent", "a" * 39, "a" * 20 + "." + "b" * 20,
                                ("a" * 31 + ".") * 2, "ssl-timekeeping-agent", "operator.refused"])
def test_a_short_or_broken_label_is_kept(ok):
    assert oh.shown_label(ok) == ok


def test_a_64_character_dotted_label_is_kept():
    label = ("a" * 7 + ".") * 8
    assert len(label) == 64 and oh.shown_label(label) == label


def test_the_39_40_boundary_is_exact():
    assert oh.shown_label("a" * 39) == "a" * 39
    assert oh.shown_label("a" * 40) == oh.NOT_SHOWN


def test_the_existing_rules_are_unchanged():
    assert oh.shown_label(None) is None
    for bad in (7, b"x", "", "a b", "x" * 65, oh.KEY_PREFIX + "abc"):
        assert oh.shown_label(bad) == oh.NOT_SHOWN


def test_shown_label_and_shown_id_agree_on_the_token_rule():
    for value in ("a" * 40, TOKEN_43, "a" * 39, "don"):
        assert (oh.shown_label(value) == oh.NOT_SHOWN) == (oh.shown_id(value) == oh.NOT_SHOWN)
