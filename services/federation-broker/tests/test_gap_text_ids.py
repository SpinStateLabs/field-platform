"""A manifest gap quoted in a verdict reason is never cut inside an id."""
import pytest

from federation_broker import engine

TID = "7d3f9a1c-52be-4c08-9e6a-1b2c3d4e5f60"


@pytest.mark.parametrize("kept", range(1, len(TID)))
def test_a_long_gap_is_cut_before_the_id(kept):
    before = "z" * (200 - kept)
    gap = before + TID + " end"
    assert engine._bounded_gaps([gap]) == [f"{before}...[truncated {len(gap) - len(before)} chars]"]
