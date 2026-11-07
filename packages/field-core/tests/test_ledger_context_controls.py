"""S8-4 — control, format and bidi characters never reach a ledger row through correlation_context
or ledger_note. Letters of any script are kept; whitespace still separates words."""

from __future__ import annotations

import pytest

from field_core.ledger_context import (MAX_ID_CHARS, MAX_NOTE_CHARS, correlation_context, ledger_note)

CASES = [
    ("a\x1b[31mred", "a[31mred"),        # ESC is dropped; the printable remainder is plain text
    ("a\x00b", "ab"),
    ("a\x7fb", "ab"),
    ("a\u0085b c", "a b c"),             # NEL is whitespace to str.split: a separator
    ("a\u0090b", "ab"),                  # C1 control
    ("a‮b‬c", "abc"),          # bidi override and pop
    ("a⁦b⁩", "ab"),            # bidi isolates
    ("a​b", "ab"),                  # zero-width space (Cf)
    ("a\udcffb", "ab"),                  # lone surrogate
    ("ab", "ab"),                  # private use
    ("a\x0ab\tc\r\nd", "a b c d"),       # whitespace still separates words
    ("a b", "a b"),
    ("日本語-id-１", "日本語-id-１"),       # CJK and full-width digit kept
    ("Zoë-ñ", "Zoë-ñ"),
]


@pytest.mark.parametrize("raw, want", CASES)
def test_ledger_note(raw, want):
    assert ledger_note(raw) == want


@pytest.mark.parametrize("raw, want", CASES)
def test_correlation_context(raw, want):
    assert correlation_context({"session_id": raw}) == {"session_id": want}


@pytest.mark.parametrize("raw", ["\x00", "\x1b\x7f", "‮‬", " \x00 \t", "\udcff", "​"])
def test_a_value_empty_after_cleaning_is_dropped(raw):
    assert ledger_note(raw) is None
    assert correlation_context({"source": raw, "session_id": "ok"}) == {"session_id": "ok"}


def test_truncation_comes_after_cleaning():
    assert ledger_note("\x00" * 1000 + "x" * 10) == "x" * 10          # the nulls do not eat the budget
    assert ledger_note("a‮" * 1000) == "a" * MAX_NOTE_CHARS
    assert correlation_context({"event_id": "\x1b" * 500 + "y" * 5}) == {"event_id": "y" * 5}
    assert len(correlation_context({"event_id": "z" * 500})["event_id"]) == MAX_ID_CHARS


def test_allow_list_and_non_strings_unchanged():
    assert correlation_context({"secret": "x", "session_id": 5, "source": "s"}) == {"source": "s"}
    assert correlation_context(None) == {} and ledger_note(None) is None and ledger_note(5) is None
