"""S11-12: the delegation-authority README states no estate fact about FIELD_DOA_ROSTER.

This repository is public (architect ruling 2026-11-06 on PR 819 condition 2, applied in
docs/capstone-evidence/v2-one-liners.md): `FIELD_DOA_ROSTER` is unset by default, and whether an estate sets it is
recorded outside this repository and is Declared here. The README once said, in three places, that it was unset "on
both estates today", set "on both the GB10 and Fly estates as of 2026-10-23", and not armed "on the estates until
arming step A3": three claims that cannot all be true and that no test here can verify.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"
TEXT = README.read_text(encoding="utf-8")

ESTATE_FACT_PATTERNS = [
    r"on both estates",
    r"both estates",
    r"both the GB10 and Fly",
    r"(set|unset|armed|deployed)[^.\n]{0,40}\bestates?\b[^.\n]{0,40}(today|as of|2026-)",
    r"as of 2026-10-23",
    r"deployed on both estates",
    r"stays \*?Declared\*? on the estates",
    r"until arming step A3",
]



@pytest.mark.parametrize("pattern", ESTATE_FACT_PATTERNS)
def test_the_readme_contains_no_estate_fact_phrase(pattern):
    hit = re.search(pattern, TEXT, re.I)
    assert hit is None, f"README states an estate fact: {hit.group(0)!r}"


def test_the_readme_says_it_is_unset_by_default_and_the_estate_state_is_declared_elsewhere():
    assert "Leave it unset" in TEXT, "the roster section no longer says it may be left unset"
    unset = [ln for ln in TEXT.splitlines() if "FIELD_DOA_ROSTER" in ln and "unset" in ln]
    assert unset, "the README no longer says FIELD_DOA_ROSTER is unset by default"
    assert TEXT.count("recorded outside this repository") >= 3   # the roster section, the Enforced table row, LIMITS
    assert "Declared" in TEXT


def test_no_dated_arming_claim_remains():
    """A dated statement about arming or setting a roster is an estate fact whatever its wording or line."""
    for pattern in (r"\b(armed|arming)\b[^.\n]{0,80}\b2026-\d\d-\d\d", r"\bset\b[^.\n]{0,80}\bas of 2026"):
        assert re.search(pattern, TEXT, re.I) is None, pattern
