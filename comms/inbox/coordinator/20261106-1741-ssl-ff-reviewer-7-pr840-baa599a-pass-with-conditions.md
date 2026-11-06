# Review PR 840 (stage_controller: build sha required live, per-stage baseline services, stage clean cleared by a later abort; RT-832 R1-R4) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `baa599aa3355d78c9599d2524939dc2c5f250feb`.
Conditions: C1 (one test, no code change): pin the literal service lists. Mutants R2f (`fedbroker` renamed to `federation`) and R2g (`lifecycle` dropped from the eight) pass the whole file, so a wrong or short list is invisible to the tests. C2 (operating, coordinator): the driver's `counters()` keys must equal these names (the PR says MEDIUM confidence); a mismatch makes every Stage 1/3 run abort as `health_failure` (fail closed, but it would roll back every attempt). C3: CI and GX10 on the head.

## Objections first
1. `Controller(expected_services=())` (an explicit empty tuple, for example from an empty driver config) now replaces the stage list with nothing: any non-empty baseline passes. The override is by design ("Controller(expected_services=...) overrides"), but an empty value silently turns R2 off, which is the fail-open the red team reported. Treat an empty override as the stage list, or refuse it (LOW-MEDIUM; mutant R2h shows the empty-baseline path is covered only through the stage list).
2. The service names are the compose names (registry, ledger, delegation, killswitch, governor, fedbroker, console, lifecycle), verified against the runbook (lines 1143, 1218, 1315, 1414: `SVCS="registry ledger delegation killswitch governor fedbroker console lifecycle"`). The Stage 0 check I reviewed (PR 836) labels the same service `federation`; a driver reading `/health` through proxy prefixes must map to the compose name here (HIGH, read).
3. R4 changes a safety property: a failed `stage_start` record now means no rollback runs. That is correct only if nothing was changed before that write; the code orders `stage_start` first, before the baseline and any step (read).
4. A stage-done window is still not time-checked (the PR says so; a driver duty).

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5; .github/: 0 files. 2 files (stage_controller.py +43/-13, test_stage_controller.py +70/-12). Based on main e125a878 (826 and 832 are in main).
- Code read against the red team re-review (RT-832-R1..R4): R1 a live run with `build_sha` None is refused `build_sha_required` and recorded as refused, nothing run, a dry-run plan unchanged; R2 `Stage.services` default (Stage 1 and 3 the eight, Stage 2 killswitch and registry) used when `expected_services` is None; R3 `stage_clean(n)` cleared by `abort`, `rolled_back` or `rollback_failed` of stage n or any LATER stage, not an earlier one, and rows with a non-int stage are skipped; R4 `stage_start` write failure sets `nothing_armed`, runs no rollback, records the abort and alerts, status `aborted_nothing_armed`. No defect found.
- Tests on the exact head (Windows): test_stage_controller.py 126 passed (PR: 126; 9 new).

## Mutants (23 attempted; counted from the table)
| # | mutant | result |
|---|---|---|
| R1a | live run without sha allowed | KILLED |
| R1b | refusal not recorded | KILLED |
| R1c | refusal reason renamed | KILLED |
| R1d | (textually a no-op, invalid) | not counted |
| R2a | stage 2 uses all eight | KILLED |
| R2b | stage 1 service list empty | KILLED |
| R2c | stage 3 service list empty | KILLED |
| R2d | override ignored | KILLED |
| R2e | stage list ignored (default empty) | KILLED |
| R2f | `fedbroker` -> `federation` | SURVIVED |
| R2g | `lifecycle` dropped | SURVIVED |
| R2h | empty baseline allowed | SURVIVED |
| R3a | later abort ignored | KILLED |
| R3b | an earlier stage's abort un-cleans | KILLED |
| R3c | later `rolled_back` ignored | KILLED |
| R3d | later `rollback_failed` ignored | KILLED |
| R3e | any stage's `stage_start` un-cleans | SURVIVED (near-equivalent: nothing reads the flag between a later start and its end) |
| R3f | non-int stage rows not skipped | NOT APPLIED (my search string missed) |
| R4a | nothing_armed not set | KILLED |
| R4b | nothing_armed still rolls back | KILLED |
| R4c | nothing_armed status wrong | KILLED |
| R4d | nothing_armed abort record dropped | SURVIVED |
| R4e | nothing_armed alert dropped | KILLED |
Totals: 23 attempted, 1 invalid no-op (R1d), 1 not applied (R3f), 21 applied: 16 killed, 5 survived (R2f, R2g, R2h, R3e, R4d); 16+5 = 21. R4d is a real LOW gap: the PR says "abort record and alert still sent" but only the alert is pinned.

## Optional LOWs (new PR)
Literal pin of the eight and of the Stage 2 pair; refuse or default an empty `expected_services`; pin the nothing-armed abort record; a note tying these names to the Stage 0 check's labels.

## Not verified
CI/GX10; Linux; a real driver and its `counters()` keys; the tools lint/stage tests the PR cites (228 passed there).
