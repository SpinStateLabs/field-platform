"""S3-20: DriftTracker kept one float per completed window per (route, dimension) series forever, and status() (the
GET /telemetry hygiene_trend) returned them all. Only the first `baseline_windows` entries (until the baseline is
fixed) and the last two (the alert) are ever READ by the logic, so the retained list is capped (default 20) and
status() reports the cap and the total ever completed. HIGH CARE: state is rebuilt at startup by replaying the stored
scores, so trimming must not change the replay: baseline_mean, consecutive_out, alert_active, alerts_fired and every
emitted alert must be identical with and without trimming."""

from __future__ import annotations

import random

import pytest

from force_gateway.drift import DriftTracker

MODEL, RUBRIC = "judge-a", "r1"
NO_TRIM = 10**9


def tracker(cap=None, **kw):
    t = DriftTracker(**kw)
    if cap is not None:
        t.window_history_cap = cap
    return t


def scores(n=1000, seed=7):
    """n scores in a pattern that fixes a baseline, then drifts out, recovers and drifts again, with noise."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        window = i // 5
        phase = (window // 7) % 3          # 0 = in band, 1 = out of band, 2 = in band
        base = 0.5 if window < 6 or phase != 1 else 0.95
        out.append(min(1.0, max(0.0, base + rng.uniform(-0.03, 0.03))))
    return out


def feed(t, seq, route="r", dim="overall"):
    alerts = []
    for s in seq:
        a = t.record(route, dim, s, MODEL, RUBRIC)
        if a is not None:
            alerts.append((a.route, a.dimension, a.baseline_mean, a.band, a.window_means))
    return alerts


def logic_state(t, route="r", dim="overall"):
    st = t.status()[route][dim]
    return {k: st[k] for k in ("baseline_mean", "consecutive_out_of_band", "alert_active", "alerts_fired",
                               "scores_in_current_window", "band", "window_size", "model", "rubric_version")}


@pytest.mark.parametrize("cap", [2, 3, 20])
def test_a_1000_score_replay_is_identical_with_and_without_trimming(cap):
    seq = scores(1000)
    plain, trimmed = tracker(NO_TRIM), tracker(cap)
    a_plain, a_trim = feed(plain, seq), feed(trimmed, seq)
    assert a_plain == a_trim and len(a_plain) >= 2          # the pattern really does fire (and re-arm and fire again)
    assert logic_state(plain) == logic_state(trimmed)
    assert logic_state(plain)["alerts_fired"] == len(a_plain)


def test_a_fresh_tracker_replaying_the_stored_scores_reproduces_the_live_one():
    seq = scores(1000)
    live, replayed = tracker(), tracker()
    feed(live, seq)
    feed(replayed, seq)                                      # what api._load_state does at startup
    assert logic_state(live) == logic_state(replayed)
    assert live.status() == replayed.status()


def test_the_retained_list_is_capped_and_keeps_the_newest_windows():
    seq = scores(1000)
    plain, trimmed = tracker(NO_TRIM), tracker(20)
    feed(plain, seq)
    feed(trimmed, seq)
    full = plain.status()["r"]["overall"]["completed_windows"]
    kept = trimmed.status()["r"]["overall"]["completed_windows"]
    assert len(full) == 200 and len(kept) == 20
    assert kept == full[-20:]


def test_status_reports_the_cap_and_the_total_ever_completed():
    t = tracker(20)
    feed(t, scores(1000))
    st = t.status()["r"]["overall"]
    assert st["window_history_cap"] == 20 and st["completed_windows_total"] == 200
    assert len(st["completed_windows"]) == 20


def test_before_the_baseline_is_fixed_nothing_is_trimmed():
    t = tracker(2, baseline_windows=4)
    feed(t, [0.5] * (5 * 3))                                 # 3 windows: baseline not yet fixed
    st = t.status()["r"]["overall"]
    assert st["baseline_mean"] is None and len(st["completed_windows"]) == 3
    feed(t, [0.5] * 5)                                       # 4th window fixes it
    st = t.status()["r"]["overall"]
    assert st["baseline_mean"] == 0.5 and len(st["completed_windows"]) <= 2 and st["completed_windows_total"] == 4


def test_the_alert_still_names_the_last_two_window_means_after_trimming():
    t = tracker(2)
    alerts = feed(t, [0.5] * 20 + [0.9] * 5 + [0.95] * 5)    # 4 baseline windows, then two out of band
    assert alerts == [("r", "overall", 0.5, 0.15, (0.9, 0.95))]


def test_a_judge_change_still_resets_the_series_including_its_total():
    t = tracker(20)
    feed(t, [0.5] * 50)
    t.record("r", "overall", 0.5, "judge-b", "r1")
    st = t.status()["r"]["overall"]
    assert st["completed_windows"] == [] and st["completed_windows_total"] == 0 and st["baseline_mean"] is None
