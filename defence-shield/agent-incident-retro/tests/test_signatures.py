"""Signature tables: bounded matching cost (ReDoS) and detection parity.

Second independent review (2026-10-12), HIGH-2: the ``ssti`` pattern was cubic
(8 KB -> 2.1 s, 16 KB -> 18 s) and the 8 KB cap applied only in ``classify``,
not in ``hostile_params``. These tests pin both fixes.
"""

import re
import time
from urllib.parse import quote

import pytest

from agent_incident_retro.signatures import (
    AUTOMATION_UA,
    DEBUG_PATH,
    DEBUG_QUERY,
    MAX_MATCH_LEN,
    PAYLOAD_PATTERNS,
    bounded,
    classify,
    hostile_params,
    is_automation_ua,
)

SQLI = quote("' OR '1'='1", safe="")

#: 16 KB adversarial inputs, one per family's open-ended construct.
ADVERSARIAL = {
    "ssti {{config": "{{config" * 2048,
    "ssti {{ no close": "{{" + "a" * 16382,
    "xss <img": "<img " * 3277,
    "xss <img onx": "<img " + "onx " * 4095,
    "sqli union": "union " * 2731,
    "sqli ' or": "' or " * 3277,
    "sqli ' or word": "' or " + "a" * 16379,
    "cmdi backtick": "`" + "a" * 16383,
    "cmdi ;": "; " * 8192,
    "traversal": "../" * 5461,
    "debug &debug=": "&debug=" * 2340,
}

LIMIT_S = 0.2


def _timed(fn):
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


@pytest.mark.parametrize("label", sorted(ADVERSARIAL))
def test_adversarial_16kb_input_classifies_fast(label: str):
    payload = ADVERSARIAL[label]
    assert len(payload) >= 16 * 1024 - 8
    query = f"q={quote(payload, safe='')}&z={SQLI}"
    assert _timed(lambda: classify("/search", query)) < LIMIT_S, label
    assert _timed(lambda: classify("/" + payload, "")) < LIMIT_S, label
    # the S.pivot path: hostile_params used to run the patterns UNCAPPED
    assert _timed(lambda: hostile_params(query)) < LIMIT_S, label
    assert _timed(lambda: is_automation_ua(payload)) < LIMIT_S, label


def test_cap_applies_in_every_regex_entry_point():
    """A 1 MB value must cost no more than an 8 KB one in every public matcher."""
    huge = "{{config" * (1024 * 1024 // 8)
    assert len(bounded(huge)) == MAX_MATCH_LEN
    query = f"q={quote(huge, safe='')}&z={SQLI}"
    assert _timed(lambda: hostile_params(query)) < LIMIT_S
    assert _timed(lambda: classify("/x", query)) < LIMIT_S
    assert _timed(lambda: classify("/" + huge, "")) < LIMIT_S
    assert _timed(lambda: is_automation_ua(huge)) < LIMIT_S


def test_no_pattern_has_an_unbounded_run_between_required_tokens():
    """Audit, codified: an open-ended ``[^x]*`` / ``.*`` between two required
    tokens is where super-linear backtracking comes from. Every such run in the
    tables must carry an explicit ``{0,N}`` bound."""
    unbounded = re.compile(r"(\[\^[^\]]*\]|\\S|\\s\\S|\.)\s*(\*|\+)(?!\+)")
    tables = {**PAYLOAD_PATTERNS, "DEBUG_PATH": DEBUG_PATH, "DEBUG_QUERY": DEBUG_QUERY, "AUTOMATION_UA": AUTOMATION_UA}
    for name, pattern in tables.items():
        assert unbounded.search(pattern.pattern) is None, (name, pattern.pattern)


def test_bounded_patterns_still_detect_the_payloads_they_are_for():
    assert "ssti" in classify("/", "q=" + quote("{{config.__class__}}", safe=""))[0]
    assert "ssti" in classify("/", "q=" + quote("{{ self.__init__.__globals__ }}", safe=""))[0]
    assert "ssti" in classify("/", "q=" + quote("{{7*7}}", safe=""))[0]
    assert "ssti" in classify("/", "q=" + quote("${7*7}", safe=""))[0]
    assert "xss" in classify("/", "q=" + quote("<img src=x onerror=alert(1)>", safe=""))[0]
    assert "xss" in classify("/", "q=" + quote("<svg/onload=alert(1)>", safe=""))[0]
    # parity with v0.1: an unclosed "{{config" was never a match
    assert "ssti" not in classify("/", "q=" + quote("{{config", safe=""))[0]
    # a benign query with braces is not a payload
    assert classify("/", "q=" + quote("{{ not a template }}", safe=""))[0] == []
