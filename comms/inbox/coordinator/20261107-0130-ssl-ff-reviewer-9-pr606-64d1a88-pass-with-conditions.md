VERDICT: PASS WITH CONDITIONS on 64d1a885a646501b419e6d5f048f97415e6b78f8  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). HIGH CARE: this is the policy enforcement point and I read the engine, not only the tests. Re-review of the condition fix for reviewer-8's PASS WITH CONDITIONS on 9bf0bc98. Both of their conditions (C1: a /status object without a known state fell through to ALLOW; C2: a truthy non-boolean `active` counted as active) are fixed and pinned. I found two further defects of the same family, one of which makes /check answer 500 with no verdict and no ledger row; neither blocks, both need a decision.

R-PR606-64d1a88, PR 606 (conformance-sentinel: upstream bodies of the wrong shape BLOCK with a named clause; scout S-2-22). Applies to this head only. The fetched pull/606/head is 64d1a885; 3 commits above main, author AND committer Don Hagell on all; base 97dcfec1 is 186 commits behind main and `git merge-tree` of the head into main is clean (tree id only). Nothing under .github/.

OBJECTIONS FIRST
1. The PR says "No reason added here echoes an upstream value (C-503)". True of the reasons it ADDED. But two existing sites still copy an upstream string into the verdict reasons, and I measured both with the PR's own harness on this head (marker string in the upstream body, in-process POST /check): a governor /status with state BLOCK, THROTTLED or ESCALATE and `detail` = a marker returns a verdict whose reasons are exactly the marker (marker_in_reasons True on all three); a delegation introspect with `active: false` and `reason` = a marker returns BLOCK D.token with the marker in the reasons. (engine.py lines 669, 678, 685: `spend.get("detail", ...)`; line 568: `intro.get('reason')`.) These verdict reasons go to the caller and to the ledger. MEDIUM-LOW (needs the governor or the delegation service to answer such text; both are internal), HIGH confidence (measured).
2. The same sites make /check raise when `detail` is not a string. With a /status of state BLOCK, THROTTLED or ESCALATE and `detail` = a dict, `5`, `null` or a list, the verdict build fails: 5 of my 9 status probes raised pydantic ValidationError ("1 validation error for ConformanceVerdict ... string_type") out of the app, which is a 500 over HTTP with no verdict and no ledger record: exactly the failure mode the PR sets out to remove for wrong-shaped bodies, one field over. A caller that treats a non-200 as deny stays safe; one that does not has no decision. MEDIUM, HIGH confidence (measured: BLOCK detail=dict, =5, =null, THROTTLED detail=list, ESCALATE detail=dict all raised; BLOCK without a detail and the string cases answered 200).
3. After the fix the engine reads two more unchecked values from the same bodies that cannot fail open but can fail loudly or echo: `spend.get("retry_after_seconds")` goes into the verdict context for THROTTLED without a type check, and `intro.get("status", "unknown")` selects the clause (an unknown value gives D.token, fail-closed). LOW.
4. The two reviewer-8 conditions are closed correctly by code I read: step 8 (and the judge-spend gate at engine.py ~326) refuse any `state` outside OK, ESCALATE, THROTTLED, BLOCK (BLOCK E.spend_cap / ESCALATE D.semantic with fixed texts, the judge never consulted); `active` must be exactly JSON true, else BLOCK with the specific clause kept (D.revoked for a revoked token, measured through the new tests). HIGH.
5. Not run by me: the whole sentinel suite (the builder also could not: each test takes 15 to 60 s here, hours in all). I ran subsets selected by name, below; a broken test elsewhere in the file is not excluded. NOT VERIFIED.

ASSUMPTIONS
A1 The probes use the PR's own helpers (govern, post, use_governor, intro) so the stack is the PR's, with the sentinel in enforce mode. A2 Reviewer-8's 8 mutants (O1 to O8: non-object accepted, decode error propagating, missing/bool/negative/float spent_cents, bare-string scope, non-string scope entries) cover code this delta does not touch and still hold; I did not repeat them.

REASONING / CHECKS
1. Delta read in full (9bf0bc98..head), engine.py: `_SPEND_STATES`; the judge-spend gate escalates on an unknown state; step 8 blocks E.spend_cap on an unknown state; `active` compared with `is not True`. Tests: +12 unknown-state bodies, four states with their exact clauses, 11 `active` values, 6 judge-budget bodies. HIGH.
2. Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 (one commit message carries the words "HIGH CARE" before its trailer, harmless). HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, every service src and field-core on PYTHONPATH): the four-governor-state tests 4 passed (baseline control); the unknown-state and active subsets pass inside the mutant runs (the failing ones are the killed mutants). HIGH on what ran.
4. Mutants on a copy of the head, engine.py, selected tests (-x, a kill = pytest rc 1; my first selection for N1, N7 to N9 caught only the four-state tests, so I re-ran those four with the unknown-state tests included and report the corrected results):

| id | mutation | result |
|----|----------|--------|
| N1 | step-8 unknown-state check removed | KILLED |
| N2 | judge-gate unknown-state check removed | KILLED |
| N3 | `active` truthy again | KILLED |
| N4 | THROTTLED missing from the state set | KILLED |
| N5 | ESCALATE missing from the state set | KILLED |
| N6 | OK missing from the state set | KILLED |
| N7 | state compared case-insensitively | KILLED |
| N8 | an unknown state returns ALLOW | KILLED |
| N9 | an unknown state answers D.token instead of E.spend_cap | KILLED |

Counted from the table: 9 mutants, 9 KILLED, 0 SURVIVED, 0 NOT APPLIED (a baseline row without mutation passed). HIGH.

CONDITIONS
C1 (required, small; a condition fix on the head) make the three upstream strings safe: reasons built from `detail` and `reason` only when they are strings (and bounded), else a fixed text; `retry_after_seconds` only when a non-negative number. Pin each with a body where it is not a string, and with the marker body, so objections 1 and 2 turn red.
C2 (decision for the coordinator) whether copying a short upstream `detail` into a reason is wanted at all (C-503 says no echo): replace with fixed texts per state.
C3 (standing gate) GX10 16/16 and CI on this exact head, including the whole sentinel suite; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
The whole sentinel suite on this head, GX10 / Linux, CI, the HTTP status the real service returns for objection 2 (I saw the exception in-process; FastAPI turns an unhandled one into 500).

CONCLUSION
reviewer-8's two conditions are closed: an object /status without one of the four exact states now BLOCKs E.spend_cap, a judge budget of unknown state escalates and never judges, and only a JSON true counts as an active token; 9 of 9 mutants die and the clause assertions tell the states apart. The same fail-loud family remains one field over: a non-string `detail` makes /check raise (500, no verdict, no ledger row), and three upstream strings still reach the verdict reasons. PASS WITH CONDITIONS: C1 required and small, C2 a decision, C3 the gate.
