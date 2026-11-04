# Lane O reviewer: PR 503 (scout P-21, force-gateway: the hygiene judge refuses a NaN, infinite or non-number score) @5f38e6317910ef04f14e70033117d3626093560a. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 5f38e631. Lane A (force-gateway). Two commits on main cd3b7690 (contains main: yes): the fix and a docs re-anchor of docs/ENVIRONMENT.md; both Don Hagell noreply as author and committer (HIGH). Source change: hygiene_judge.py +5 lines in `clamp`; test file +79. I did not write the head. Claimed through dispatch.sh (R-PR503-5f38e63).

Objections first: (1) the fix makes a NaN or non-number score an ERROR (`HygieneJudgeError`), so one bad judge reply loses that judgment entirely; the caller's handling of that error (log, skip, retry) is outside this PR and I did not trace it (I do not know). It is the right direction (a NaN `premise_rigor` used to clamp to 1.0, perfect rigor, per the code comment) but it trades a wrong score for a missing one. (2) integer scores 0 and 1 are accepted and returned as `float(x)`; a bool is refused (read, HIGH). (3) Python's json.loads accepts the literals NaN and Infinity, so the guard is the only thing standing between a model reply "NaN" and a perfect score (read, HIGH; confirmed by the test parametrisation).

Docs commit: `python tools/environment_anchors.py --check` on the head: 0 wrong anchor row(s) (run, HIGH). The three moved anchors (hygiene_judge.py:170, :116, :181) belong to the +5-line shift.

Run here (cloud, scratch worktree on 5f38e631, relative PYTHONPATH of every service src and packages src): new file 33 passed; whole force-gateway suite 481 passed. NOT run: the 16-suite set, CI.

Mutants on hygiene_judge.py `clamp` and the judgment build (25 run in a scratch worktree; each against the new test file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 NaN or infinity is an error, not a clamped score | 5 | 5 | 0 |
| B2 a bool, string, None, list or dict is an error | 5 | 4 | 1 |
| B3 a finite out-of-range score is still clamped to 0..1 | 4 | 4 | 0 |
| B4 integers 0 and 1 are numbers (returned as floats) | 4 | 3 | 1 |
| B5 the error text names the exception class only | 4 | 2 (both by older tests) | 2 |
| B6 a well-formed reply is returned as is | 3 | 2 | 1 |
| Total (counted from the rows) | 25 | 20 | 5 |
B6 has 3 mutants (under the 4 asked).

Survivors (5): 3 equivalent, 2 real LOW pin gaps.
- Equivalent (read, MEDIUM): allowing None through `clamp` (the following `float(None)` raises and is wrapped into the same error); a `{x!r}` in the inner ValueError text (the outer handler reports the class name only, so the value never reaches the message); `except HygieneJudgeError: pass` (that branch is not reachable from inside the try).
- F-O-pr503-1 LOW: the returned score's TYPE is unpinned: dropping `float(...)` returns int 0 or 1 for an integer score; `HygieneJudgment` is a dataclass, so the int is kept as an int (hygiene_judge.py clamp).
- F-O-pr503-2 LOW: the 300-character cap on `rationale` is unpinned (cutting it to 30 survives).
- Weak pin (not a survivor of the whole suite): the PR's own `test_the_error_text_names_the_class_only` kills NEITHER error-text mutant; only older tests do (0 of 4 B5 mutants killed by the new file), so the new test does not guard the property its name states.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 objection 1 recorded: what the caller does with a HygieneJudgeError, one line.
Optional, NEW PR only after the head is frozen: F-O-pr503-1/2 pins; make the error-text test fail when the message carries the exception text.

Tokens/cost line: not available to me. I do not know.
