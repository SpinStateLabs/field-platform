VERDICT: PASS WITH CONDITIONS on 2282927fab5f586454477c1ce6acf8a514b39521  (ssl-ff-reviewer-9; Windows only, no GX10, CI not read)

R-PR778-2282927, PR 778 (S8-21, conformance-sentinel scorecard: failing ledger command and wrong-shaped verdict become MeasurementError). Applies to this head only.

OBJECTIONS FIRST
1. A failed "down" command is not cleaned up. `ledger_is_down = True` is set only AFTER `_toggle(ledger_toggle, True)` returns, so if the down command fails part-way (a TimeoutExpired is one of the PR's own parametrized cases: the process may already have stopped the ledger), the `finally` sees `ledger_is_down` False and never runs the up command: the estate's ledger can be left down. The PR pins the retry only for a failing UP. My mutant B5 (set the flag before the down call, so the finally retries) SURVIVES: neither behaviour is pinned. Pre-existing in shape (main raised raw from the same place), but the PR is the one that adds the "named failure" path and says the cleanup retries. MEDIUM.
2. The PR keeps `except Exception: pass` in the finally: a second failure of the up command in cleanup is silent, while the primary error is reported. After the retry fails, the operator is told "up command failed" once and nothing says the ledger may still be down. LOW.
3. Tightening: a falsy non-dict `context` (`[]`, `""`, `0`) used to read as `{}` and is now refused (stated in the PR). A target that returns `"context": ""` or `0` would now stop the whole scorecard run. Not checked against any real target's verdicts. LOW.
4. The CLI path (`except MeasurementError` → "measurement refused", exit 1) is asserted by construction only; the PR says it has no CLI-level test. I did not run the CLI. MEDIUM-LOW.
5. Base is 13 commits behind main; `git merge-tree` of main and the head is clean; the PR says it avoids cli.py (S3-13). HIGH.

ASSUMPTIONS
A1 The `from None` in `_toggle` is intended (hides the chained command text). A2 Only measure.py and one test file are in scope.

REASONING / CHECKS
1. Diff read: measure.py +35/-6 (a `_toggle` helper, `_wrong_shape`, `_as_dict`, three isinstance guards, two compute_metrics reads), +96 test; nothing under .github/. The error text names `type(exc).__name__` only. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONPATH = head src + field-core src, import path confirmed): new file 25 passed; new file + test_scorecard.py 33 passed, 0 failed. The PR's "sentinel suite 288 passed" I did NOT confirm: my full-directory run did not finish inside 9 minutes on this box (no failure seen in the dots printed, no final count). NOT VERIFIED.
4. Mutants on a copy of the head, new file first, then test_scorecard.py for survivors (a kill = pytest rc 1):

| id | mutation | result |
|----|----------|--------|
| B1 | down toggle called raw | KILLED |
| B2 | up toggle called raw | KILLED |
| B3 | message carries str(exc) | KILLED |
| B4 | only OSError caught in _toggle | KILLED (run by hand; the script run errored on a bad edit of mine) |
| B5 | down flag set before the call (cleanup would retry) | SURVIVED (new file and test_scorecard.py) |
| B6 | up flag cleared before the call | KILLED |
| B7 | verdict isinstance check removed | KILLED |
| B8 | context isinstance check removed | KILLED |
| B9 | would_be isinstance check removed | KILLED |
| B10 | falsy context read as {} (old behaviour) | KILLED |
| B11 | compute_metrics wb_decision uses raw `(would_be or {})` | KILLED |
| B12 | compute_metrics wb_clause uses raw `(would_be or {})` | KILLED |
| B14 | finally retry removed | KILLED |

Counted from the table: 13 run, 12 KILLED, 1 SURVIVED, 0 NOT APPLIED. Per behaviour: toggle-to-MeasurementError 4 (B1-B4), type-only message 1 (B3), cleanup/retry 3 (B5, B6, B14), wrong shapes 4 (B7-B10), compute_metrics tolerance 2 (B11, B12). The 4-per-behaviour bar is met for the toggle and wrong-shape groups. HIGH on the counts.

CONDITIONS
C1 (non-blocking, MEDIUM; new PR) decide and pin what happens when the DOWN command fails: set `ledger_is_down` before the call (so cleanup tries "up", which is harmless if already up) and add a test, or document that the operator must check the ledger. This kills B5.
C2 (non-blocking, LOW) say in the error text, or in the log, when the cleanup up-command also failed.
C3 (standing gate) GX10 16/16 on this exact head rebased on main, including the full sentinel suite (288 per the PR; I could not confirm it here).

NOT VERIFIED
The 288-test sentinel suite, the CLI exit-1 path, CI, GX10/Linux, real target verdict shapes (objection 3).

CONCLUSION
The change does what it says for every case the tests name: 25 + 8 tests pass, 12 of 13 mutants are killed. The one survivor is a real operational gap, a failed down command with partial effect, which leaves the ledger down and is not pinned. No blocking finding. PASS WITH CONDITIONS (C1, C2 optional; C3 gate). Head frozen except a condition fix.
