CORRECTION to the 1158 report: the S7 table row was garbled there; this copy has it fixed. Verdict and counts unchanged.

# Review PR 456 @ 77f0b8a296c33a69bef9d2654c4e8ec8f9ae0937 (C-1172, B-19 lint, rebuild of PR 445 + 449) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 77f0b8a2. UNVERIFIED (cloud, no GX10).

## Conditions
1. MERGE ORDER (HIGH, read from the allowlist): the allowlist in this PR lists `services/spend-governor/src/spend_governor/cli.py` (8 keys) and `services/federation-broker/src/federation_broker/cli.py` (3 keys). PR 462 (C-1179) and PR 464 (C-1181) remove exactly those sites. Whichever lands second makes `test_the_repo_matches_the_allowlist` fail with "stale allowlist entry". The later PR (or the coordinator's batch) must delete those lines. I did not run the combined tree; this is read from the files.
2. Coordinator: GX10 16/16 and CI on this head rebased on current main.

## Objections first
1. A lint whose scanner lives in the test file can be blind in places its own tests never look. Probed with 36 mutants of the scanner and allowlist.
2. The allowlist is a hand count of 40 uses; a drifting count fails both ways (L1-L5 kill).
3. Base is b39287c1; main is now 97dcfec1. A trial merge of this head into 97dcfec1 is clean and the lint file passes there (35 passed), with 462/464 not yet in main.

## Facts (HIGH)
- Head fetched via refs/pull/456/head = 77f0b8a2; 4 commits; author AND committer on all four are Don Hagell <13129187+dhagell@users.noreply.github.com>. Tests and an allowlist only; no code change.
- Baseline unmutated: lint file 35 passed, on the head and on the trial merge with main. Relative PYTHONPATH not needed (stdlib scanner).

## Mutants (mutated the scanner in the test file, or the allowlist; lint file run each time; files restored, worktree clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| S1 call shapes and aliases (S1a-f) | 6 | 6 | 0 |
| S2 operator_headers is a finding (S2a-c) | 3 | 2 | 1 (S2c) |
| S3 star import (S3a-c) | 3 | 2 | 1 (S3c) |
| S4 alias count, enclosing name (S4a-c) | 3 (S4a anchor failed, not run) | 2 | 0 |
| S5 duplicate allowlist key, comments (S5a-c) | 3 | 2 | 1 (S5b) |
| S6 new and stale reported (S6a-d) | 4 | 4 | 0 |
| S7 skips: test files, tests dir, home, conftest (S7a-e) | 5 | 2 (S7b, S7c) | 3 (S7a, S7d, S7e) |
| S8 scan roots (S8a-d) | 4 | 4 | 0 |
| L allowlist edits (L1-L5) | 5 | 5 | 0 |

Per-row sums: killed 6+2+2+2+2+4+2+4+5 = 29; survived 0+1+1+0+1+0+3+0+0 = 6. Totals COUNTED from the 36 listed rows: 29 KILLED, 6 SURVIVED (S2c, S3c, S5b, S7a, S7d, S7e), 1 anchor failure (S4a, not run, not counted as killed). 29 + 6 + 1 = 36.

## Survivors (the whole-suite run did NOT finish: my attempt hit its 500 s timeout and printed nothing; no result is claimed)
Grep of the head shows only this test file and its allowlist reference the lint, so no other test could kill them (read, not run).
- S5b duplicate summed: EQUIVALENT (the duplicate raises before the line runs).
- S7d home exemption in `scan_texts`: redundant with `python_files()`; effectively equivalent for the repo scan.
- F-R456-1 LOW-MEDIUM: `from field_core.operator_auth import *` is not pinned (S2c); the docstring claims it. Add a flag test.
- F-R456-2 LOW: after a star import, a later call is not counted separately (S3c).
- F-R456-3 LOW: skip by name (`test_*.py`, `conftest.py` outside a tests directory) is unpinned (S7a, S7e); no such file exists in scan roots today (find shows none). The docstring claims it, but no pin claim is made.
Optional LOWs go in a NEW PR; the head is frozen after this verdict.

## Not done
Whole `tools/tests` baseline was not run (collection needs service packages not installed in this venv); not counted.
