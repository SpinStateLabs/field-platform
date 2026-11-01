"""The invoicing skill names its clients by placeholder only (C-1068, reviewer C-1058 F-397-1).

The check is structural so no real name has to appear in a test: in the description line, each cadence word in
brackets is preceded by a ``<Client X>`` placeholder, and the short-code example uses placeholders on both sides.
"""
from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "agents" / "ssl-invoicing-agent" / "SKILL.md"
PLACEHOLDER = r"<Client [A-Z]>"


def _lines():
    return SKILL.read_text(encoding="utf-8").splitlines()


def test_each_cadence_in_the_description_follows_a_client_placeholder():
    description = next(line for line in _lines() if line.startswith("description:"))
    cadences = re.findall(r"\((?:weekly|monthly)\)", description)
    assert len(cadences) == 2, cadences
    assert len(re.findall(PLACEHOLDER + r" \((?:weekly|monthly)\)", description)) == 2


def test_the_short_code_example_uses_placeholders_on_both_sides():
    codes = [line for line in _lines() if line.startswith("- ") and " codes:" in line]
    assert len(codes) == 1
    assert re.search(r"\(for example `" + PLACEHOLDER + r"` = `<code [A-Z]>`\)", codes[0]), "example not a placeholder pair"
    assert not re.search(r"= `[A-Z]{2,3}`", codes[0]), "a literal short code is back"
