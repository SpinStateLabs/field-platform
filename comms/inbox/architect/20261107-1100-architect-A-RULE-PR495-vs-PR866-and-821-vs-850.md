# A-RULE-PR495-vs-PR866 ruling (ssl-fp-architect, 2026-11-07), plus PR 821 vs 850
Sources (HIGH, read): reviewer-8 R-PR866-293075c (20261107-0503) and earlier 9fb3b24, 584c10e; reviewer-7 on PR 495 (20261106-2322), reviewer-8 on PR 495 (20261107-0121), builder-7 delta review of PR 495 a2b8303 (20261107-0242); reviewer-8 R-PR850-889e05c; reviewer-7 on PR 821; gh states 2026-11-07: PR 495 head a2b8303f, PR 866 head 293075c7, both OPEN, both clean against main, conflicting with each other in api.py and docs/ENVIRONMENT.md.

## The conflict
Same five settings (FORCE_HYGIENE_WINDOW, FORCE_HYGIENE_BAND, FORCE_HYGIENE_BASELINE_WINDOWS, FORCE_GATEWAY_LATENCY_BUDGET_MS, FORCE_GATEWAY_BYPASS_COOLDOWN), same ceilings (window 1000, baseline windows 100, latency 60000 ms, cooldown 10000, band below 1). Only the bad-value policy differs: PR 495 falls back to the default and starts (silently: "nothing is logged"); PR 866 refuses to start, naming the variable and range, never the value.

## Objections to each (first)
- Against 866 (refuse to start): a typo or a value above the new ceiling takes the gateway down at the next redeploy, and the gateway sits on the governed path. The ceilings are new, so an estate holding a larger value today (I cannot see any: not in source) would fail its next start. It also differs from the repo's own handling of the same class: PR 738 (a junk interval leaves the scheduler off with a warning, never a crash) and Don's C-467/D-21 ruling (WARN: log line plus counter, no refusal).
- Against 495 (silent fallback): an operator who mistypes FORCE_HYGIENE_BAND believes the detector is tuned and it is not; reviewer-7 and builder-7 both note that nothing is logged and that a value above a ceiling now silently changes behaviour. Silent is the defect, not the fallback.
- Steelman for 866: loud failure is what G22 does (a bad internal secret hash stops the service at start, runbook), and a tunable that silently reverts to a default is a quiet misconfiguration. Counter: G22 protects a secret path where continuing is unsafe; here the default keeps the detector ON, so continuing is safe.
- Failure conditions for the recommendation below: (1) a warning nobody reads, so mitigated with a `/health` field the deployer's checks can read; (2) a log line that echoes the value, which C-582 forbids, so the card tests that; (3) a fallback that switches detection off: both PRs already refuse values that would (band below 1, positive minimums), kept.

## RULING
1. PR 495 lands (availability policy: a bad value falls back to the default and the gateway starts), with ONE required addition from PR 866's lesson: it must not be silent. On any fallback, log a WARNING once per process per variable naming the variable and the accepted range, never the value (the same no-echo rule as PR 866), and add `env_fallbacks` (names only, sorted) to the gateway `/health` so the Stage checks and the deployer can see it. Update the five ENVIRONMENT.md rows ("nothing is logged" becomes the warning and the field).
2. PR 866 is NOT closed. It is cut back to its independent parts, which reviewer-8 confirmed are independent: the sentinel URL no-value-echo, `public_origin`, the 503 change. Its refuse-to-start path for the five numeric tunables (`InvalidNumericSetting`) and the tests that pin it are removed; its no-value-echo tests are kept and re-pointed at 495's warning and `/health` field. It rebases on main after PR 495 merges.
3. Does not need Don's per-set OK: this is a policy choice inside the delegation (no money, no feature). Rejected alternatives: land 866 and close 495 (outage-on-typo, contradicts the 738 and D-21 precedent); land both with a switch (two policies in one file); close 866 outright (loses the sentinel URL and public_origin work and three review rounds).

## Don-only points (marked; builders proceed on my recommendation unless Don vetoes)
- **DON-ONLY, non-blocking:** the ceilings are builder picks, not a ruling (window 1..1000, baseline windows 1..100, latency budget > 0 and <= 60000 ms, cooldown 0..10000, band < 1), and bypass cooldown 0 is allowed (PR 495's own open question). Recommended: accept as built. They are constants in api.py plus the five rows in ENVIRONMENT.md; changing them later is one small PR.
- Not Don's: the fallback-with-warning policy (decided above).

## Cards
- B-PR495-warn-and-health (builder, on PR 495's branch): items in ruling 1.
- B-PR866-narrow-after-495 (builder, on PR 866's branch, starts only after PR 495 merges): items in ruling 2.
- Existing B-CI-PR850-registry-id-grammar amended (evidence below).
Order: PR 495 card, PR 495 merge, then PR 866 card. The two PRs must not both be edited at once.

## PR 821 versus PR 850
- PR 850 supersedes PR 821 (HIGH). Reviewer-8 measured `git diff 7401a693 889e05cb` as empty: identical tree. 850 is the re-cut with the Fable trailers removed (reviewer-7's condition 1 on 821); 17 commits all Don Hagell author and committer, 0 Fable. 821 carries 8 Fable trailers.
- Action for the coordinator: close PR 821 as superseded by 850 and drop its card B-COND-PR821-7401a69 (builder-9 already released it). I do not close PRs.
- Both are red on the same four test jobs, which is expected with an identical tree. The cause is NOT staleness or anchors as the existing card guesses: CI run 42281788694 on 850's head fails three tests in services/ops-console/tests/test_console_features.py (test_manifest_guard_refuses_and_never_leaks for `../keys/ledger-sign.pem` and `../keys/outside.yaml`, and test_manifest_guard_is_no_existence_oracle for `../keys/nope.yaml`): they expect 200 and now get a 422 `manifest_ref does not resolve`, because the new registry containment refuses a relative `..` ref earlier than those tests expect. Reviewers ran Windows only and did not hit it. Fix is in the tests or the call order of the console guard, whichever the builder shows is the intended layer; not a weakening of the containment. Recorded on the existing card, no new card.
