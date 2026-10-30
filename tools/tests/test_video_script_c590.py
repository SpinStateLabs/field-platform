"""C-590, C-830 (reviewers C-538, C-706, C-755, C-739): a script read aloud states no number the repository cannot back.

Pins on docs/VIDEO-SCRIPT.md: no figure (a digit, a number word or a rough quantity) next to a count or a time noun in
the spoken text (tests, checks, events, records, entries, systems, seconds, milliseconds, minutes), whatever the
wording; the 60-second cut's tamper index agrees with the cue card; no hard-coded run time anywhere in the file; the
event count is read off the screen. Numbers the demo itself produces and the repository backs (five hundred dollars,
one hour, ninety-six percent, seven services) are not nouns of this class and stay.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "docs" / "VIDEO-SCRIPT.md").read_text(encoding="utf-8")
CARD = (ROOT / "integration" / "video" / "CUE-CARD.md").read_text(encoding="utf-8")

NUM = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
       r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half|"
       r"dozen|several|many|few|couple|[0-9][0-9,.:]*)")
NOUN = r"(?:tests?|checks?|events?|records?|entr(?:y|ies)|systems?|seconds?|milliseconds?|minutes?|s|ms)"
GAP = r"(?:[\s\-]+\w+){0,3}?[\s\-]+"
FIGURE_BEFORE = re.compile(rf"\b{NUM}{GAP}{NOUN}\b", re.I)          # "a hundred and sixty-eight tests", "about forty ms"
FIGURE_AFTER = re.compile(rf"\b{NOUN}{GAP}(?:of|is|was|are|at|:)?\s*{NUM}\b", re.I)   # "a test count of 168"


def spoken() -> list[tuple[int, str]]:
    """The lines a voice reads: blockquotes and the VO of the 60-second table."""
    out = []
    for n, line in enumerate(SCRIPT.splitlines(), 1):
        if line.startswith(">"):
            out.append((n, line.lstrip("> ").strip()))
        elif "VO:" in line:
            out.append((n, line.split("VO:", 1)[1].strip()))
    return out


def test_the_scan_reads_the_spoken_text():
    lines = spoken()
    assert len(lines) > 40
    assert any("seven governance services" in text for _, text in lines)


@pytest.mark.parametrize("sample", [
    "one hundred sixty-eight tests", "a hundred and sixty-eight tests", "1,000 tests", "15 events",
    "fifteen records", "fifteen entries", "about twenty-three seconds", "23 seconds", "about 30 s",
    "under half a minute", "forty milliseconds", "a test count of 168", "twelve governance systems",
    "over a hundred checks", "0:23 seconds",
])
def test_the_pattern_catches_each_spelling_reviewers_found(sample):
    assert FIGURE_BEFORE.search(sample) or FIGURE_AFTER.search(sample), sample


def test_the_spoken_text_states_no_count_and_no_time():
    hits = [(n, text) for n, text in spoken() if FIGURE_BEFORE.search(text) or FIGURE_AFTER.search(text)]
    assert not hits, hits


def test_the_spoken_text_keeps_the_figures_the_demo_backs():
    text = " ".join(t for _, t in spoken())
    for kept in ("five hundred dollars a day", "one hour", "ninety-six percent", "seven governance services"):
        assert kept in text, kept


def test_the_script_says_the_event_count_is_on_screen():
    para = re.search(r"chain intact: True\]\*\*(.*?)\n>\s*\n", SCRIPT, re.S)
    assert para and "on screen" in para.group(1)


def test_the_sixty_second_cut_names_the_same_tamper_index_as_the_cue_card():
    cut = re.findall(r"TAMPERED at index (\d+)", SCRIPT)
    card = set(re.findall(r"hash mismatch at index (\d+)", CARD))
    assert cut and card and set(cut) == card


def test_the_script_hard_codes_no_demo_run_time_anywhere():
    # production directions such as "Title card, 3 s" are screen times, not claims about the demo
    assert not re.search(r"~\s*\d+\s*s\b|\brun(?:s| time|ning)?\b[^.\n]{0,30}\b\d+\s*(?:s|sec|seconds|ms)\b"
                         r"|\btakes\b[^.\n]{0,30}\b\d+\s*(?:s|sec|seconds)\b", SCRIPT)
