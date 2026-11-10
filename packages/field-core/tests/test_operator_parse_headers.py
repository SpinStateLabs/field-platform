"""S4-6: operator_auth.parse_headers had no test naming it (only exercised through authenticate and ops-console).
Pinned here directly: a Starlette Headers (getlist) and a plain dict (case-insensitive names), both absent, and every
malformed shape is OperatorRefused(400, 'malformed operator credential headers'): a duplicated header, an empty
value, a comma-joined value, a non-ASCII value, a 65-character id, a 257-character key, and a value ending in a
newline. The newline case was a defect: _OPERATOR_RE and _KEY_RE end in `$` and were applied with .match(), and `$`
also matches before a final newline, so 'don' + newline was accepted; they are now applied with .fullmatch()."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from field_core.operator_auth import HEADER_KEY, HEADER_OPERATOR, OperatorRefused, parse_headers

NL = chr(10)
BAD = "malformed operator credential headers"
KEY = "k" * 40


def starlette(*pairs):
    return Headers(raw=[(k.lower().encode(), v.encode("utf-8")) for k, v in pairs])


def refused(request_headers):
    with pytest.raises(OperatorRefused) as exc:
        parse_headers(request_headers)
    assert exc.value.status == 400 and exc.value.detail == BAD
    return exc.value


# ---- the accepted shapes -----------------------------------------------------------------------------------------


def test_both_headers_are_returned_from_a_starlette_headers_object():
    assert parse_headers(starlette((HEADER_OPERATOR, "svc-op.1@x"), (HEADER_KEY, KEY))) == ("svc-op.1@x", KEY)


def test_both_headers_are_returned_from_a_plain_dict_with_any_name_case():
    assert parse_headers({HEADER_OPERATOR.upper(): "op", HEADER_KEY.title(): KEY}) == ("op", KEY)
    assert parse_headers({HEADER_OPERATOR: "op", HEADER_KEY: KEY}) == ("op", KEY)


@pytest.mark.parametrize("make", [lambda d: starlette(*d.items()), dict])
def test_both_absent_is_none_none_and_one_alone_is_returned(make):
    assert parse_headers(make({})) == (None, None)
    assert parse_headers(make({HEADER_OPERATOR: "op"})) == ("op", None)
    assert parse_headers(make({HEADER_KEY: KEY})) == (None, KEY)


def test_the_length_and_charset_boundaries_are_accepted():
    assert parse_headers({HEADER_OPERATOR: "o" * 64, HEADER_KEY: "k" * 256}) == ("o" * 64, "k" * 256)
    assert parse_headers({HEADER_OPERATOR: "A-z0.9_@", HEADER_KEY: "A-z0.9_~+/="}) == ("A-z0.9_@", "A-z0.9_~+/=")


# ---- every malformed shape is the same fixed 400 -----------------------------------------------------------------


def test_a_duplicated_header_is_refused():
    refused(starlette((HEADER_OPERATOR, "a"), (HEADER_OPERATOR, "b"), (HEADER_KEY, KEY)))
    refused(starlette((HEADER_OPERATOR, "a"), (HEADER_KEY, KEY), (HEADER_KEY, KEY)))


@pytest.mark.parametrize("make", [lambda d: starlette(*d.items()), dict])
def test_an_empty_value_is_refused(make):
    refused(make({HEADER_OPERATOR: "", HEADER_KEY: KEY}))
    refused(make({HEADER_OPERATOR: "op", HEADER_KEY: ""}))


@pytest.mark.parametrize("value", ["a,b", "a, b", ",", "a b", " a", "a ", "a/b", "a\\b", "a;b", "a:b"])
def test_a_comma_joined_or_out_of_charset_operator_is_refused(value):
    refused({HEADER_OPERATOR: value, HEADER_KEY: KEY})


@pytest.mark.parametrize("value", [KEY + ",other", KEY + " ", " " + KEY, KEY + ";", KEY + "*", KEY + "?"])
def test_a_comma_joined_or_out_of_charset_key_is_refused(value):
    refused({HEADER_OPERATOR: "op", HEADER_KEY: value})


@pytest.mark.parametrize("value", ["caf" + chr(0xE9), chr(0x4F60) + chr(0x597D), "op" + chr(0x200B), "o" + chr(0xFF11)])
def test_a_non_ascii_value_is_refused(value):
    refused({HEADER_OPERATOR: value, HEADER_KEY: KEY})
    refused({HEADER_OPERATOR: "op", HEADER_KEY: value})


def test_one_character_over_the_caps_is_refused():
    refused({HEADER_OPERATOR: "o" * 65, HEADER_KEY: KEY})
    refused({HEADER_OPERATOR: "op", HEADER_KEY: "k" * 257})


@pytest.mark.parametrize("make", [lambda d: starlette(*d.items()), dict])
def test_a_trailing_newline_is_refused_on_both_headers(make):
    refused(make({HEADER_OPERATOR: "don" + NL, HEADER_KEY: KEY}))
    refused(make({HEADER_OPERATOR: "don", HEADER_KEY: KEY + NL}))
    refused(make({HEADER_OPERATOR: "don" + NL + NL, HEADER_KEY: KEY}))


def test_the_refusal_text_never_carries_a_header_value():
    exc = refused({HEADER_OPERATOR: "SECRET-MARKER" + chr(0xE9), HEADER_KEY: KEY})
    assert "SECRET-MARKER" not in str(exc) and "SECRET-MARKER" not in exc.detail

