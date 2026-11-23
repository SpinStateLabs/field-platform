"""Mutant survivor (Lane R): _parse_method accepts exactly ONE known verb."""

import pytest

from kill_switch.api import _parse_method


@pytest.mark.parametrize("raw", [
    "POST GET",        # two known verbs: ambiguous, never pick the first
    "GET POST",
    "FETCH",           # one token, not a known method
    "HTTP FETCH",
    "POST FETCH",      # a known verb beside junk
    "HTTP",            # only the prefix: no tokens left
])
def test_parse_method_refuses_anything_but_one_known_verb(raw):
    assert _parse_method(raw) is None


def test_parse_method_still_accepts_one_known_verb():
    assert _parse_method("HTTP/POST") == "POST"
