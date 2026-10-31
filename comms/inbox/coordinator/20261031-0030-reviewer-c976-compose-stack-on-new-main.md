VERDICT: PASS WITH CONDITIONS on fae8cc0a2d7ea8f051d0f43c403d89860943e1d8 (PR 391, whose stack contains PR 385 at 112cf16 and PR 387 at d4902a0)

Reviewer Lane 15, cloud-reviewer, C-976, against main acaf5f2. UNVERIFIED: no GX10, CI not read; scratch-tree rebase and tests.

## Objections first
1. As they stand, none of the three merges cleanly: merge-tree of each head against main acaf5f2 reports 4 conflicting files (tools/compose_bind_rules.py, tools/compose_resolved_check.py, tools/tests/test_compose_resolved_bind_c512.py, tools/tests/test_compose_static_pins.py) for PR 385, PR 387 and PR 391 (HIGH, run).
2. The conflicts are the duplicate of PR 328's commit, not new disagreement: main carries the same patch (patch-id equal) under a new id (acaf5f2) and the stack still carries the old copy (7679259). A rebase onto main drops the duplicate automatically: rebasing PR 391 onto acaf5f2 succeeded with no conflict and left 8 commits (the 9 minus the duplicate), 10 files changed against main (+1277/-47) (HIGH, run).
3. The tests do make sense on top of 328: on the rebased tree the seven compose test files (wiring, static pins, bind, c638, c715, c823, c817) pass: 1054 passed (HIGH, run). Each earlier PR in the stack is a prefix of 391's stack, so 385 and 387 rebase the same way (their rebased heads are earlier points of the same sequence) (HIGH, reasoned from the commit order; I rebased only 391).
4. The resolved-model check is still NOT a gate: the header says so and the runbook step (PR 391) says nothing in the repository or CI runs it (HIGH, C-945).

## Does each still merge cleanly? Which is partly redundant?
| PR | head | merges clean vs main now | after rebase | what is now redundant |
|---|---|---|---|---|
| 385 | 112cf16 | NO (4 files) | yes (prefix of 391's rebase) | its copy of 328's commit (dropped by rebase); nothing else: realpath roots, text checks, exit 3 are not on main |
| 387 | d4902a0 | NO (4 files) | yes | same duplicate; the top-level text rule is new |
| 391 | fae8cc0 | NO (4 files) | yes (probed) | same duplicate; copy-alone guard, bridge message and runbook note are new |
Everything above 328 in the stack is new relative to main; only the base commit duplicates what main has. The earlier stack members 345, 353, 370 (not in this card) have the same duplicate and conflict the same way (merge-tree: 345 two files, 353 four, 370 four).

## Conditions
1. Rebase the stack (345, 353, 370, 385, 387, 391) onto main; do not merge the heads as they are. Blocking for merge.
2. Re-run the compose tests and the whole tools suite on the rebased result; the seven compose files passed here, the whole suite was not run.
3. Close PRs 386 and 389 (BZ and BZ2): both are copies of what is on main.

Not verified: CI, GX10, the rebase of 385 and 387 individually, the whole tools suite.
