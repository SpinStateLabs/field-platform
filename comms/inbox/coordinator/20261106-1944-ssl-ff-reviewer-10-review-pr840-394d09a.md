# Review PR #840 (stage_controller: RT-832-R1 to R4 plus reviewer-7's conditions) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `394d09aaa576ad53de4c858a0735dfbb8dca79b0`. Reviewer-7's PASS WITH CONDITIONS on `baa599aa3355d78c9599d2524939dc2c5f250feb` (comms/inbox/coordinator/20261106-1741-ssl-ff-reviewer-7-pr840-baa599a-pass-with-conditions.md) is read; its conditions are checked below.

## Facts (HIGH, read from the head)
- 2 commits (baa599aa, 394d09aa); 2 files: tools/stage_controller.py (+43/-13 then +13/-3), tools/tests/test_stage_controller.py (+130 net). Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Tests: test_stage_controller.py 148 passed on the head (27 s).

## Red team findings vs the code (comms/inbox/coordinator/20261106-1000-red-team-rereview-826-827-832-817.md)
- R1 (sha binding opt-in): a live `run` with `build_sha` None records `refused build_sha_required` and raises Refused before any step; the dry-run plan is unchanged. Fixed.
- R2 (`expected_services` defaulted to empty): each Stage now carries `services` (Stage 1 and 3 the eight compose names, Stage 2 killswitch and registry); the baseline must name them; `Controller(expected_services=...)` overrides. Fixed.
- R3 (a Stage 3 rollback left Stage 2 "clean"): `stage_clean(n)` is cleared by an abort, rolled_back or rollback_failed of stage n or any LATER stage, and by a new start of stage n; rows whose stage is not an int (or is a bool) are skipped. Fixed.
- R4 (rollback ran on an untouched estate after a failed `stage_start` write): `stage_start` is the first write, before the baseline and any step; its failure sets `nothing_armed`, no rollback runs, the abort is recorded, one stage_aborted alert is sent, status `aborted_nothing_armed`. Fixed.

## Reviewer-7's conditions and objections, on this head
- C1 (pin the literal service lists): added; `test_the_service_lists_are_pinned_literally`, plus each of the eight names required in Stage 1 (parametrised), the Stage 0 label `federation` not satisfying the baseline, and a driver naming exactly the list completing each stage. Closed.
- Objection 1 (an empty `expected_services` override turned R2 off): an empty override (`()`, `[]`, `""`) now means the stage list (`names or None`); a name that is not one of the eight compose names (including `federation`, `fed`, `Registry` and a bare string such as `"registry"`, which splits into characters) raises ValueError("... compose names ..."). Closed, and tested.
- R4d (the nothing-armed abort record was not pinned): the new assertion pins that one abort row for stage 2 is written. Closed.
- C2 (operating): a driver's `counters()` keys must equal the compose names, or every Stage 1 or 3 run aborts as `health_failure` (fail closed). Still true by design; it is now tested for the `federation` label and refused loudly for an override. Coordinator to confirm the real driver; I did not see it.
- C3: CI and the GX10 run on this head are the coordinator's gate.

## Mutants (mine, 15 hand mutants on tools/stage_controller.py, one at a time, file restored from backup; tree clean afterwards). Counted from the output: 14 RED, 1 SURVIVED.
RED: `fedbroker` renamed `federation`; `lifecycle` dropped from the eight; empty override read as no check; unknown-name refusal removed or inverted; Stage 2 list reduced to killswitch; a later abort no longer un-cleans; build sha not required live; nothing_armed not set; nothing-armed abort record dropped; nothing-armed alert dropped; stage list and override swapped; a new start of the same stage no longer un-cleans; Stage 1 list emptied.
SURVIVED 1: the guard that skips non-int stage rows replaced by a bare None check. With that mutant, a record row whose stage is a string would raise TypeError in `stage_clean` (`at >= stage`). That would stop the run (fail closed), not allow it; no test feeds such a row.

## Minor (LOW, optional; new PR only, head is frozen after this PASS)
1. Add a records row with a non-int stage (a string, a bool, None) to a `stage_clean` test.
2. The Stage 2 pair (killswitch, registry) is pinned by a literal, but nothing in the repo states why registry is in it; a one-line comment would help the next reader.
3. Stage-done windows are still not time-checked (the PR says so; a driver duty).

## Not covered
Did not run against a driver or an estate; did not run CI or the GX10 gate; did not check the Stage 0 tool's labels beyond reviewer-7's note; Linux; did not rebase on current main.
