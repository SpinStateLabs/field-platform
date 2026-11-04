# Lane O reviewer: PR 605 (lifecycle-manager: a malformed roster is 422/503, not 500; junk interval warns; 60 s floor) @382c2c357c67c2e0cf660cc067e3d46603dbd209. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 382c2c35. Lane B (lifecycle). One commit (382c2c35), Don Hagell noreply (numeric form) as author and committer (git log, HIGH). The head is 1 commit behind origin/main (git rev-list --count pr605..origin/main); I did not test a merge. Files: lifecycle_manager/api.py +31/-4, two test files (+53 new, 4 changed), one ENVIRONMENT.md row. I did not write the head. Claimed through dispatch.sh (R-PR605-382c2c3).

Objections first: (1) the PR title is about roster errors, but it also adds a NEW behaviour that its own comment calls undecided: an interval read from the environment is raised to a 60 s floor ("proposed floor, Don to confirm", api.py MIN_ENV_EVERY_S). A deployment that today sets FIELD_LIFECYCLE_EVERY=30 would run every 60 s after this change; it ships with the roster fix, so the roster fix cannot land without the floor (read, HIGH). (2) the 422/503 body is `parse_roster`'s own message ("a line number, never content", per the new docstring); I did not verify that claim for every parse path (I do not know). (3) the ENVIRONMENT.md row IS updated for the new behaviour (ASCII digits only, WARNING, below 60 raised to 60) and `tools/environment_anchors.py --check` reports 0 wrong anchor row(s) on the head (run, HIGH): unlike PR 495, the docs match the code here.

Run here (cloud, scratch worktree on 382c2c35, relative PYTHONPATH of every service src and packages src plus the tests directory): the two touched test files 38 passed; whole lifecycle-manager suite 285 passed. NOT run: the 16-suite set, CI.

Mutants on lifecycle_manager/api.py (24 written; 1 did not apply and is excluded; 23 run in a scratch worktree; each against the two touched test files, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a malformed roster in the body is 422 with the parse message | 5 | 5 | 0 |
| B2 a malformed configured roster file is 503 (one more did not apply) | 3 | 1 | 2 |
| B3 an empty (owner-less) roster is still refused 503 | 2 | 0 | 2 |
| B4 the environment interval: ASCII decimal digits only, junk leaves the scheduler off | 5 | 4 | 1 |
| B5 a small environment interval is raised to the 60 s floor with a warning | 6 | 4 | 2 |
| B6 an explicit zero or negative interval stays off | 2 | 1 | 1 |
| Total (counted from the rows) | 23 | 15 | 8 |
B3 and B6 have 2 runnable mutants each (under the 4 asked).

Survivors (8): 2 equivalent, 6 real (4 distinct gaps):
- Equivalent (read, HIGH): `parse_roster(text) or []` (the result is only tested for truth); `every <= MIN_ENV_EVERY_S` instead of `<` (an interval of exactly 60 is raised to 60: the same value).
- F-O-pr605-1 MEDIUM (3 mutants): the refusal of an EMPTY roster is not pinned by any test in the whole suite: deleting `raise RosterUnavailable(...contains no owners — refusing an empty sweep)`, making the condition `if False`, or testing `owners is None` all pass. The code comment says an owner-less roster "would orphan every agent — refuse loudly", and this PR rewrote the lines around it (api.py `_resolve_roster`).
- F-O-pr605-2 LOW: `raw.isdecimal()` without `isascii()` passes: non-ASCII decimal digits (for example Arabic-Indic) are accepted by `int()` and would set an interval, although the PR's stated rule is ASCII digits only; the tests use superscripts and circled digits, which `isdecimal` already rejects.
- F-O-pr605-3 LOW: the floor WARNING can be removed unnoticed (the test asserts the raised value, not the log line).
- F-O-pr605-4 LOW: an explicit negative interval passed to create_app (not from the environment) maps to 1 second instead of 0 unnoticed (api.py `if every < 0`).

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main; I could not run it. C2 Don's decision on the 60 s floor (objection 1), recorded, or the floor split into its own PR.
Optional, NEW PR after the head is frozen: F-O-pr605-1 (the empty-roster test first), -2, -3, -4.

Tokens/cost line: not available to me. I do not know.
