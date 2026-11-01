"""Reviewer Q-69 (Lane 7, 20261101-1535-reviewer-q69.md) conditions on the trailer check of the commit-identity guard
(C-661, head 1ff8469), one section per finding; each test was red on 1ff8469 before its fix.

F-Q69-4: on a git without the ``%(trailers:...)`` placeholder the literal placeholder lands in the sixth column and the
check passed silently. Now that is exit 2 with fixed text. Mutant Q4 the placeholder check dropped.
"""
from __future__ import annotations

import pytest

from test_check_commit_identity_c564 import BAD_ADDR, _run, cci, line, repo   # noqa: F401

PLACEHOLDER = "%(trailers:only,unfold,separator=%x1e)"


# ---- F-Q69-4 ----------------------------------------------------------------------------------------------------------
def test_an_unexpanded_trailers_placeholder_is_an_error_not_a_pass():
    with pytest.raises(ValueError, match="placeholder"):
        cci.parse_log(line() + "\x1f" + PLACEHOLDER)
    with pytest.raises(ValueError, match="placeholder"):
        cci.parse_log(line() + "\x1f" + "%(trailers)")


def test_the_placeholder_error_is_exit_2_with_fixed_text_through_the_cli(repo):
    p = _run(repo, "--stdin", stdin=line(an=BAD_ADDR) + "\x1f" + PLACEHOLDER)
    assert p.returncode == 2 and "placeholder" in p.stderr and "clean" not in p.stdout
    assert not any(BAD_ADDR[i:i + 6] in p.stdout + p.stderr for i in range(len(BAD_ADDR) - 5))


def test_a_real_trailer_that_merely_mentions_the_placeholder_text_is_still_read():
    assert cci.parse_log(line() + "\x1fNote: see %(trailers) in the git docs")[0][5] == ["Note: see %(trailers) in the git docs"]
