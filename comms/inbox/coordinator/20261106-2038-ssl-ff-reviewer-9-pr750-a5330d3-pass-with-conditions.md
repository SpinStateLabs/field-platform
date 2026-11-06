VERDICT: PASS WITH CONDITIONS on a5330d3a6239e3ca3b6607d31d11ade7caaeb888  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for reviewer-3's PASS WITH CONDITIONS on 6bdbb4c9. The three findings are fixed; the one remaining condition is a merge conflict with current main.

R-PR750-a5330d3, PR 750 (S7-25, sealed-ledger POST /export bad out_dir and path echo). Applies to this head only. gh pr view 750 confirms the live head.

OBJECTIONS FIRST
1. The head no longer merges cleanly: `git merge-tree --write-tree origin/main <head>` reports CONFLICT (content) in docs/ENVIRONMENT.md (api.py and tools/tests/boundary_echo_allowlist.txt auto-merge). The base is ebb027a2, 60 commits behind main. reviewer-3 found it clean when main was 8 ahead. The conflict is in the anchor rows that cite sealed-ledger api.py line numbers; the repo rule is to re-run `python tools/environment_anchors.py --fix` after a rebase instead of hand-merging. Because api.py also auto-merged with main's changes, the anchors need a re-check after the rebase, not just a text merge. HIGH.
2. Mutant M9 (the OSError branch logs str(exc)) SURVIVES here on Windows (14 passed), although reviewer-3 killed it on Linux. Cause: the test asserts `str(tmp_path) not in caplog.text`, but a Windows OSError text shows the path in escaped form (doubled backslashes), so the plain path never matches and the assertion is vacuous on this platform. The code is correct (`type(exc).__name__` only); the pin is platform-dependent. MEDIUM-LOW.
3. Mutant M15' (the 422 detail echoes the first 50 characters of out_dir) SURVIVES: the only no-echo assertion is `len(r.text) < 400`. A full echo of the 4097-character case would fail, a short echo would not. LOW.
4. The condition-fix commit touches tests only (+10/-2 in test_export_route_failures.py); api.py is byte-identical to the head reviewer-3 reviewed (git diff 6bdbb4c9..head: only that test file). HIGH.

ASSUMPTIONS
A1 reviewer-3's mutant list (M1-M18, A1-A4) is the baseline; I re-ran my own 15-row list against the new head and relied on reviewer-3 for the ENVIRONMENT.md/allowlist mutants (A1-A4), which I did not repeat.

REASONING / CHECKS
1. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. Nothing under .github/ (the PR's file list has none). HIGH.
2. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): test_export_route_failures + test_export_bundle + test_422_no_echo_sealed_ledger_c1114 + test_operator_auth_g_sealed_ledger = 124 passed, 0 failed. tools: test_boundary_echo_lint_c505 61 passed; test_environment_doc + test_environment_anchors_c1116 98 passed; `environment_anchors.py --check` on the head: 0 wrong anchor rows. HIGH.
3. Reviewer-3's three findings, each re-checked by a mutant on a copy of the head (new test file only, -x, a kill = pytest rc 1):

| finding | mutant | result |
|---------|--------|--------|
| F1 (MEDIUM) ValueError log carries str(exc) | M12b | KILLED |
| F2 (LOW) ValueError log removed | M12 | KILLED |
| F3 (LOW) bound constant changed to 4097 | M3 | KILLED |

4. Full mutant table on the head (own list, one script):

| id | mutation | result |
|----|----------|--------|
| M1 | route check removed | KILLED |
| M2 | `>=` bound | KILLED |
| M3 | MAX_OUT_DIR = 4097 | KILLED |
| M5 | lone-surrogate check removed | KILLED |
| M7 | OSError detail is str(exc) | KILLED |
| M8 | OSError log removed | KILLED |
| M9 | OSError log carries str(exc) | SURVIVED (Windows, objection 2) |
| M10 | ValueError branch removed | KILLED |
| M11 | ValueError detail is str(exc) | KILLED |
| M12 | ValueError log removed | KILLED |
| M12b | ValueError log carries str(exc) | KILLED |
| M13 | OSError status 503 | KILLED |
| M13b | ValueError status 502 | KILLED |
| M15' | 422 echoes first 50 characters | SURVIVED (objection 3) |
| M16 | ValueError log text changed | KILLED |

Counted from the table: 15 run, 13 KILLED, 2 SURVIVED, 0 NOT APPLIED (my NUL-check mutant M4 did not apply because of a quoting slip; reviewer-3 killed it on the unchanged code). HIGH.

CONDITIONS
C1 (merge) rebase or cherry-pick onto current main, run `python tools/environment_anchors.py --fix`, then re-run the four sealed-ledger files and the three tools files above; a conflict resolution in the merge vehicle is the merge writer's, no push to this PR head is needed.
C2 (non-blocking, LOW; new PR) make the OSError log pin platform-independent (assert on the exception text from a known OSError, e.g. compare against `str(exc)` rather than `str(tmp_path)`), and assert the 422 text equals the fixed message exactly (kills M15').
C3 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me.

NOT VERIFIED
GX10 / Linux, CI, the rebased result, reviewer-3's allowlist and anchor mutants (A1-A4).

CONCLUSION
The condition fix does what the builder says: M12, M12b and M17 are now dead, tests-only change, identity correct, 124 + 159 tests pass. The head now conflicts with main in docs/ENVIRONMENT.md and needs the standard anchor re-fix in the merge. PASS WITH CONDITIONS (C1 merge conflict, C2 optional LOWs, C3 the gate). Head frozen except a condition fix.
