# Reviewer report: PR 640 @ 4ae9cdf5f28867ccab87b1fb7d170ae66ed724cd (force-gateway: DriftTracker keeps the newest 20 completed windows per series, S3-20)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main b963407a (the current tip); `git merge-tree --write-tree origin/main pr640` clean. 2 files (+133): force_gateway/drift.py (+20) and tests/test_drift_window_cap.py (+113). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. The change trims state that is REBUILT at startup by replaying stored scores (force_gateway/store.py header and the test docstring say so): any trimming that changes the replayed baseline, alert state or emitted alerts is a silent behaviour change of the drift alert. The PR's own "HIGH CARE" note names this, so I checked it with an independent probe (below) and with mutants.
2. The cap interacts with `baseline_windows`: `FORCE_HYGIENE_BASELINE_WINDOWS` is configurable, and a value above the cap (20) makes the baseline window list longer than what is retained. A wrong order (trim before the baseline mean is computed) would corrupt exactly that case.
3. `/telemetry` now shows `completed_windows` capped at the cap and two new fields; any consumer that read the full list (the ops console, scripts) sees less history; the docs do not say so (LOW).

## Verified (run by me)
- Baseline on the exact head: tests/test_drift_window_cap.py + test_d2_drift_dimensions.py 18 passed; whole services/force-gateway/tests 457 passed (all service sources on the path, pytest-xdist -n 4).
- Independent probe (not in the PR): 3000 noisy scores through a tracker with the default cap 20 versus a tracker with the cap at 10**9 (no trimming), for `baseline_windows` in 1, 2, 5, 19, 20, 21, 25, 30: the alerts (index, window means, baseline), the baseline mean, `consecutive_out`, `alert_active` and `alerts_fired` are identical in every case, `windows_completed` is 1000 and the retained list is 20 (HIGH). The same holds for caps 0, 1 (floored to 2), 2 and 3. So the code is correct where the tests are thin.

## Mutants (mutations of drift.py; scratch worktree on the head; baseline 18 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| T1 | trim does nothing | 3 failed | yes |
| T2 | trim keeps the OLDEST entries | 5 failed | yes |
| T3 | keep not floored at 2 | 18 passed | NO |
| T4 | keep floored at 1 | 18 passed | NO |
| T5 | keep floored at 3 | 1 failed | yes |
| T6 | trim before the baseline mean is computed | 18 passed | NO |
| T7 | trim only at the baseline, never afterwards | 2 failed | yes |
| T8 | trim never at the baseline (only after) | 1 failed | yes |
| T9 | `windows_completed` not incremented | 2 failed | yes |
| T10 | `windows_completed` incremented by 2 | 2 failed | yes |
| T11 | status: total missing | 3 failed | yes |
| T12 | status: cap shown raw (no floor) | 18 passed | NO |
| T13 | default cap 20 -> 200 | 18 passed | NO |
| T14 | default cap 20 -> 2 | 18 passed | NO |
| T15 | default cap 20 -> 19 | 18 passed | NO |
| T16 | status total as a float | 18 passed | NO (type only) |
Totals counted from the table: 16 valid mutants, 8 killed, 8 survived (T3, T4, T6, T12, T13, T14, T15, T16). My T17 (reset on a judge change) was not built and is excluded. Survivors against the whole force-gateway suite (457 at baseline): T3, T4, T13, T14 still pass 457 (run); I did not run T6, T12, T15, T16 against the whole suite.

## Findings
- F-S320-1 MEDIUM-LOW: the floor at 2 ("it must stay >= 2", the comment in drift.py) is unpinned (T3, T4); without it a cap of 0 or 1 would leave fewer than two entries and the alert's `window_means[-2]` would raise. The code floors it; no test does.
- F-S320-2 MEDIUM-LOW: the order "baseline first, trim after" is unpinned for `baseline_windows` above the cap (T6); the replay-equality property the PR calls HIGH CARE has no case where `baseline_windows > cap`. My probe shows the code correct there; add the case.
- F-S320-3 LOW: the default cap 20 is unpinned by value (T13, T14, T15) and the status cap floor and total type (T12, T16).
- F-S320-4 LOW: objection 3, document that `completed_windows` is now the newest 20.

## Verdict: PASS on 4ae9cdf5f28867ccab87b1fb7d170ae66ed724cd
The behaviour is correct (independent probe) and the replay-equality tests kill the trim-direction and trim-timing mutants; the 8 survivors are test gaps, F-S320-1 and -2 the ones worth a follow-up. Head frozen; they go in a NEW PR. CI green and the full GX10 run on this exact head per the coordinator procedure. Not run by me: CI, GX10.
