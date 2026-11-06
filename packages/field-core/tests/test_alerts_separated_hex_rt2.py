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
