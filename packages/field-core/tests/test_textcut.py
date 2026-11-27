"""``field_core.textcut.cut`` and the ledger-note cleaning that uses it."""
import pytest

from field_core.ledger_context import MAX_ID_CHARS, MAX_NOTE_CHARS, correlation_context, ledger_note
from field_core.textcut import cut

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"          # made up, the shape field_core.delegation mints
KEPT = range(1, len(TID))                             # how much of the id lies before the limit
LIMITS = [200, 300, 500]


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize("kept", KEPT)
def test_a_limit_inside_an_id_cuts_before_it(limit, kept):
    before = "z" * (limit - kept)
    assert cut(before + TID + " end", limit) == before


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize("kept", [0, 36, 37])
def test_a_limit_beside_an_id_is_a_plain_cut(limit, kept):
    text = "z" * (limit - kept) + TID + " and more"
    assert cut(text, limit) == text[:limit]


@pytest.mark.parametrize("text", ["z" * 400, "20261127-0249 " * 30, "cafebabe-fed " * 30, ("7d3f9a1c-52be " * 30)])
def test_text_without_a_whole_id_across_the_limit_is_a_plain_cut(text):
    for limit in (0, 1, 13, 200, 300):
        assert cut(text, limit) == text[:limit]


def test_a_short_text_is_returned_as_it_is():
    assert cut(TID, 36) == TID and cut("", 0) == ""


def test_a_text_that_begins_with_an_id_longer_than_the_limit_becomes_empty():
    assert cut(TID + " end", 20) == ""


def test_adjacent_ids_keep_the_ones_that_fit():
    assert cut(TID + TID + "end", 50) == TID


def test_overlapping_runs_are_all_left_whole_or_out():
    chain = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"     # a second run starts inside the first
    assert cut(chain, 40) == ""


@pytest.mark.parametrize("kept", KEPT)
def test_a_ledger_note_is_cut_after_collapsing_and_never_inside_an_id(kept):
    before = "a b " + "z" * (MAX_NOTE_CHARS - kept - 4)
    note = "a \t\n b " + before[4:] + TID + " end"
    assert ledger_note(note) == before


@pytest.mark.parametrize("kept", KEPT)
def test_a_correlation_value_is_never_cut_inside_an_id(kept):
    before = "z" * (MAX_ID_CHARS - kept)
    assert correlation_context({"session_id": before + TID}) == {"session_id": before}
