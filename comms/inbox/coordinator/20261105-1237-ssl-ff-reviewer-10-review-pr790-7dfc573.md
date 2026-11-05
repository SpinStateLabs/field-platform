# Review PR #790 (start_role_session: a failed kickoff keeps the session id; name validated, S8-32, stacked on #595) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `7dfc5737690e56cafc3da5673af956152229edd9` for the residual commit only (the parent 37cec4cf is the head of the OPEN PR #595, reviewed separately; this PR is stacked, merge order #546, #595, then this). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 2 commits above the main merge-base: 37cec4cf (#595's head, not reviewed here) and 7dfc5737 (this PR). Residual diff: tools/start_role_session.py (+19/-4), tools/tests/test_start_role_session_orphan_id.py (+112). Nothing under .github/. Both commits author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Behaviour: the session id is written to stderr as soon as the session exists (before the kickoff call); a SystemExit from the kickoff `call()` is re-raised as `session <id> was created but not started: <existing fixed message>` (no upstream body, the #595 rules hold); stdout still carries only the id on success; `session_name` must fullmatch `[A-Za-z0-9_-]{1,64}` at argparse time (exit 2, before any request). The session id is not a credential (it is the handle the operator needs to stop a billable session).
- Tests: tools/tests/test_start_role_session_orphan_id.py with the #546/#595 test files: 71 passed on the head (41 s). The PR's "lints 199 pass" not run by me.
- Not changed (author discloses): the unit of `--budget-cents`/`max_list_cost.amount` is unknown (not in source).

## Mutants (start_role_session.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | stderr id line removed | RED |
| M2 | stderr id printed after the try (moved/removed before kickoff) | RED |
| M3 | kickoff SystemExit not wrapped | RED |
| M4 | name length limit 65 | RED |
| M5 | `fullmatch` to `match` | RED |
| M6 | '.' allowed in names | RED |
| M7 | exit line omits the id | RED |
| M8 | success `print(sid)` removed | RED |
| M9 | name validator not attached | RED |
| M10 | exit line repeats the id | equivalent (harmless), not counted |
| M11 | `[\w-]` (Unicode word characters) | RED |
Totals counted from the table: 10 real mutants, 10 RED, 0 SURVIVED; 1 equivalent excluded.

## LOWs (optional, new PR)
1. The module still carries workspace agent ids in a public repo (pre-existing in the stacked base, not introduced here); the ROLE-LOOP rule forbids estate addresses and credentials, ids are neither, so note only.
2. If #595 changes during its own review, re-check that the residual still applies (the head SHA above is pinned to 37cec4cf as parent).
