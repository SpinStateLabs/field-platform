"""Fallback scan: `store.resolve_retain` (the FORCE_TELEMETRY_RETAIN parse) is exercised end to end by `test_d2_rates.py` with
the values 1 and 3, but its edge cases are named in no test: unset, blank, whitespace, junk, zero, negative, float text, a huge
number, padding. docs/ENVIRONMENT.md says "int clamped to >= 1; non-integer or blank falls back to 10000". Tests only, no
source change; what is pinned is what the code does today."""
from __future__ import annotations

import pytest

from force_gateway.store import DEFAULT_RETAIN, GatewayStore, resolve_retain

ENV = "FORCE_TELEMETRY_RETAIN"


def test_the_documented_default_is_ten_thousand():
    assert DEFAULT_RETAIN == 10_000


def test_unset_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert resolve_retain() == DEFAULT_RETAIN


@pytest.mark.parametrize("value,want", [
    ("1", 1), ("3", 3), ("10000", 10_000), ("50000", 50_000), ("123456789012", 123_456_789_012),
    (" 5 ", 5), ("\t7\n", 7), ("+4", 4), ("0007", 7), ("1_000", 1000),          # int() accepts padding, a sign, underscores
])
def test_an_integer_is_used_as_read(monkeypatch, value, want):
    monkeypatch.setenv(ENV, value)
    assert resolve_retain() == want


@pytest.mark.parametrize("value", ["0", "-1", "-100", "-0", "-99999999999"])
def test_zero_and_negative_clamp_to_one(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    assert resolve_retain() == 1


@pytest.mark.parametrize("value", ["", " ", "\t", "abc", "1.5", "1e3", "5.0", "0x10", "ten", "1 2", "--1", "nan", "inf",
                                   "١٢", "5!", "None"])
def test_a_blank_or_non_integer_falls_back_to_the_default(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    got = resolve_retain()
    # int() accepts Arabic-Indic digits ("١٢" is 12): that one is an integer, not junk; every other value here is junk
    assert got == (12 if value == "١٢" else DEFAULT_RETAIN)


def test_a_caller_supplied_default_is_what_junk_falls_back_to(monkeypatch):
    monkeypatch.setenv(ENV, "junk")
    assert resolve_retain(default=42) == 42
    monkeypatch.setenv(ENV, "")
    assert resolve_retain(default=7) == 7
    monkeypatch.delenv(ENV)
    assert resolve_retain(default=9) == 9


def test_the_default_argument_is_not_clamped(monkeypatch):
    """Only a PARSED value is clamped to >= 1; a caller's default is returned as given."""
    monkeypatch.setenv(ENV, "junk")
    assert resolve_retain(default=0) == 0


def test_the_store_reads_the_environment_when_no_retain_is_given(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "17")
    store = GatewayStore(tmp_path / "t.sqlite3")
    try:
        assert store.retain == 17
    finally:
        store.close()


def test_an_explicit_retain_beats_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "17")
    store = GatewayStore(tmp_path / "t.sqlite3", retain=3)
    try:
        assert store.retain == 3
    finally:
        store.close()


def test_an_explicit_zero_retain_is_kept_as_given_not_replaced_by_the_environment(monkeypatch, tmp_path):
    """`retain if retain is not None`: 0 is an explicit value, not 'unset'."""
    monkeypatch.setenv(ENV, "17")
    store = GatewayStore(tmp_path / "t.sqlite3", retain=0)
    try:
        assert store.retain == 0
    finally:
        store.close()


def test_the_store_prunes_to_the_resolved_retain(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, "2")
    store = GatewayStore(tmp_path / "t.sqlite3")
    try:
        for i in range(5):
            store.commit_request("balanced", {"i": i}, agg={}, counters={}, drift_scores=[], ts="2026-01-01T00:00:00Z")
        assert [r["i"] for r in store.records()] == [3, 4]               # the newest two, oldest first
    finally:
        store.close()
