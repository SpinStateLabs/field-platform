# Report: C-1147 (Lane R). Draft PR 487, head ce2876e4bb4d7042685de05b0a8ece2944191a02. Author "needs review"; not reviewed, no GX10 run, CI not yet seen.

PR: https://github.com/SpinStateLabs/field-platform/pull/487 (draft), branch `fix/c1147-retired-key-narrow-rule`, one commit on main cd3b7690, Don Hagell noreply as author and committer. HIGH CARE, key handling, made-up keys only; no estate value.

## Rule (Don, 2026-11-02, card line 1182)
A key retired at any generation below the highest generation seen is refused when seen again at that highest generation; same-generation re-reads and rollbacks re-issued at a higher generation keep working.

## Answer to my earlier question (branch target)
New branch and PR from main, not on PR 355's own branch: PR 355 (head 640e1bd1, draft, tests only) was not pushed to. It is not stacked on 355 either; main has the code the rule changes. If 355's tests overlap, the reviewer or coordinator folds them.

## Change (operator_auth.py `_apply_retired_memory`, +14/-3)
A load that is a new highest generation clears its own keys from the retired table (a re-issue is live again). Any retired key still present is then in a file at or below the highest generation, so it is refused alone (403, never 503). The old refusals are a subset of the new ones.

## Measured (Windows, repo venv, relative PYTHONPATH, PYTHONUTF8=1)
- Bug reproduced by the new test on main cd3b7690: 41/42/43 rotation A, B, C; a second generation-43 file holding A is accepted (HIGH, run).
- New file `packages/field-core/tests/test_operator_retired_key_narrow_rule_c1147.py`: 8 tests; on main 1 red (the bug), 7 green (guards for the behaviours the ruling keeps); with the change 8 green.
- With the change: new file plus existing retired-memory tests 184 passed; whole `packages/field-core/tests` 1552 passed, 2 skipped; boundary-echo, environment anchors/doc, http-proxy and topology lints plus operator plumbing 560 passed, 1 skipped; `tools/environment_anchors.py --check` 0 wrong rows.
- Hand mutants (restored after each): old rule 1 red; never clear on a new high 3 red; clear on every load 3 red; `>=` for new high 3 red; refuse nothing 3 red; retire at generation-1 SURVIVES (equivalent: the stored generation now only orders cap eviction at MAX_RETIRED_HASHES).

## Not done / uncertain
- GX10 16-suite and CI: not run or not seen. The card says "16-suite result in a note": that needs Merge Assistant 1 or a verifier run on ce2876e4.
- Not exercised: the services that call operator_auth (kill-switch, registry) beyond the field-core suite and the lints above; a reviewer should name any they want.
- Per-process memory resets on a restart (Declared in the code comment), so the rule only covers one process's history; unchanged.
- The retired-key counter `operator_retired_hash_seen` now counts a refusal at the high generation as a sighting (once per path, hash, generation); alert rules reading it may see one more event per such file. Not measured against an alert rule.

## Process
I claimed C-1147 when Don said "take a card"; the claim file 20261104-1000-rebase-builder-claim-C-1147.md was first (no earlier claim). Held: C-1174 (R4b). PR 469 (C-1182) already landed in batch s2q.
