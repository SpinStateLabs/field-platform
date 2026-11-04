# Reviewer report: PR 636 @ 67e347da50c215f8cfcb6f9ab243b298d662c184 (conformance-sentinel tests: scorecard gate boundaries and the vacuous false-block pass, S3-14)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Two commits on origin/main b963407a (the current tip): the test commit and "remove a stray empty file committed by mistake"; net diff is one file, services/conformance-sentinel/tests/test_scorecard_gate_boundaries.py (+111), tests only. `git merge-tree --write-tree origin/main pr636` clean. Author and committer of both = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 (HIGH).

## Objections first
1. The test file pins a FINDING as current behaviour: a run with no conforming seeds passes the false-block gate vacuously ("nothing was measured, the gate reads PASS"), and the docstring says a fix would be a separate card. Pinning a questionable behaviour makes a later fix a visible test change, which is intended; it also writes the questionable behaviour down as "expected". The coordinator should decide whether the vacuous pass is acceptable before relying on the gate.
2. The 0.95 and 0.02 gates are compared with floating point (`>=`, `<=`) on ratios like 19/20 and 2/100; the PR pins both exact boundaries and the markdown "allow at most" arithmetic for n = 1..60, 100, 150, 200, which covers the float edge for those sizes only.
3. Hand-built `SeedResult` lists test `compute_metrics` in isolation; they do not show the seeded run feeds it correctly (stated by the file: "not through the seeded run").

## Verified (run by me)
- Baseline on the exact head: tests/test_scorecard_gate_boundaries.py 71 passed (relative PYTHONPATH with every service's src; the test imports the registry through the seeded module); whole services/conformance-sentinel/tests 334 passed (pytest-xdist -n 4).

## Mutants (mutations of conformance_sentinel/measure.py; scratch worktree on the head; baseline 71 passed; kill = at least one failure in the PR's file)
| # | Mutant | Result | Killed |
|---|---|---|---|
| G1 | catch gate `>=` -> `>` | 6 failed | yes |
| G2 | false-block gate `<=` -> `<` | 5 failed | yes |
| G3 | CATCH_GATE 0.95 -> 0.9 | 11 failed | yes |
| G4 | CATCH_GATE 0.95 -> 0.96 | 2 failed | yes |
| G5 | FALSE_BLOCK_GATE 0.02 -> 0.03 | 2 failed | yes |
| G6 | FALSE_BLOCK_GATE 0.02 -> 0.01 | 2 failed | yes |
| G7 | gates_passed uses `or` | 4 failed | yes |
| G8 | gates_passed ignores the false-block gate | 1 failed | yes |
| R1 | zero denominator gives 1.0 | 3 failed | yes |
| R2 | zero denominator raises | 3 failed | yes |
| C1 | gated catch ignores the clause | 1 failed | yes |
| C2 | gated catch ignores the decision | 71 passed | NO |
| C3 | raw catch requires the exact decision | 71 passed | NO |
| F1 | false block also counts ESCALATE | 1 failed | yes |
| F2 | false block counts nothing | 64 failed | yes |
| F3 | conforming includes the ambiguous seeds | 71 passed | NO |
| S1 | skipped seeds are run | 1 failed | yes |
| S2 | skipped ids not listed | 1 failed | yes |
| M1 | markdown miss allowance uses round() | 31 failed | yes |
| M2 | markdown block allowance uses round() | 24 failed | yes |
| M3 | markdown miss allowance hard-coded 0.05 | 71 passed | NO (equivalent: 1 - 0.95 is not exactly 0.05 in float, but the test sizes give the same ints; see below) |
| M4 | markdown block allowance off by one | 63 failed | yes |
| E1 | false-escalate rate counts BLOCK | 1 failed | yes |
| K1 | routing coverage over all seeds, not the run ones | 71 passed | NO |
Totals counted from the table: 24 valid mutants, 19 killed, 5 survived (C2, C3, F3, M3, K1). Survivors against the whole conformance-sentinel suite (334 at baseline): F3 is KILLED there (2 failed, 332 passed); C2, C3 and K1 still pass 334 (run); M3 I did not run against the whole suite. On M3: `int(n * (1 - 0.95))` and `int(n * 0.05)` differ in float for some n; the test checks sizes up to 60, 100, 150, 200 and found no difference, so I call it equivalent for the tested sizes, not proven for all n (MEDIUM).

## Findings
- F-S314-1 MEDIUM-LOW: C2 and C3: the gate's catch rule is "decision AND clause" (pinned for the clause by C1) but a right clause with the wrong decision is not a test case, and the raw-catch rate (any would-be verdict) is not distinguished from an exact-decision rate. Add a seed whose would-be decision differs (ESCALATE where BLOCK is expected) and assert `gated_catch_rate` 0.0 and `raw_catch_rate` 1.0.
- F-S314-2 LOW: K1 (routing coverage denominator: run seeds vs all seeds) is unpinned even though a skipped-only test sets both to 0.0; add a mixed skipped and routed case.
- F-S314-3 LOW: F3 is covered by older tests; M3 as above.
- F-S314-4 note: objection 1, the vacuous false-block pass is a policy question for the coordinator, not a defect of this PR.

## Verdict: PASS on 67e347da50c215f8cfcb6f9ab243b298d662c184
Head frozen; LOWs go in a NEW PR. Tests only: CI green and the full GX10 run on this exact head per the coordinator procedure (not docs-only, so no light run). Not run by me: CI, GX10.
