VERDICT: PASS WITH CONDITIONS on d320e840204eaae9f110d4b8a886299e5e218e78  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). HIGH CARE (policy enforcement point). Re-review of the condition fix for my PASS WITH CONDITIONS on 64d1a885. My required C1 (a non-string upstream `detail` made /check raise: 500, no verdict, no ledger row; upstream strings reached the reasons) is fixed and re-measured. The head conflicts with main in engine.py, but the conflict is one import line, which I resolved in a scratch tree and tested.

R-PR606-d320e84, PR 606 (conformance-sentinel: upstream bodies of the wrong shape BLOCK with a named clause; scout S-2-22). Applies to this head only. The fetched pull/606/head is d320e840: one commit over the head I reviewed (engine.py +29/-5, tests +62). Nothing under .github/.

OBJECTIONS FIRST
1. The head does not merge cleanly with current main: `git merge-tree` reports CONFLICT (content) in engine.py. Cause: main now carries PR 802 (the ledger-drop counter, commit 117469db), which also edits the import block. I ran the merge in a scratch worktree (never pushed): the only conflict is the import lines (`import math` from this PR against `import logging` from main), and the resolution is to keep both. On that merged tree the PR's tests plus main's drop-counter test file give 144 passed (test_upstream_body_shapes.py and test_ledger_drop_counter_sc9b.py), and the judge budget-status subset 6 passed. So the conflict is mechanical, but whoever lands this must resolve it; no one has. HIGH (measured). MEDIUM operationally.
2. Upstream text is still copied into the verdict reasons, now only when it is a non-blank string and cut to 200 characters (the `detail` of a BLOCK, THROTTLED or ESCALATE status, and the `reason` of an inactive token). Measured on this head with the PR's harness: a marker string in `detail` or `reason` still appears in the reasons; a 5000-character `detail` or `reason` is cut (reasons 200 and 216 characters); a `detail` with newlines, an ANSI escape and a right-to-left override arrives in the reasons with those control characters intact. So the decision I raised (C2: replace with fixed texts, C-503 says no echo) is open, and control characters in a reason can reach a ledger row, a terminal or a log. MEDIUM-LOW, HIGH confidence (measured).
3. The fix of my C1 holds, re-measured: for every non-string `detail` I tried (dict, 5, null, a list, the empty string, whitespace) the verdict is HTTP 200 with the fixed text ("cap reached", "rate limit exhausted", "threshold crossed"); `retry_after_seconds` reaches the context only as a finite, non-negative number (a negative, a string, 1e999 and True all gave None; 30 gave 30); an inactive token whose `status` or `reason` is a dict or list gives BLOCK D.token (200); a revoked token still gives D.revoked. HIGH.
4. Mutant T2 (the inactive-token `status` not cut to the bound) SURVIVES the PR's tests: a 5000-character status string passing through uncut is not pinned (in my probe the unmutated code does cut it, reasons 216 characters). LOW. HIGH.
5. The whole sentinel suite was not run by me (hours here); the PR's new tests and main's drop-counter tests ran (item 3 of the checks). NOT VERIFIED.

ASSUMPTIONS
A1 The probes use the PR's own harness (govern, post, intro) with the sentinel in enforce mode; I removed my probe file afterwards. A2 My scratch merge was committed nowhere; its only edit is the import line.

REASONING / CHECKS
1. Delta read in full: `MAX_UPSTREAM_REASON_CHARS = 200`; `_upstream_text(value, fallback)` returns the string (cut) only when it is a non-blank str, else the fallback; `_retry_after(value)` returns a number only when it is not a bool, is an int or float, is finite and is not negative; the inactive-token path coerces a non-string `status` to "unknown" before it picks the clause and cuts the text; the three governor detail reads and the retry context go through the helpers. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests: on the merged scratch tree (D:/venvs/field-mcp-l1, PYTHONUTF8=1, every service src and field-core on PYTHONPATH): tests/test_upstream_body_shapes.py plus tests/test_ledger_drop_counter_sc9b.py 144 passed, 0 failed (37 minutes); tests/test_judge.py -k budget_status 6 passed. HIGH on what ran.
4. Mutants on a copy of the head, engine.py, the new tests (selected by name, -x, a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| U1 | a non-string value used as the reason | KILLED |
| U2 | bound 2000 | KILLED |
| U3 | bound 199 | KILLED |
| U4 | a blank string kept | KILLED |
| U5 | the string not cut | KILLED |
| U6 | the fallback ignored | KILLED |
| R1 | a bool retry accepted | KILLED |
| R2 | a negative retry accepted | KILLED |
| R3 | an infinite retry accepted | KILLED |
| R4 | a string retry accepted | KILLED |
| R5 | a zero retry refused | KILLED |
| T1 | the non-string status guard removed | KILLED |
| T2 | the inactive-token status not cut | SURVIVED |
| T3 | the reason fallback replaced by the raw reason | KILLED |
| D1 | the spend BLOCK detail read raw again | KILLED |
| D2 | the THROTTLED detail read raw again | KILLED |
| D3 | the ESCALATE detail read raw again | KILLED |
| D4 | the retry value put in the context raw | KILLED |

Counted from the table: 18 run, 17 KILLED, 1 SURVIVED (T2, a real boundary gap), 0 NOT APPLIED. My previous report's nine mutants (state set, unknown state, `active`) are unchanged code and were not repeated. HIGH on the counts.

CONDITIONS
C1 (required at landing) resolve the conflict with main in engine.py: keep both imports (`logging` and `math`), re-run the two test files above on the result; a condition fix is the only push allowed on the head.
C2 (decision for the coordinator, carried) copy no upstream text into the reasons (fixed text per state); if text is kept, strip control and format characters before use and pin it. Add a test for T2.
C3 (standing gate) GX10 16/16 and CI on this exact head, including the whole sentinel suite; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
The whole sentinel suite on this head, GX10 / Linux, CI, the real HTTP status for an unhandled error (no longer reachable in my probes).

CONCLUSION
My required condition is met: no non-string upstream field I tried raises out of /check any more, the retry value is typed, and an inactive token with an odd status or reason is a D.token BLOCK; 18 mutants (17 killed), 144 and 6 tests pass on a merged scratch tree, identity correct. Left: a one-line import conflict with main that needs resolving at landing, upstream strings still (bounded) in the reasons with control characters unstripped, and an uncut-status boundary test missing. PASS WITH CONDITIONS: C1 at landing, C2 a decision, C3 the gate.
