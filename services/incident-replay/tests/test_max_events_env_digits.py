"""S12-24: FIELD_REPLAY_MAX_EVENTS is ASCII digits, not whatever int() accepts: underscores (2_500; not 5_000, which equals the default), a leading '+' and
Unicode decimal digits (fullwidth, Arabic-Indic) all silently became the event cap. Anything else keeps the default."""
from __future__ import annotations

import pytest

from incident_replay import engine as engine_mod


@pytest.mark.parametrize("raw", ["2_500", "1_0", "+100", "１００", "٣٠", "𝟏𝟎𝟎"], ids=repr)
def test_a_non_ascii_digit_underscore_or_plus_falls_back_to_the_default(monkeypatch, raw):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", raw)
    assert engine_mod.max_timeline_events() == 5000


@pytest.mark.parametrize("raw,expected", [("100", 100), (" 100 ", 100), ("9999", 9999), ("1", 1), ("0100", 100)])
def test_plain_digits_still_work(monkeypatch, raw, expected):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", raw)
    assert engine_mod.max_timeline_events() == expected


@pytest.mark.parametrize("raw", ["10000", "0", "-5"])
def test_out_of_range_still_falls_back(monkeypatch, raw):
    monkeypatch.setenv("FIELD_REPLAY_MAX_EVENTS", raw)
    assert engine_mod.max_timeline_events() == 5000
