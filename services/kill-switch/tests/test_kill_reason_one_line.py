"""``KillRequest.reason`` is one plain line: no control, invisible-format, line- or paragraph-separator character."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kill_switch.api import KillRequest

REFUSED = [0x00, 0x09, 0x0A, 0x0D, 0x1B, 0x7F, 0x85, 0x9F, 0xAD, 0x200B, 0x200D, 0x200F, 0x202E, 0x2028, 0x2029,
           0x2060, 0xFEFF, 0xE0001]


@pytest.mark.parametrize("code", REFUSED, ids=[f"U+{c:04X}" for c in REFUSED])
@pytest.mark.parametrize("position", ["start", "middle", "end"])
def test_a_reason_with_such_a_character_is_refused(code, position):
    text = {"start": chr(code) + "halt", "middle": "ha" + chr(code) + "lt", "end": "halt" + chr(code)}[position]
    with pytest.raises(ValidationError):
        KillRequest(operator="o", reason=text)


@pytest.mark.parametrize("reason", ["halt", "  padded  ", "incident 42: re-check", "caf" + chr(0xE9),
                                    chr(0x4E2D) + chr(0x6587), "a" + chr(0xA0) + "b", "x" * 1000])
def test_an_ordinary_reason_is_kept_as_sent(reason):
    assert KillRequest(operator="o", reason=reason).reason == reason
