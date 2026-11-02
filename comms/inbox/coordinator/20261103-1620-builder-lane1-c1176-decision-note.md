# Lane 1 report: C-1176 decision note (field-mcp batch: what goes before, what goes after)
Evidence: Lane 7 Q-70 (20261101-1245-reviewer-q70.md) on PR 380 head 24d5482b. C-1175 (the PR 368 verdict) has not reported; its conditions are not listed here. Read from the report, not re-run.

DECISION (recommendation, the coordinator rules): keep the default. F-Q61-1 and F-Q61-2 go in a new PR from main AFTER the batch lands. Land the batch (PR 368 then PR 380) as it stands once C-1175 passes and GX10 is 16/16.
Why: Q-70 says none of the open items blocks the merge, none is a hostile-input hole in the id or operator-pair invariants, and the merge carries all of 368's fixes. Both are fail-closed or consistency defects, not leaks.
Caveat I could not settle (UNVERIFIED): F-Q61-2 gives the model "internal error" after a 2xx send that the outcome row records as ok (reproduced at JSON depth 1,100 and 5,000, not at 990). If a model retries on "internal error" and the write route is not idempotent, that is a double-write risk. I did not measure either half. If the coordinator or Don wants no such window at landing, F-Q61-2 is the one item to pull before the batch; F-Q61-1 (a leading or trailing space in the operator id or key passes the header check, so writes append rows, send nothing and say "outcome unknown; do not retry") stays after in either case.

Remaining non-blocking conditions of Q-70, proposed as follow-up cards (counts and ids only):
- A. Production fixes with tests: F-Q61-1, F-Q61-2.
- B. Tests only: F-Q61-4 (assert the offending value), M51 (trailing-newline path id through the dispatcher), M03 (Tier 1 refusal wording), M57 (quote wire form), F-Q65-3, -4, -5, -6 and constants M68, M83, M84, M82 (pins; behaviour correct today).
- C. Production: F-C775-3 (no overall reply deadline; a byte-dripped reply returned ok after 13.2 s against a 10 s read timeout).
- D. CI: F-C775-4 (`--require-hashes` after an unhashed field-core install, ci.yml lines 36 and 45).
- INFO, no card: F-Q61-5 C6, F-Q61-6, F-Q61-7; 16 of 86 hand mutants survived (7 equivalent, 9 real pin gaps, all in card B).
C-1175 conditions: pending that verdict. I take card A first if the coordinator opens it, after C-1177.
