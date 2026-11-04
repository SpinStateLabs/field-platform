# Reviewer report (fallback, read-only): MERGE 14 (batch cb21, PR 432, tools/environment_anchors.py, C-1116) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop: `dispatch.sh next reviewer` answered EMPTY at 21:35 and a restock-needed report is filed (restock-needed-3). Choice of batch: MERGE 16 (PR 446), MERGE 17, 18, 20, 21, 22, 23, 24, 9, 11, 12, 13 and 15 already have reviewer mutant notes on comms (`ls` of comms/inbox/coordinator), and the Lane A audit 20261104-0800 covers 16 to 23; MERGE 14 had none (nor did MERGE 10 or 1 to 8). I took MERGE 14 because every PR I review now depends on this tool (`--check` is a CI step since C-1191). Nothing was pushed; I changed no repository file.

Scope: `tools/environment_anchors.py` as it is on main today (the C-1116 commit 49948328 plus the follow-ups C-1122 a713e7a9, and the C-1173 and C-1183 test commits), against `tools/tests/test_environment_anchors_c1116.py` (36 tests). Author and committer of the five commits that touch the tool and its tests: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH, from `git log`).

## Verdict: PASS (the tool and its test file on ebb027a2), with LOW test gaps for a new PR. This is a retrospective review of merged code, so it has no merge condition.

## Objections first (FORCE-O)
1. The tool decides when a doc may merge (CI runs `--check`), so its false negatives matter most. The path "is this line a read" depends on `ast`: a file that does not parse falls back to a text match, and the fallback is the weakest part: mutant T28 (no word boundary in the fallback, so `FIELD_X` matches inside `FIELD_X_FILE`) survives all 36 tests. The tool's own docstring promises "a longer name that contains the variable is not a read"; for an unparseable source file that promise is untested (LOW; the AST path pins it, T3 killed).
2. `--fix` is the dangerous mode (it edits the doc). Its guards are pinned: the rewrite touches only the last cell (T17 killed), refuses an ambiguous cell (T18 killed), keeps CRLF and LF bytes (T25 killed), writes through a temporary file and a rename (T26 killed), and exits non-zero while anchors remain (T24 killed). One counter is wrong and untested: T15 (a `no-read` finding given a `new` value) makes `--fix` print "fixed 1" for a row it did not rewrite; the file is untouched because the rewrite also needs a `rel` (not run end to end; LOW).
3. Duplicate rows are reported once per name (design), and the test only checks that a duplicate is reported: T10 (one finding per duplicate row) survives (LOW).
4. T1 (docstrings counted as reads) survives, but is near-equivalent: the read test is `n.value == name` (exact equality), and a docstring holds more than the name, so the explicit docstring skip only matters for a bare string statement exactly equal to the variable name. I checked directly that a docstring mention before the real read still gives only the real line (`[7]`) under the mutant. The docstring case itself is pinned by a separate test (line 69 of the test file), which kills nothing here only because the equality already excludes it.
5. T20 (carriage return not stripped in `parse_rows`) survives and is equivalent: the row regex ends in `\|\s*$`, and `\s*` matches the `\r`.
Steelman: the tool replaced a hand-merged table that conflicted in every PR touching ENVIRONMENT.md; its rule is stricter than the older `test_environment_doc.py` check (first string constant exactly equal to the name, not a docstring, comment, longer name or later use), it never guesses (ambiguous file, duplicate rows, leading zero, short rows all reported and left alone), and the C-1173 and C-1183 sweeps have already pinned the survivors of an earlier mutation sweep.

## Runs (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1)
- tools/tests/test_environment_anchors_c1116.py: 36 passed. With tools/tests/test_environment_doc.py and tools/tests/test_ci_anchors_step_c1191.py: 68 passed (24.5 s). `python tools/environment_anchors.py --check` was 0 wrong anchor rows on every PR head I reviewed today.

## Mutants (environment_anchors.py; kill = test_environment_anchors_c1116.py with `-x`; baseline 36 passed)
| id | mutation | result |
|---|---|---|
| T1 | docstring skip removed | SURVIVED (near-equivalent, objection 4) |
| T2 | f-string literal pieces counted as reads | KILLED |
| T3 | substring match instead of equality | KILLED |
| T4 | last read instead of first | KILLED |
| T5 | an anchor on the last read accepted | KILLED |
| T6 | an anchor on any read accepted | KILLED |
| T7 | fenced rows not ignored | KILLED |
| T8 | fence toggle removed | KILLED |
| T9 | duplicate rows not reported | KILLED |
| T10 | duplicate reported once per row | SURVIVED (objection 3) |
| T11 | leading zero accepted in the line number | KILLED |
| T12 | First read cell index 3 | KILLED |
| T13 | short rows not reported | KILLED |
| T14 | ambiguous source file allowed | KILLED |
| T15 | `no-read` finding made fixable | SURVIVED (objection 2) |
| T16 | `mention` and `stale` kinds swapped | KILLED |
| T17 | rewrite replaces every occurrence in the line | KILLED |
| T18 | rewrite count check removed | KILLED |
| T19 | rows split with `splitlines` | KILLED |
| T20 | carriage return not stripped | SURVIVED (equivalent, objection 5) |
| T21 | `--check` exit code inverted | KILLED |
| T23 | unreadable doc exits 1 not 3 | KILLED |
| T24 | `--fix` exits 0 with anchors left | KILLED |
| T25 | doc read with newline translation | KILLED |
| T26 | atomic write replaced by a direct write | KILLED |
| T27 | fallback counts comment lines | KILLED |
| T28 | fallback without word boundary | SURVIVED (objection 1) |
Discarded: T22 (my "check also writes" edit left the condition effectively unchanged, so it is a no-op and invalid); I count it nowhere. Totals counted from the table: 27 valid mutants; 22 killed; 5 survivors (T1 near-equivalent, T20 equivalent, T10, T15, T28 real LOW gaps).
