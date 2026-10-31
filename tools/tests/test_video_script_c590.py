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
       r"dozens?|hundreds|thousands|millions|billions|scores?|countless|several|many|few|couple|lots|a lot|"
       r"zero|handful|single|"
       r"[0-9][0-9,.:]*)")
NOUN = (r"(?:tests?|checks?|controls?|events?|records?|rows?|keystrokes?|entr(?:y|ies)|systems?|seconds?|"
        r"milliseconds?|minutes?|hours?|s|ms)")
GAP = r"(?:[\s\-]+\w+){0,3}?[\s\-]+"
FIGURE_BEFORE = re.compile(rf"\b{NUM}{GAP}{NOUN}\b", re.I)          # "a hundred and sixty-eight tests", "about forty ms"
FIGURE_AFTER = re.compile(rf"\b{NOUN}{GAP}(?:of|is|was|are|at|:)?\s*{NUM}\b", re.I)   # "a test count of 168"
A_TIME = re.compile(r"\b(?:a|an)\s+(?:second|minute|hour)\b", re.I)                   # "in under a second", "an hour of"
MULTIPLIER = re.compile(r"\b[0-9]+\s*x\b|\b\w+\s+times\s+(?:faster|more|as)\b|\b\w+-?fold\b", re.I)   # "10x faster", "ten-fold"
BARE_TIME = re.compile(r"\b(?:nano|micro|milli)seconds\b|\b(?:in|within)\s+(?:seconds|minutes)\b", re.I)    # "in milliseconds"
KEPT = (re.compile(r"(?<![\w-])one hour(?![\w-])", re.I),)    # backed by run_demo.sh:76 (--ttl 3600); masked whole-word only


def figure_in(text: str) -> bool:
    for kept in KEPT:
        text = kept.sub(" ", text)
    return bool(FIGURE_BEFORE.search(text) or FIGURE_AFTER.search(text) or A_TIME.search(text)
                or MULTIPLIER.search(text) or BARE_TIME.search(text))


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
    "dozens of controls", "hundreds of tests", "thousands of events", "a lot of checks", "lots of tests",
    # C-937 F-C937-2: the ten shapes the first widening still missed
    "countless checks", "in under a second", "millions of events", "a score of tests", "eight thousand rows",
    "within an hour", "two hours", "ten times faster", "10x faster", "an hour of tests", "two keystrokes",
    # C-1062 (reviewer C-1050 F-C1050-1): collective words, zero, a fold, a single keystroke, bare time phrases
    "scores of tests", "a handful of events", "zero tests", "ten-fold faster", "tenfold faster", "a single keystroke",
    "in milliseconds", "in seconds", "within minutes", "in nanoseconds", "answers in microseconds",
    # C-1062 (reviewer C-1050 F-C1050-2): the kept phrase masks only itself, not a longer figure around it
    "twenty-one hours of tests", "one hourly check", "one hours of tests",
])
def test_the_pattern_catches_each_spelling_reviewers_found(sample):
    assert figure_in(sample), sample


@pytest.mark.parametrize("sample", ["one hour", "a test suite that runs on every change", "five hundred dollars a day",
                                    "ninety-six percent of cap", "one command boots seven governance services",
                                    # C-1062 (reviewer C-1050): not figure claims
                                    "every second", "no tests failed", "minutes not hours", "in no time", "instantly",
                                    "a signed key with one hour to live", "the ttl is one hour"])
def test_the_pattern_leaves_the_backed_figures_alone(sample):
    assert not figure_in(sample), sample


def test_the_spoken_text_states_no_count_and_no_time():
    hits = [(n, text) for n, text in spoken() if figure_in(text)]
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
