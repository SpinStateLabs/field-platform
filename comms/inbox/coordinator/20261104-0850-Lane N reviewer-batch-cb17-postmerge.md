# Reviewer (read-only, post-merge, FALLBACK): MERGE 10 = batch cb17, main c4ac8c14 -> b5e98d8e (PRs 407 @e256e6b, 406 @a40e6da, 396 @2d830e9, 393 @91af42b, 378 @1519000, 377 @4292a6a; 11 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `b5e98d8e`.** Queue was EMPTY, so this is the ROLE-LOOP fallback. Scope of my mutation work is partial and stated below.

## Record checked (HIGH, from git and gh)
- 11 commits (STATUS: 11), a fast-forward, 0 nonconforming identities (Don Hagell noreply, author and committer). All six PRs CLOSED, CI SUCCESS 7/7 on each head.
- A reviewer PASS naming each head found: 407 (c1075), 406 (c1055), 396 and 378 (c1053), 393 and 377 (c1076). Verifier A report `20261101-2008-gx10-verifier-A-batch-cb17.md` found and names the batch (2 matching lines; its 16/16 wording not re-read here, MEDIUM).

## What the batch is
Mostly docs (ntfy runbook, capstone hardening evidence, soak steps, v1.2 deploy runbook) and two test files: `tools/tests/test_renew_token_ledger_helpers_c1042.py` (17 tests, pins production helpers in `tools/renew_token.py`) and `tools/tests/test_boundary_echo_lint_c505.py` (58 tests, a lint whose logic lives inside the test file) with a 120-line allowlist.

## Objections first
1. Docs commits rewrite what is "current" versus "history" in evidence files: they have no behaviour to mutate, and I did not re-verify their sentences against code (not done).
2. The boundary-echo lint is a security lint with an allowlist; an allowlist can hide a real echo. I ran the 58 tests (pass) but did NOT mutate the lint or audit the 120 allowlist rows (not done): that part of the batch has 0 mutants from me.
3. The renew_token tests run with `PYTHONPATH=tools` only: they assume field_core is NOT installed, so a run with `packages/field-core/src` on the path fails 2 of them (environment-dependent, by design of what they pin).

## Measured (GX10 ~/ff-work/wt-cb17 at b5e98d8e, python -B, own venv)
`test_renew_token_ledger_helpers_c1042.py`: 17 passed with `PYTHONPATH=tools` (2 failed when field-core src was also on the path, as objection 3 says); `test_boundary_echo_lint_c505.py`: 58 passed.

## Mutants (29 rows run on `tools/renew_token.py`; source restored, worktree clean; 1 anchor did not match and was not run)
| Behaviour | Killed | Survived |
|---|---|---|
| A1 the repo copy is appended, never prepended | 4 | 0 |
| A2 an installed field_core leaves the path alone | 3 | 1 (INVALID: my anchor also matched an unrelated `is not None: return` earlier in the file) |
| A3 the root is the checkout beside tools | 3 | 1 (gap: `os.getcwd()` instead of the file's own location passes, because the tests run with the repo root as cwd) |
| L1 the signer is loaded once | 4 | 0 |
| D1 a failed signing counts and names only the class | 3 | 1 (gap: counting 2 per failure passes, because the test only looks for `dropped_ledger_appends=2` as a substring in the output of two failures) |
| U1 an unavailable signer names the class, an unusable key is said | 4 | 0 |
| B1 a blank identity or key is not set, naming the variable | 5 | 0 |
Totals counted from the table: killed 4+3+3+4+3+4+5 = 26; survived 0+1+1+0+1+0+0 = 3; 29 rows. 1 survivor is my invalid mutant, 2 are real gaps.

## Conditions
- C1: none blocking (merged; record complete).
- C2: the boundary-echo lint and its allowlist need a mutation pass by a reviewer with time (objection 2); until then that claim is unreviewed by mutation.

## Findings (non-blocking; new PR only)
- F-cb17-1 LOW: after two failed signings assert the LAST message says `=2`, not that `=2` appears somewhere (D1).
- F-cb17-2 LOW: run the root test with a different cwd so `os.getcwd()` fails it (A3).
