# Review PR #842 (G26 repo side: Stage 3 plan notice + rollback rehearsal) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `cca160cd2e5608e024fe11e65e00bd7f0416bb49`.

## Facts (HIGH, read from the head)
- 1 commit (cca160cd); 2 files: tools/stage_controller.py (+8/-1), tools/tests/test_stage_controller.py (+86). Nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Tests: tools/tests/test_stage_controller.py 123 passed on the head (20 s).
- Production change: a `Stage.irreversible` field (default None) set only on Stage 3, and `plan` prints `irreversibility: ...` when it is set. No estate action, no flag, no change to steps, rollback tuples or gates, so the flags-off behaviour of Stages 1 and 2 is unchanged (their plan output has no new line; pinned by the test).

## Checked against the runbook
- Rollback order: STAGES[3].rollback = remove_require_flag, recreate_seven, recreate_killswitch matches runbook step 8 ("remove FIELD_OPERATOR_REQUIRE from .env, then recreate the seven FIRST and killswitch LAST"). The new rehearsal drives the controller through a stateful FakeEstate (each service takes its mode from the flag only when recreated), forces an abort at `recreate_eight`, and asserts: the run ends `aborted_rolled_back`, the flag is off, all eight services are log-only, the rollback steps run in that order, and the kill-switch is recreated last. A second test shows the fake is order-sensitive (flag removed last leaves every service in REQUIRE), so the first test can fail.
- Notice text vs the runbook "Irreversibility (todo.md row G)" (l.1661-1665): the runbook says an image rollback to a pre-G image is only safe while REQUIRE has never been set, accepted writes carry the authenticated id and key fingerprint permanently, roll back by unsetting FIELD_OPERATOR_REQUIRE first, never by image alone. The notice says the same in one sentence; "unavailable" is a little stronger than the runbook's "only safe while ... never been set".
- A Stage 3 plan without a go sentence refuses: `go_sentence_missing` for None, "" and whitespace (parametrised, exit 2).

## Mutants (mine, 13 hand mutants on tools/stage_controller.py, one at a time, file restored from backup; tree clean afterwards). Counted from the output: 13 RED, 0 survived.
Rollback: flag removal moved after recreate_seven; killswitch step dropped; killswitch first; seven dropped. Notice: Stage 3 irreversible None; "never by image alone" clause removed; "eight" changed to "seven"; print condition inverted; printed always; notice added to Stage 2; (note: my mutant 13, printing before steps, also printed "None" for stages 1 and 2 so it was red for that reason, not for ordering). Gates: Stage 3 go sentence not needed; Stage 3 clean-Stage-2 requirement removed.

## Minor (LOW, optional; new PR only, head is frozen after this PASS)
1. Stage 2 also sets `FIELD_OPERATOR_REQUIRE`, on the kill-switch; the runbook note says image rollback is only safe "while REQUIRE has never been set", which already fails after Stage 2 (accepted kill writes carry the authenticated id). The notice prints for Stage 3 only, and the test pins its absence from Stages 1 and 2. This matches the G26 card ("once REQUIRE is on all eight") so it is not a defect against the card; whether Stage 2 should carry a notice is Don's call.
2. `@pytest.mark.parametrize("broken", ["recreate_eight"])` has one value (the rehearsal covers one abort point; an abort at `set_require_flag` or `delete_override` is not rehearsed, though the generic abort tests exist).
3. The fake does not model the dependency that makes the kill-switch last (its registry PATCH is refused once the registry is under REQUIRE); the order is asserted as a list, not derived.

## Conditions
None.

## Not covered
Did not run against an estate; did not run the full tools/tests suite; did not rebase on current main.
