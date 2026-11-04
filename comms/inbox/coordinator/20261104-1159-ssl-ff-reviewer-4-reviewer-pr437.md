# Reviewer report: PR 437 @ 355c3cac58db30334cf0fecc3ba1ab04aee055e4 (C-1117)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Three files under tools/tests/ (+248/-1): the boundary-echo lint's rules (they live in test_boundary_echo_lint_c505.py, which is test code), a new corpus file test_boundary_echo_blindspots_c1117.py, and three allowlist entries. 9 commits incl. 2 merges of main; author and committer of all 9 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No production code changed (HIGH).

## Objections first
1. The lint and its tests change together in one PR (the rule is edited in the same file that tests it), so a wrong rule can be pinned by a test written to match it; mutation is the only independent check.
2. Three new real sites are added to the allowlist as "DEBT ... decision for the owner" (crosswalk regwatch._observe, force-gateway _authorize, lifecycle-manager scheduled_tick): the PR closes a blind spot by recording, not fixing, three reply echoes. That is a deliberate scope choice, not a defect, but each is an open decision.
3. The base is 05942b98, main is 97dcfec1; a conflict would have broken a stale head.

## Verified
- Head unchanged at 355c3cac. Baseline: test_boundary_echo_lint_c505.py + test_boundary_echo_blindspots_c1117.py = 127 passed (relative PYTHONPATH).
- Scratch merge of origin/main 97dcfec1 with this head (`merge-tree` clean, committed in a scratch worktree): the same two files pass 130 (HIGH). The real-repo scan therefore still matches the allowlist after main's movement.
- Diff read: new sinks (`secho`, `sys.stderr/stdout.write`, `logging.getLogger(..).<log method>`), `visit_Return` rule (a dict with a reply-field key over a tainted value, nested anywhere in the returned expression, not counted twice when it is an argument of a sink call).

## Mutants (scratch worktree on the head; baseline 127 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| M1 | `secho` dropped | 5 failed | yes |
| M2 | sys.stdout dropped | 2 failed | yes |
| M3 | `.write` -> `writelines` | 5 failed | yes |
| M4 | getLogger name check broken | 5 failed | yes |
| M5 | return-dict key test inverted | 16 failed | yes |
| M6 | sink-argument exclusion dropped (double count) | 2 failed | yes |
| M7 | taint test ignored (any value flagged) | 8 failed | yes |
| M8 | generic_visit dropped after the Return rule | 4 failed | yes |
| M9 | only top-level returned dict (no nesting) | 6 failed | yes |
| M10 | keyword args of sinks not excluded | 1 failed | yes |
| M11 | getLogger(..) rule removed | 5 failed | yes |
| M12 | allowlist: crosswalk _observe entry removed | 1 failed | yes |
| M13 | allowlist: force-gateway _authorize entry removed | 1 failed | yes |
| M14 | allowlist: lifecycle scheduled_tick entry removed | 1 failed | yes |
| M15 | allowlist: _authorize count 1 -> 2 | 1 failed | yes |
| M16 | floor MIN_SINKS 600 -> 700 | 1 failed | yes |
| M17 | PASS_METHODS: strip removed | 2 failed | yes |
| M18 | LOG_METHODS: exception removed | 3 failed | yes |
Totals counted from the table: 18 mutants, 18 killed, 0 survived. Every behaviour the PR claims to pin (new sink spellings, returned-dict rule, nesting, no double count, three allowlist entries, S1-S7 survivors, floors) has at least 4 mutants except the floors (1: M16) and the S1/S3/S7 equivalents, which the PR itself names as equivalent pins (not mutated by me). Survivors to run against the suite: none. I did not run the other suites.

## Findings
- F-C1117-1 LOW: the "returned dict inside a sink call is one finding" test exists twice (test_boundary_echo_lint_c505.py and the new corpus file's test_a_returned_dict_inside_a_sink_call_is_one_finding_not_two); duplicate coverage only.
- F-C1117-2 LOW (owner decisions, not blocking): the three new DEBT echoes above; a class-name-only reply would close each.
- F-C1117-3 LOW: the three Return-rule behaviours I could not tell apart from the sink rule on the real repo; the PR's "scan unchanged at 179" claim I did not re-measure (the scratch merge passes, which includes the allowlist agreement).

## Verdict: PASS on 355c3cac58db30334cf0fecc3ba1ab04aee055e4
Head frozen; LOWs go in a NEW PR. Merge is clean against current main. CI green and GX10 16/16 on this exact head rebased on current main per the coordinator procedure. Not run by me: CI, GX10.
