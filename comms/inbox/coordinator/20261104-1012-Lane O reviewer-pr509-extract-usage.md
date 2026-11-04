# Lane O reviewer: PR 509 (scout P-12, field-agent tests: pin extract_usage and report_usage_from) @0a0d458b4d209450b1e3dd02704b639982a9ff69. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 0a0d458b. Lane A/B boundary (packages/field-agent). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); one new test file (+110), no source change. I did not write the head. Claimed through dispatch.sh (R-PR509-0a0d458).

Objections first: (1) the tests pin a meter that accepts nonsense counts: probe (run, HIGH) on the head: `extract_usage({"model": "m", "usage": {"input_tokens": -5, "output_tokens": True}})` returns `input_tokens: -5, output_tokens: 1` (a negative count and a boolean pass through `int()`); the docstring's rule "a guessed meter is worse than a loud one" covers missing counts only, and no test says what a negative or boolean count should do (usage.py:178-189). (2) `"12.5"` raises ValueError from int() with a message about base 10, not the module's own "cannot report" text, so a float-string count fails loudly but unhelpfully (probe, run, HIGH). (3) `test_report_usage_from_forwards...` replaces `agent.report_usage` with a spy by assignment, which depends on `report_usage_from` calling `self.report_usage` by attribute (read, HIGH).

Run here (cloud, scratch worktree on 0a0d458b, relative PYTHONPATH of every service src and packages src plus the package directory so `tests.conftest` imports): new file 21 passed. NOT run: the whole field-agent suite (no survivor needed it), the 16-suite set, CI.

Mutants on field_agent/usage.py and agent.py (26 run in a scratch worktree; each against the new test file; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a missing usage or model is a ValueError | 5 | 5 | 0 |
| B2 a missing token count is a ValueError, never a guessed zero | 5 | 5 | 0 |
| B3 cache read defaults to 0 and maps cache_read_input_tokens | 4 | 4 | 0 |
| B4 counts are int and the model is str | 4 | 4 | 0 |
| B5 a zero count is a real zero | 4 | 4 | 0 |
| B6 report_usage_from forwards the extracted fields and the note | 4 | 4 | 0 |
| Total (counted from the rows) | 26 | 26 | 0 |
No survivor: the strongest mutant table in this series so far; I note it as a small-surface result, not proof of the objection-1 case, which no mutant touches because no test sets the intent.

CONDITIONS (blocking): C1 CI green on the exact head; a tests-only PR may take a light GX10 run that says "tests only" (I could not run it). C2 a decision recorded on objection 1 (reject a negative or boolean count, or state that the governor does): the tests stay as written.
Optional, NEW PR only after the head is frozen: a test for a negative count and a boolean count once decided.

Tokens/cost line: not available to me. I do not know.
