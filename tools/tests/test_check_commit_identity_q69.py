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


# ---- F-Q69-1: the trailer KEY was echoed in the field label; only well-known keys are named now ---------------------------
def fields(text, **kw):
    return [(f.field, f.reason) for f in cci.check(text, **kw)]


def tline(*trailers, **kw) -> str:
    return line(**kw) + "\x1f" + "\x1e".join(trailers)


@pytest.mark.parametrize("key", ["Co-authored-by", "Signed-off-by", "Reviewed-by", "Acked-by", "Tested-by", "Reported-by",
                                 "Suggested-by", "Helped-by", "Cc", "CO-AUTHORED-BY"])
def test_a_well_known_key_is_named_in_lower_case(key):
    assert fields(tline(f"{key}: Someone <{BAD_ADDR}>")) == [(f"trailer {key.lower()} email", "is not an accepted no-reply form")]


@pytest.mark.parametrize("key", ["Handle-Name", "someone-example", "X-Mailbox", "Dev123", "a-b-c-d-e-f"])
def test_any_other_key_is_shown_as_trailer_only(key):
    assert fields(tline(f"{key}: Someone <{BAD_ADDR}>")) == [("trailer email", "is not an accepted no-reply form")]
    assert fields(tline(f"{key}: {BAD_ADDR}")) == [("trailer", "is an email address")]


def test_the_known_key_set_is_small_and_lower_case():
    assert cci.KNOWN_TRAILER_KEYS and all(k == k.lower() and "-" in k or k == "cc" for k in cci.KNOWN_TRAILER_KEYS)
    assert len(cci.KNOWN_TRAILER_KEYS) <= 16


# ---- F-Q69-3: a URL, an @handle or a scoped package name in a bare trailer value was flagged as an address --------------
@pytest.mark.parametrize("trailer", [
    "Link: https://example.invalid/@someone/post",
    "Reviewed-on: https://review.example.invalid/c/x/+/12",
    "Link: https://example.invalid/pkg/@scope/name@1.2.3",
    "Package: @scope/name@1.2.3",
    "Package: @scope/name",
    "Co-authored-by: Example Person (@someone)",
    "Thanks: @someone, @someone-else.",
    "Ref: ssh://git@git.example.invalid/org/repo.git",
])
def test_a_url_a_handle_or_a_package_name_in_a_bare_trailer_value_is_not_an_address(trailer):
    assert cci.check(tline(trailer)) == [], trailer


@pytest.mark.parametrize("trailer", [
    "Reported-by: " + BAD_ADDR,
    "Thanks: ask " + BAD_ADDR + " about it",
    "Reviewed-on: git@git.example.invalid:org/repo",       # scp-style remote: a user@host token, flagged by design
    "Note: someone @ mail . example . invalid",
    "Link: https://example.invalid/x " + BAD_ADDR,           # the address token beside the URL is still seen
])
def test_an_address_token_in_a_bare_trailer_value_is_still_a_finding(trailer):
    assert cci.check(tline(trailer)) != [], trailer


# ---- F-Q69-2: only git's trailer block is read; the subject, prose paragraphs and a prose line inside the trailer paragraph
# are not. Stated in the docstring and pinned through git (mutant Q2: ``only`` dropped from the placeholder, which would
# read the prose line of the trailer paragraph).
def test_a_prose_line_inside_the_trailer_paragraph_is_not_read(repo):
    from test_check_commit_identity_c564 import GOOD_EMAIL, _commit_with_message
    _commit_with_message(repo, "subject mentioning " + BAD_ADDR + "\n\nbody paragraph with " + BAD_ADDR + "\n\n"
                               "Signed-off-by: Example Person <" + GOOD_EMAIL + ">\nask " + BAD_ADDR + " for details")
    p = _run(repo)
    assert p.returncode == 0 and "checked 1 commit)" in p.stdout, p.stdout + p.stderr


def test_the_docstring_states_what_is_not_read():
    doc = cci.__doc__
    assert "subject" in doc and "prose" in doc and "trailer block" in doc


def test_the_bracketed_form_is_unchanged_by_the_token_rule():
    assert fields(tline("Co-authored-by: Example Person (@someone) <" + BAD_ADDR + ">")) == [("trailer co-authored-by email", "is not an accepted no-reply form")]
    assert fields(tline("Co-authored-by: " + BAD_ADDR + " <" + BAD_ADDR + ">")) == [("trailer co-authored-by name", "is an email address"),
                                                                                 ("trailer co-authored-by email", "is not an accepted no-reply form")]
    assert cci.check(tline("Co-authored-by: Example Person <noreply@anthropic.com>")) == []
