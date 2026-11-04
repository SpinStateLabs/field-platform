# Report: S-C4 (scout round 3), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or note for retention-metric shapes.
PR 519 (draft): https://github.com/SpinStateLabs/field-platform/pull/519, branch fix/retention-metrics-wrong-shape-sc4, head bf80c86c37729d3f0e33df2061e93990139f3b03 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane B: attestation).
Bug (R, 17 red tests): _retention_metrics indexed .get on whatever /retention/check gave for offending/unresolvable; a wrong shape lost the WHOLE board pack out of build(). Fix: each must be a list of records (the file's own _non_records) else the count metric is unavailable with a fixed note, policy figure still published. Well-formed, empty, missing and None unchanged. `False`/0/"" still read as empty via the existing `or []` (not changed).
19 tests; attestation-reporter 274 passed; anchors --check 0 wrong; one mutant 17 red.
Not run: other suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513, 514, 517, 518, 519; none merged by me.
Round 3 not yet taken: S-C2, C3, C6, C7, C8; docs/CI S-D1..D8.
