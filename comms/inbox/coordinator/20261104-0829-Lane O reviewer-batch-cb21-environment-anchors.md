# Lane O reviewer: batch cb21 = MERGE 14 (main 32b6eaa3 to 1d11c5e7; PR 432 environment_anchors.py, C-1116), read-only re-audit of the merged code. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; the batch is already on main), naming the merged head 1d11c5e7. Lane A (tools). Two commits, 49948328 (tools/environment_anchors.py +186, tests/test_environment_anchors_c1116.py +180) and 1d11c5e7 (one ENVIRONMENT.md anchor), both Don Hagell noreply as author and committer (HIGH). This is the FALLBACK review of a merged batch with no reviewer note naming it as a batch; STATUS MERGE 14 cites Lane 7 C-1121 PASS and Lane 17 PASS WITH CONDITIONS on PR 432; I did not read those reports and do not repeat them. Claimed through dispatch.sh (R-BATCH-cb21). I reviewed the code as merged at 1d11c5e7; current main has a longer file (207 lines) from later changes that I did not review.

Objections first: (1) `--fix` moves an anchor to the nearest code line naming the variable; for a variable read in two places it silently picks one, and a wrong-but-valid move passes `--check`, so the tool proves the anchor names the variable in code, not that it is the FIRST read the column promises (read, HIGH). (2) the tool is only as good as its own tests: 16 of 45 mutants below survive the PR's tests. (3) on current main `python tools/environment_anchors.py --check` reports 0 wrong anchor row(s) (run, HIGH).

Run here: the new test file 16 passed on the merged head; tools/tests/test_environment_doc.py 62 passed (the older weaker rule, the survivor cross-check). NOT run: the 16-suite set, CI.

Mutants on tools/environment_anchors.py (46 written; 1 did not apply and is excluded; 45 run in a scratch worktree on 1d11c5e7; each against the new test file, survivors against test_environment_doc.py; no syntax-broken kills. A first pass wrongly counted 16 survivors as killed by a test file that does not exist at this commit; I caught it from the unmutated baseline and re-ran, the table below is the corrected run):
| Behaviour | Mutants run | Killed | Survived |
|---|---|---|---|
| B1 stale anchor reported, fixed, only the number changes | 5 | 5 | 0 |
| B2 an anchor on a docstring or comment line is wrong | 5 | 4 | 1 |
| B3 a valid anchor is left alone, two rows may share a line | 4 | 3 | 1 |
| B4 fix changes nothing but the number, keeps order and columns | 4 | 3 | 1 |
| B5 a duplicated variable is reported and never touched | 4 | 2 | 2 |
| B6 an unresolvable anchor is reported and left alone | 4 | 1 | 3 |
| B7 no code line in the file means no guess (one more mutant did not apply) | 3 | 1 | 2 |
| B8 CRLF and line indexes kept byte for byte | 4 | 1 | 3 |
| B9 an escaped pipe does not move the edit | 4 | 3 | 1 |
| B10 nearest code line, tie goes to the lower | 4 | 4 | 0 |
| B11 this repository's own anchors are all right (real doc) | 4 | 2 | 2 |
| Total (counted from the rows) | 45 | 29 | 16 |

Survivors (16): 5 equivalent or non-informative: the NAME-token branch without the docstring test (a docstring is a STRING token, never a NAME); a duplicate row carrying new=1 (apply_fixes skips rows without `rel`); two CRLF mutants that are no-ops on Linux (open without newline="" on write, ROW match without rstrip: `\s` matches `\r`), which differ only on Windows; one no-op mutant of mine (SKIP = 1). 11 real LOW pin gaps:
- F-O-cb21-1: a variable that appears as a Python NAME (identifier equal to the env var), not in a string, is never tested (B3).
- F-O-cb21-2: `_rewrite_last_cell` guard: a row whose other cell holds the same `path.py:LINE` text; plain str.replace survives (B4).
- F-O-cb21-3: a duplicated variable is reported once per name, not per row (B5).
- F-O-cb21-4: three resolution paths unpinned: a path matching more than one source file ("matches N source files"), the short-row boundary (4 vs 5 cells), and resolution by substring instead of the /src/ suffix (B6).
- F-O-cb21-5: the SyntaxError and TokenError fallbacks of code_lines_naming are unpinned (B7, 2).
- F-O-cb21-6: the stray U+2028 claim in parse_rows (split on "\n", not splitlines) is unpinned on Linux (B8).
- F-O-cb21-7: an escaped pipe inside the LAST cell is unpinned (B9).
- F-O-cb21-8: a lowercase or mixed-case variable name in the table is not matched by an upper-case-only ROW regex and no test notices (B11).

CONDITIONS (none blocking; the batch is on main): C1 the coordinator may file one tests-only card for F-O-cb21-1..8 (a new PR; this head is merged). C2 re-run this table against current main's 207-line file before relying on it, since the code moved after this batch.

Tokens/cost line: not available to me. I do not know.
