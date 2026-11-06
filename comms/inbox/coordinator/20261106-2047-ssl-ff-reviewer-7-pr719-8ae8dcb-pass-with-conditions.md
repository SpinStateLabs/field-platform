# Review PR 719 (S6-19: deployment_agent journal fails closed on a transition with an unreadable state) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `8ae8dcbda6b479416db0ac6add22cbbb46d376c0`.
The change does what it says for the case it names. Condition C1 (code, small, HIGH importance): the same fail-open the PR describes still exists for a HALTED line that is corrupted into NON-JSON. I reproduced it on this head (below): the halted run resumes. C2: CI and GX10 on the landed head.

## Objections first (the reason for C1)
1. The PR's own argument ("a corrupted line that was the HALTED transition would vanish, `is_halted()` would be False and a halted rotation could run again: a silent fail-open on the one record that must stop it") applies to every way that line can be damaged, but only the valid-JSON-with-a-bad-state case is closed. A non-JSON line is still skipped and counted in `torn_lines`, whatever its position. Reproduction (the real `Journal` on this head): journal planned -> minted -> installed -> halted, then the halted line truncated by 5 bytes. Result: `is_halted()` False, `pending()` returns the `installed` state, and `transition(State.VERIFIED)` is ACCEPTED, i.e. the halted run is resumed. Same result when a later valid line follows the damaged one (variant "mid": a `note` after it). No code consumes `torn_lines` except the `seq` counter (grep of tools/: only journal.py), so the counter is never acted on.
2. A torn write can only be the FINAL line (the module docstring: "a crash leaves at worst a torn final line"). A non-JSON line with any valid line after it cannot be a crash tear, so it is corruption and should be treated like the case this PR fixes: raise `JournalError`. A non-JSON final line stays skipped (the crash case; resuming from the last good state is the intended recovery there).
3. As the PR says, the rotator's `_locked` does not catch `JournalError`, so a corrupt journal surfaces as an exception from `rotate()` (it was a bare KeyError/ValueError before); converting it to a halted `RotationResult` is a follow-up.

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. 2 files: tools/deployment_agent/journal.py (+11/-1), tools/tests/test_deployment_agent_journal_shape.py (+136). Based on ebb027a2; main is 250154d3; a trial merge into current main is clean.
- Code read: `entries()` now numbers physical lines and, for a valid-JSON object whose `event` is `transition` and whose `state` is not exactly one of the `State` values (missing, null, int, list, object, empty, wrong case), raises `JournalError` with a fixed text naming the line number and never the content; non-transition events are not judged; non-object lines are counted torn. `pending()`, `is_halted()`, `last_transition()` and `append()` all go through `entries()`, so all raise the same error, and `append()` writes nothing.
- Tests on the exact head (Windows): test_deployment_agent_journal_shape.py plus test_deployment_agent_rotation.py 370 passed together (the PR says 369; one more case after the second commit).

## Mutants (12 attempted; counted from the table)
| # | mutant | result |
|---|---|---|
| J1 | guard removed (old behaviour) | KILLED |
| J2 | guard only for a missing state | KILLED |
| J3 | any string counts as a readable state | KILLED |
| J4 | state compared case-insensitively | KILLED |
| J5 | `str(value)` accepted | SURVIVED (equivalent for JSON input: no non-string JSON value stringifies to a state name) |
| J6 | every event judged, not only transitions | KILLED |
| J7 | events containing "transition" judged | KILLED |
| J8 | error without the line number | KILLED |
| J9 | error echoes the state value | KILLED |
| J10 | line number counts non-empty lines only | NOT APPLIED (search string missed; the PR's second commit pins physical line numbers) |
| J11 | non-object lines not counted torn | KILLED |
| J12 | skip-and-count instead of raise (the card's first option) | KILLED |
Totals: 12 attempted, 11 applied, 10 killed, 1 survived, 1 not applied (10+1+1 = 12). None of them exercises C1: no test places a NON-JSON line before a valid line, or a damaged halted line, which is the gap.

## Optional LOWs (new PR)
Convert `JournalError` in `_locked` to a halted `RotationResult`; have `append()` or the rotator refuse when `torn_lines > 0` on anything but the final line.

## Not verified
CI/GX10; Linux; a real rotation on an estate.
