# Delta review PR 719 (S6-19 deployment_agent journal) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `ab4117f85b151128dceb771f9530c4e2ff288196` (delta from reviewer-9's 68de8d35; their C1 first half, pin a malformed ack (mutant A2), is CLOSED. Their C2 and C3 stand).
Conditions: C1 (non-blocking) runbook sentence still owed (B-FU-PR719-runbook-repair): a hand-written torn_tail_ack un-halts; a halted line torn as the FINAL line is lost by design. C2 (decision for Don, unchanged from reviewer-9) whether a halted record needs a stronger guard than the torn-tail tolerance. C3 (standing gate) GX10 and CI on the landed head rebased on main; not run by me.

Independence: I did not build or fix this PR (7 commits, none mine).

## Checks (HIGH, run by me)
- Identity: the new commit ab4117f8 author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Delta 68de8d35..ab4117f8: one file, `tools/tests/test_deployment_agent_journal_shape.py` +23, tests only; `journal.py` is unchanged by the delta (the check is journal.py:125).
- Tests on exact head (Windows, py3.14, venv, from repo root): `test_deployment_agent_journal_shape.py` 57 passed (10 s). I did NOT re-run `test_deployment_agent_rotation.py` (reviewer-9 ran 390 passed at 68de8d35, 1,502 s; the delta touches no source).
- Trial merge (`git merge-tree`, worktree untouched) against current origin/main: clean (tree id only, no conflict).

## Mutants (4 on the new claim "a malformed or foreign ack excuses nothing"; counted from the table)
| # | mutant (journal.py:125) | result |
|---|---|---|
| M1 | `damaged_line in (damaged_at, None)` (reviewer-9's A2) | KILLED (new test `[missing]`) |
| M2 | `.get("damaged_line", damaged_at)` (missing key excuses) | KILLED (new test `[missing]`) |
| M3 | `str(...) == str(damaged_at)` (a string excuses) | KILLED (new test `[string]`) |
| M4 | `damaged_line is not None` (any non-null excuses) | KILLED, by the existing "names another line" test, not by the new one (the new `other-line` and `negative` ids also cover it) |
Totals: 4 attempted, 4 killed, 0 survived, 0 not applied. Tree restored and verified clean.

## New finding (own probe, HIGH on measurement, LOW severity, non-blocking)
Python equality makes two JSON values excuse a damaged line they should not: `damaged_line: 2.0` excuses damaged line 2, and `damaged_line: true` excuses damaged line 1 (`2.0 == 2`, `True == 1`). Probe on this head: both give no JournalError. The new parametrised test has no float or bool id, so it does not pin this. Same trust level as the forged ack reviewer-9 already measured (needs write access to the journal); the fix is `type(v) is int and v == damaged_at`, plus two ids. Fold into the C1 follow-up PR.

## Not verified
GX10 / Linux; CI; the rotation suite on this head; a real rotation; the rotator's behaviour on a JournalError beyond reading it.
