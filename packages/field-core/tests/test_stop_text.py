"""``field_core.stop_text``: what a stop request's reason and operator text may hold."""

from __future__ import annotations

import pytest

from field_core.stop_text import operator_ok, reason_ok, require_operator, require_reason

#: control, format, line and paragraph separator, unpaired surrogate
REFUSED = [0x00, 0x09, 0x0A, 0x0D, 0x1B, 0x7F, 0x85, 0x9F, 0xAD, 0x200B, 0x200D, 0x200F, 0x202E, 0x2028, 0x2029,
           0x2060, 0xFEFF, 0xE0001, 0xD800, 0xDFFF]
ORDINARY = ["halt", "  padded  ", "incident 42: re-check", "caf" + chr(0xE9), chr(0x4E2D) + chr(0x6587),
            "a" + chr(0xA0) + "b", chr(0x1F6D1) + " stop"]


@pytest.mark.parametrize("code", REFUSED, ids=[f"U+{c:04X}" for c in REFUSED])
def test_a_reason_holding_such_a_character_is_refused_without_being_repeated(code):
    text = "zz-marker" + chr(code)
    assert reason_ok(text) is False
    with pytest.raises(ValueError) as exc:
        require_reason(text)
    assert "zz-marker" not in str(exc.value)


@pytest.mark.parametrize("text", ["", " ", "   "])
def test_a_blank_reason_is_refused(text):
    assert reason_ok(text) is False


@pytest.mark.parametrize("text", ORDINARY)
def test_an_ordinary_reason_passes_unchanged(text):
    assert reason_ok(text) is True and require_reason(text) is text


@pytest.mark.parametrize("code", [0xD800, 0xDBFF, 0xDC00, 0xDFFF])
def test_operator_text_with_an_unpaired_surrogate_is_refused(code):
    text = "zz-marker" + chr(code)
    assert operator_ok(text) is False
    with pytest.raises(ValueError) as exc:
        require_operator(text)
    assert "zz-marker" not in str(exc.value)


@pytest.mark.parametrize("text", ["", " ", "   ", chr(9), chr(10), " " + chr(9) + " ", chr(0xA0), chr(0x2028)])
def test_blank_operator_text_is_refused(text):
    assert operator_ok(text) is False
    with pytest.raises(ValueError):
        require_operator(text)


@pytest.mark.parametrize("text", ORDINARY + ["  CISO" + chr(9), "a" + chr(0x200D) + "b"])
def test_operator_text_is_held_to_less_than_a_reason(text):
    assert operator_ok(text) is True and require_operator(text) is text
