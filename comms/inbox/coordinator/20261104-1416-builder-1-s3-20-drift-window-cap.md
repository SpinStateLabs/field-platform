# builder-1 S3-20 (force-gateway DriftTracker window cap, HIGH CARE)
PR: https://github.com/SpinStateLabs/field-platform/pull/640 (draft), head 4ae9cdf5.
Ran: tests/test_drift_window_cap.py 9 (4 red before; the replay-equivalence tests only bite once something trims); 4 mutants caught (7, 5, 1, 2 failed); services/force-gateway/tests 457 passed.
Replay safety: a 1000-score series with baseline + 2 drift episodes gives identical baseline_mean, consecutive_out, alert_active, alerts_fired and emitted alerts with and without trimming at caps 2, 3, 20.
Decision for Don: store.drift_scores stays append-only and unpruned (card said note only); /telemetry completed_windows is now at most 20 and gains completed_windows_total and window_history_cap.
Needs a reviewer: HIGH CARE card; second reviewer on the replay tests advised.
Note: the first `report` call for S3-17 returned exit 1 ("nothing to commit"), but the file was already on origin/comms and byte-identical (diffed), so it had landed.
