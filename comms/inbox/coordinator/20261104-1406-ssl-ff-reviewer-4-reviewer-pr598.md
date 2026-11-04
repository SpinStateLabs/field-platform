# Reviewer report: PR 598 @ 30e7aada418cb8f370601af4b5e0dfea044876fb (force-gateway: DriftTracker refuses bad bounds at construction, scout S-2-15)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main 97dcfec1 (main is now b963407a; `git merge-tree --write-tree origin/main pr598` clean). 2 files (+85): force_gateway/drift.py (+15) and tests/test_drift_constructor_bounds.py (+70). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. Behaviour change at gateway start: `create_app` builds the tracker from `FORCE_HYGIENE_WINDOW`, `FORCE_HYGIENE_BAND` and `FORCE_HYGIENE_BASELINE_WINDOWS` (api.py:796-800 on main); a value of 0, a negative number, NaN or inf in one of them used to start the gateway and now stops it. The gateway is the LLM egress; "hygiene instrumentation keeps failing open" is its stated doctrine for runtime, while start-up refusal for a malformed number is already the documented behaviour for non-numeric values, so this extends an existing rule rather than breaking one. Still an availability trade the owner should know about.
2. docs/ENVIRONMENT.md rows 119, 120 and 123 on main say only "non-integer raises ValueError at app start" (and "non-numeric" for the band); after this PR a zero, negative, NaN or infinite value raises too, so the three rows understate the refusal. The PR does not touch the doc (LOW drift).
3. The checks refuse; they do not clamp. A stricter reading of S-2-15 might prefer clamping to a default with a warning; the PR chose refusal and says so ("refused here, not at record time"). Defensible, and the one that never silently changes a tuning.

## Verified
- Baseline on the exact head: tests/test_drift_constructor_bounds.py + the existing drift tests 42 passed (relative PYTHONPATH `../../packages/field-core/src:../../packages/field-agent/src:src`).
- Code read: `_is_int_at_least_one` rejects bool and anything not an int below 1; the band must be an int or float, not bool, finite and greater than zero; each message names the argument and never the value.

## Mutants (mutations of drift.py; scratch worktree on the head; baseline 42 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| W1 | integer check `>= 1` -> `>= 0` | 2 failed | yes |
| W2 | `>= 1` -> `> 1` | 3 failed | yes |
| W3 | bool accepted as an int | 2 failed | yes |
| W4 | float accepted for the integer arguments | 4 failed | yes |
| W5 | window_size not checked | 11 failed | yes |
| B1 | baseline_windows not checked | 11 failed | yes |
| B2 | window_size message names the wrong argument | 11 failed | yes |
| D1 | band: NaN/inf allowed (isfinite dropped) | 2 failed | yes |
| D2 | band: zero allowed (`<= 0` -> `< 0`) | 3 failed | yes |
| D3 | band: bool allowed | 1 failed | yes |
| D4 | band: strings allowed (type check dropped) | 4 failed | yes |
| D5 | band not checked | 13 failed | yes |
| M1 | message echoes the window_size value | 1 failed | yes |
| M2 | message echoes the band value | 1 failed | yes |
| M3 | message echoes the baseline_windows value | 1 failed | yes |
Totals counted from the table: 15 mutants, 15 killed, 0 survived (5 on the integer rule, 3 on the argument checks, 5 on the band rule, 3 on the no-echo rule; the groups overlap in the table only by label). No survivor to run against the suite. Not run: the other force-gateway suites.

## Findings
- F-S215-1 LOW: ENVIRONMENT.md rows for the three variables should say the new refusal (objection 2).
- F-S215-2 LOW: objection 1, the start-up trade; no change requested.

## Verdict: PASS on 30e7aada418cb8f370601af4b5e0dfea044876fb
Head frozen; LOWs go in a NEW PR. Merge clean against current main. CI green and the force-gateway suite on this exact head per the coordinator procedure. Not run by me: CI, GX10.
