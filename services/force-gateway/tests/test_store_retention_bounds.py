"""S6-22, what is left of PR 721 on current main (test-only; reviewer-sub-F BLOCK on #1245, controller ruling): main's later
pinned behaviour wins (tests/test_store_retain.py): ``FORCE_TELEMETRY_RETAIN`` is used as read (no upper cap, 0 and
negatives clamp to 1) and an explicit ``retain`` is kept as given, so PR 721's ``MAX_RETAIN`` cap is NOT carried.

What is carried is PR 721's characterisation of why ``drift_scores`` is not pruned: deleting old rows alone cannot do it.
``DriftTracker`` is rebuilt at start by replaying every row, and its baseline, completed windows, ``alerts_fired`` and
``alert_active`` all depend on the WHOLE history since the last judge change. A tracker replayed from only the newest rows
has a different baseline and loses an active alert."""

from __future__ import annotations

from force_gateway.drift import DriftTracker
from force_gateway.store import GatewayStore


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
