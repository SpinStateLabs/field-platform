"""B-RT2 (reviewer-10 MEDIUM F1): a hash or fingerprint written WITH separators must fail the alert content check.

`_HEX_RUN_RE` only matched 12+ contiguous hex digits, and the field charsets allow `. : - _ @` (estate, subject) and any
printable text including a space (detail), so `ab:cd:ef:...` and `ab12-cd34-...` passed. All values here are made up."""

import pytest

from field_core import alerts

H64 = "ab" * 32
H16 = "0123456789abcdef"


def _grouped(hexstr: str, sep: str, size: int) -> str:
    return sep.join(hexstr[i:i + size] for i in range(0, len(hexstr), size))


SEPARATORS = {"colon": ":", "dash": "-", "dot": ".", "space": " ", "underscore": "_"}


@pytest.mark.parametrize("sep", SEPARATORS.values(), ids=SEPARATORS.keys())
@pytest.mark.parametrize("size", [2, 4, 8])
@pytest.mark.parametrize("value", [H64, H16, H64.upper()], ids=["sha256", "fp16", "sha256-upper"])
def test_a_separated_hash_or_fingerprint_is_a_hex_run(value, size, sep):
    assert alerts.content_problem(_grouped(value, sep, size)) == "hex_run"


@pytest.mark.parametrize("text", [
    "build ab:cd:ef:01:23:45 ok", "sha ab12-cd34-ef56 done", "fp 0123.4567.89ab.cdef", "key 0123 4567 89ab cdef",
    "mixed ab:cd-ef.01 23_45",
])
def test_a_separated_run_inside_a_sentence_is_found(text):
    assert alerts.content_problem(text) == "hex_run"


@pytest.mark.parametrize("text", [
    "ab:cd:ef", "1.2.3", "v2026.11.06", "build 659f31b", "port 8080", "step 1 of 3", "gb10 fly", "ab-cd-ef-01-23",
    "log-only -> enforce after 24 h soak",
])
def test_short_or_ordinary_separated_text_is_not_flagged(text):
    assert alerts.content_problem(text) is None


def test_contiguous_hex_is_still_flagged():
    assert alerts.content_problem("a" * 12) == "hex_run" and alerts.content_problem("a" * 11) is None


def test_the_result_never_echoes_the_value():
    assert alerts.content_problem(_grouped(H16, ":", 2)) == "hex_run"           # a fixed code, not text


def test_a_separated_hash_in_a_field_is_withheld_not_sent():
    body = alerts.render("test", estate="gb10", subject=_grouped(H16, ":", 2))[1]
    assert alerts.WITHHELD in body and "01:23" not in body


def test_a_separated_hash_in_the_detail_is_withheld():
    body = alerts.render("test", estate="gb10", detail="fingerprint " + _grouped(H16, " ", 4))[1]
    assert alerts.WITHHELD in body and "0123 4567" not in body


@pytest.mark.parametrize("sep", list(" :._-"))
def test_the_boundary_is_twelve_hex_digits_counted_without_the_separators(sep):
    twelve = sep.join(["0123", "4567", "89ab"])
    eleven = sep.join(["0123", "4567", "89a"])
    assert alerts.content_problem(twelve) == "hex_run"
    assert alerts.content_problem(eleven) is None


# ---- R-PR860-832429a condition C1 and C2: the next most common spellings -----------------------------------------------

BS = chr(92)


@pytest.mark.parametrize("size", [9, 10, 11, 12, 16])
@pytest.mark.parametrize("sep", [" ", ":", "-"], ids=["space", "colon", "dash"])
def test_groups_of_nine_to_sixteen_digits_are_a_hex_run(size, sep):
    groups = [H64[i:i + size] for i in range(0, 48, size)]
    assert alerts.content_problem(sep.join(groups)) == "hex_run"


@pytest.mark.parametrize("sep", [": ", " - ", ", ", ",", " | ", "|", chr(9), chr(10), chr(13) + chr(10), " / ", "::", ".."],
                         ids=["colon-space", "space-dash-space", "comma-space", "comma", "space-pipe-space", "pipe", "tab",
                              "newline", "crlf", "space-slash-space", "double-colon", "double-dot"])
def test_a_doubled_or_unusual_separator_is_a_hex_run(sep):
    assert alerts.content_problem(sep.join(H16[i:i + 2] for i in range(0, 16, 2))) == "hex_run"


@pytest.mark.parametrize("sep", [chr(0x00A0), chr(0x200B), chr(0x2009), chr(0x3000)],
                         ids=["no-break-space", "zero-width-space", "thin-space", "ideographic-space"])
def test_a_no_break_or_zero_width_separator_is_a_hex_run(sep):
    assert alerts.content_problem(sep.join(H16[i:i + 2] for i in range(0, 16, 2))) == "hex_run"


@pytest.mark.parametrize("prefix", ["0x", "0X", BS + "x"], ids=["0x", "0X", "backslash-x"])
@pytest.mark.parametrize("sep", [" ", ",", ", ", ""], ids=["space", "comma", "comma-space", "none"])
def test_byte_prefixes_are_removed_before_counting(prefix, sep):
    assert alerts.content_problem(sep.join(prefix + H16[i:i + 2] for i in range(0, 16, 2))) == "hex_run"


def test_a_byte_prefix_alone_is_not_a_hex_run():
    assert alerts.content_problem("0x01 0x23 0x45") is None and alerts.content_problem("status 0xff") is None


@pytest.mark.parametrize("text", ["20261106 123045", "2026-11-06 12:30", "20261106-123045"])
def test_a_separated_digits_only_run_of_twelve_or_more_is_withheld_the_stated_tradeoff(text):
    """C2: a date and time written as digits is withheld, as a contiguous 12-digit run already was. Fail-safe, pinned so a
    later tightening is a decision, not an accident."""
    assert alerts.content_problem(text) == "hex_run"


@pytest.mark.parametrize("text", ["version 1.2.3 build 659f31b", "port 8080, retries 3", "ab:cd:ef:01:23", "a, b, c, d, e",
                                  "see https://example.test/a/b/c", "step 1: ok, step 2: ok"])
def test_ordinary_text_with_separators_stays_clear(text):
    assert alerts.content_problem(text) is None
