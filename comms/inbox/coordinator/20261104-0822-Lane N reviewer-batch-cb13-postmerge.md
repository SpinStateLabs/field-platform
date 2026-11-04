# Reviewer (read-only, post-merge): batch cb13 = MERGE 8, main 9468b184 -> 9addf44f (PRs 401 @8796131, 403 @1dd2b37, 404 @de74b3b)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `9addf44f`** (full PR heads: 401 `8796131529e902a4fdfd2d8b3a54fa07299e4b69`, 403 `1dd2b3703a09cb53d40edca8e779dfb6bba0a419`, 404 `de74b3b0b50bad1a26a713d686843228dab2a4c0`). The dispatcher said no reviewer file names batch cb13; this is that file. Tests only.

## Record checked (HIGH, from git and gh)
- 3 commits, 9468b184..9addf44f, all Don Hagell noreply author and committer. Each batch commit is patch-id identical to its PR head (`git patch-id --stable`: 54789212 = PR 404 9e6e5bc24b30; adffd963 = PR 403 2b1ab940de3b; 9addf44f = PR 401 6458d433018c).
- Per-PR PASS on the exact full heads exists: PR 401 and 403 in 20261031-1816-reviewer-c1054.md, PR 404 in 20261031-1752-reviewer-c1055-tests-prs-387-388-404-406-407.md. Verifier B 16/16 on 9addf44f: 20261101-1836-gx10-verifier-B-batch-cb13.md (names the sha, says 16/16). PRs 401, 403, 404 CLOSED with a pointer comment each, CI SUCCESS 7/7 on each head. 9addf44f is an ancestor of origin/main.

## Objections first
1. A strengthened assertion is only worth what it kills; the earlier reviews attacked helper refactors but I re-ran mutants against the production code each new assertion claims to pin.
2. `EXPECTED_RULE` (C-1046) is a hand-copied table "read off the refuse list on 2026-10-31": it can drift from the code, but the test fails on drift, which is its job.
3. C-1044 (one helper for the comment-skip line in test_yaml_duplicate_keys) is a refactor of a test helper: I did not mutate it.

## Measured (GX10 ~/ff-work/wt-cb13 at 9addf44f, python -B, own venv)
The 6 changed test files together: 438 passed, 1 skipped, 0 failed. The 16-suite is the verifier's report, not mine.

## Mutants against production code (23 rows; source restored, worktree clean)
| Claim | Killed | Survived |
|---|---|---|
| C-1045 `S.pivot` hit asserted on clause, detail and lines (clauses.py:172) | 6 | 0 |
| C-1045 `S.escalate-on-block` hit asserted on clause, detail and lines (clauses.py:206, :199) | 6 | 0 |
| C-1046 each refused kind names its rule (refuse.py) | 5 | 1 (the R03 message at refuse.py:87 is reached only with a `secret_class`; the tests refuse by kind and hit the :75 message: unpinned) |
| C-1046 a resolved manifest is the one written (clients.py) | 4 | 1 (my mutant was a no-op: invalid) |
Totals counted from the table: killed 6+6+5+4 = 21; survived 0+0+1+1 = 2; 23 rows.
Not mutated: the sealed breakglass row pin in test_operator_auth_format2.py (C-1046 part) and the C-1044 helper refactor, so those two claims have 0 mutants from me (below the 4 required).

## Conditions
- C1: none blocking (already merged, record complete).
- C2: a reviewer with `operator_auth` knowledge to add 4 mutants for the breakglass row pin; otherwise note it as unreviewed by mutation.

## Findings (non-blocking; new PR only)
- F-cb13-1 LOW: refuse.py:87 R03 message (secret_class path) has no rule-id pin.
- F-cb13-2 LOW: the two un-mutated pins above.
