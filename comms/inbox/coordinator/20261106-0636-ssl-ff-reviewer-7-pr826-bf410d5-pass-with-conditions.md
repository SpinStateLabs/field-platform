# Review PR 826 (stage_controller fail-closed: G24 red team F-816-1/2/3) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `bf410d51add668d0541507046414565be0a3900a`.
This code is the automatic rollback for production arming, so I read it as fail-closed first. The code is right where tested; conditions are one missing pin and one operating condition.
C1 (one test, no code change): pin that a records failure while writing `rollback_failed` still sends the "ROLLBACK FAILED ... act by hand" alert (mutant M7 survives; see below). C2 (operating, coordinator): F-816-3 is only half closed by default; the driver that builds `Controller` must pass `expected_services` (the eight), or a non-empty baseline that names only some services still judges only those. Plus the usual CI and GX10 on the head.

## Objections first
1. `expected_services` defaults to empty and the only constructor in the repo (`tools/stage_controller.py:366`, `Controller(records)`) passes none: today an empty baseline is refused, but a baseline missing seven of eight services is accepted, so the red team's F-816-3 ("require the expected services") is not enforced anywhere until a driver passes them. The PR flags this itself (HIGH, read).
2. A second interrupt (or one arriving during rollback) is not handled: the rollback loop in `_abort` catches `Exception`, and `_abort` is called outside the guarded region, so a KeyboardInterrupt during a rollback step propagates mid-rollback with no `rolled_back` record and no alert. By reading only, not run (MEDIUM).
3. `_record` swallows write failures silently: a lost `abort`, `rollback_step` or `rolled_back` row leaves no trace in `Result` or an alert, so an audit gap is invisible (the PR's own design; LOW-MEDIUM).
4. A failed `stage_done` write rolls back a stage that was fully armed. Conservative by design and stated in the PR; the operator should expect it.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer: none. .github/: 0 files. 2 files (stage_controller.py +48/-20, test_stage_controller.py +77). Base == current main ede21674.
- Code read against the red-team report (20261106-0230, F-816-1/2/3): every records write in a live run goes through `Controller._record` (never raises); stage_start/step_done/stage_done failures return CONTROLLER_ERROR and roll the stage back; abort/rollback_step/rolled_back/rollback_failed failures no longer skip the rest of the rollback; `except BaseException` mid-stage records the condition, rolls back once, then re-raises the original interrupt (after the rollback, not before); an empty baseline is HEALTH; `expected_services` missing from the baseline is HEALTH. Dry-run path unchanged.
- Tests on the exact head (Windows): `test_stage_controller.py` 101 passed (PR: 101; 18 new).

## Mutants (18 on stage_controller.py vs test_stage_controller.py; counted from the table)
| # | mutant | result |
|---|---|---|
| M1 | stage_start failure ignored | KILLED |
| M2 | step_done failure ignored | KILLED |
| M3 | stage_done failure ignored | KILLED |
| M4 | abort record unguarded | KILLED |
| M5 | rollback_step record unguarded | KILLED |
| M6 | rolled_back record unguarded | KILLED |
| M7 | rollback_failed record unguarded | SURVIVED |
| M8 | BaseException -> Exception | KILLED |
| M9 | interrupt swallowed, not re-raised | KILLED |
| M10 | interrupt: no rollback | KILLED |
| M11 | empty baseline allowed | KILLED |
| M12 | expected_services ignored | KILLED |
| M13 | any -> all (expected_services) | KILLED |
| M14 | _record swallow returns True | KILLED |
| M15 | _record never guards | KILLED |
| M16 | re-raise before rollback | KILLED |
| M17 | baseline read error -> CONTROLLER_ERROR | KILLED |
| M18 | expected_services default non-empty | KILLED |
Totals: 18 mutants, 17 killed, 1 survived (17+1 = 18).
M7 is the one that matters: if the records file also fails at the moment a rollback fails, an unguarded write would raise before the "act by hand" alert. The code is guarded; no test would notice if it were not.

## Not verified
CI/GX10; Linux; the tools lint/stage/public/secret suites the PR cites (748 passed there; I ran the stage controller file only); the interrupt-during-rollback path (objection 2) and a real driver.
