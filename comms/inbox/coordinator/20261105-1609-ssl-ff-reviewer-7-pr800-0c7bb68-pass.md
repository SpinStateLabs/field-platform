# Review PR 800 (rebuild of 628, S3-7 field-agent CLI verb tests) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `0c7bb682853ea67df132c325e06b7a4c50084693`. Tests-only, no source edit.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. .github/: 0 files. Scope: packages/field-agent/tests/test_cli_verbs.py (+199).
- Rebuild fidelity: `git patch-id --stable` of the non-merge commit on #628 (3501390c) == the head commit (`f4c8d5d2640a`). Net diff vs main identical, 1 file +199 on both.
- Base: merge-base is 869cf2ed; origin/main is now 3804d0b9 (batch m3 landed), so the head is NOT rebased on current main. The file is new and disjoint from m3's files, so no conflict expected; merge-1/GX10 must rebase before the 16/16.
- Tests on the exact head (Windows, all package src on PYTHONPATH): 17 passed. The PR's note about one unrelated field-agent failure (canary subprocess, relative PYTHONPATH) was not re-run by me.

## Mutants (21 against cli.py, run on the 17 tests; counted from table)
| group | mutants | killed |
|---|---|---|
| heartbeat exit/JSON/stderr (H1-H3) | 3 | 3 |
| checkin killed/unreachable/halting text (C1-C4) | 4 | 4 |
| report-usage exit 3 rogue, exit 1 not metered, note, cache tokens, required model, defaults (U1-U8) | 8 | 8 |
| mint ttl default, error exit/prefix/stderr, scope repeat, granted-by required (M1-M6) | 6 | 6 |
Totals: 21 mutants, 21 killed, 0 survived (3+4+8+6 = 21). Every group has at least 3 mutants; every claimed behaviour is pinned.

## Notes (LOW, optional)
- The upstream-body non-echo test uses a MockTransport 403 against the real bootstrap.mint: good. `version`, `check` and `cross` verbs are out of this PR's scope and not covered here.
- Not verified: CI/GX10 on this head; Linux.
