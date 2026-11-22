"""S6-22 (the part that is safe to ship): ``FORCE_TELEMETRY_RETAIN`` and an explicit ``retain`` are capped at ``MAX_RETAIN``.

NOT shipped, and why (pinned below as a characterisation): pruning ``drift_scores`` as the card specified cannot be done by
deleting old rows alone. ``DriftTracker`` is rebuilt at start by replaying every row, and its baseline, completed windows,
``alerts_fired`` and ``alert_active`` all depend on the WHOLE history since the last judge change. A tracker replayed from
only the newest rows has a different baseline and loses an active alert."""

from __future__ import annotations

import pytest

from force_gateway.drift import DriftTracker
from force_gateway.store import DEFAULT_RETAIN, MAX_RETAIN, GatewayStore, checked_retain, resolve_retain

ENV = "FORCE_TELEMETRY_RETAIN"


def test_the_cap_is_stated():
    assert MAX_RETAIN == 1_000_000 and DEFAULT_RETAIN < MAX_RETAIN


@pytest.mark.parametrize("raw,expect", [("99999999999999999999", MAX_RETAIN), ("1000001", MAX_RETAIN),
                                        ("1000000", 1_000_000), ("20000", 20_000), ("1", 1), ("0", 1), ("-5", 1),
                                        ("-99999999999999999999", 1), (" 7 ", 7)])
def test_resolve_retain_is_one_to_the_cap(monkeypatch, raw, expect):
    monkeypatch.setenv(ENV, raw)
    assert resolve_retain() == expect


@pytest.mark.parametrize("raw", ["", "abc", "1.5", "1e3", "inf", "nan"])
def test_junk_is_the_default(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert resolve_retain() == DEFAULT_RETAIN


@pytest.mark.parametrize("n,expect", [(10**30, MAX_RETAIN), (0, 1), (-1, 1), (500, 500), (MAX_RETAIN + 1, MAX_RETAIN)])
def test_the_explicit_retain_gets_the_same_check(tmp_path, n, expect):
    s = GatewayStore(tmp_path / "t.sqlite3", retain=n)
    assert s.retain == expect == checked_retain(n)
    s.close()


def test_the_store_still_prunes_to_a_small_retain(tmp_path):
    s = GatewayStore(tmp_path / "t.sqlite3", retain=3)
    for i in range(10):
        s.commit_request("r", {"i": i}, {}, {}, [], "2026-01-01T00:00:00Z")
    assert [r["i"] for r in s.records()] == [7, 8, 9]
    s.close()


# ---- the characterisation: why drift_scores is not pruned here -----------------------------------------------------------

def build(seq):
    t = DriftTracker()
    for s in seq:
        t.record("r", "overall", s, "m", "v")
    return t.status()["r"]["overall"]


def test_a_tracker_replayed_from_only_the_newest_scores_is_not_the_tracker_of_the_full_history():
    """50 steady scores fix the baseline at 0.8, then 150 drifted scores raise an alert. Replay only the newest 60 and the
    drift IS the baseline: no alert, a different baseline. Pruning old rows would silently turn a live alert off after a
    restart, so it needs a checkpoint of the tracker (baseline, windows, alert state), not a DELETE."""
    scores = [0.8] * 50 + [0.4] * 150
    full, tail = build(scores), build(scores[-60:])
    assert (full["baseline_mean"], full["alert_active"], full["alerts_fired"]) == (0.8, True, 1)
    assert (tail["baseline_mean"], tail["alert_active"], tail["alerts_fired"]) == (0.4, False, 0)


def test_the_completed_windows_also_grow_with_the_history():
    full = build([0.8] * 50 + [0.4] * 150)
    assert len(full["completed_windows"]) == 40          # one per window of 5: unbounded in the tracker too (S3-20)
