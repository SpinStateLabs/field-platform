"""C-590 (reviewer C-538 F-C538-1..3): a script read aloud states no number the repository cannot back.

Pins on docs/VIDEO-SCRIPT.md: no spoken test count (the repository's count changes every batch), no event count
spoken in Scene 2 (the demo prints the number it finds), the 60-second cut's tamper index agrees with the cue
card, and no hard-coded run time (IMPLEMENTATION.md and INTEGRATION.md disagree: ~23 s and ~30 s).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "docs" / "VIDEO-SCRIPT.md").read_text(encoding="utf-8")
CARD = (ROOT / "integration" / "video" / "CUE-CARD.md").read_text(encoding="utf-8")
NUMBER_WORDS = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|" \
               r"sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|" \
               r"hundred|thousand|[0-9,]+)"


def test_the_script_speaks_no_test_count():
    assert not re.search(rf"\b{NUMBER_WORDS}(?:[ -]{NUMBER_WORDS})*\s+tests\b", SCRIPT, re.I)


def test_the_script_does_not_speak_an_event_count():
    assert not re.search(rf"\b{NUMBER_WORDS}(?:[ -]{NUMBER_WORDS})*\s+events\b", SCRIPT, re.I)


def test_the_script_says_the_events_are_on_screen():
    assert "on screen" in SCRIPT.split("chain intact: True", 1)[1][:200]


def test_the_sixty_second_cut_names_the_same_tamper_index_as_the_cue_card():
    cut = re.findall(r"TAMPERED at index (\d+)", SCRIPT)
    card = set(re.findall(r"hash mismatch at index (\d+)", CARD))
    assert cut and card and set(cut) == card


def test_the_script_hard_codes_no_run_time():
    assert not re.search(r"~\s*\d+\s*s\b", SCRIPT)
