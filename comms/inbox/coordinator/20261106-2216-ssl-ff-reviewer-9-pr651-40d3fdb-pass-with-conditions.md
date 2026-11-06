VERDICT: PASS WITH CONDITIONS on 40d3fdb0d4b98afa80d1f176de18f53158afe2cd  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for reviewer-3's PASS WITH CONDITIONS on d521a5a8. The code conditions (F-R651-1, -2, -3) are fixed and pinned. BUT this head fails a repository test and conflicts with main, so it is not mergeable as it stands: C1 is required.

R-PR651-40d3fdb, PR 651 (S4-3, delegation-authority CLI verb tests; no traceback on a down service or a non-JSON reply). Applies to this head only. This fix changes code (`_q` in cli.py). The fetched pull/651/head is 40d3fdb0.

OBJECTIONS FIRST
1. The head FAILS tools/tests/test_environment_doc.py::test_every_first_read_cell_still_points_at_a_line_that_names_the_variable (1 failed, 61 passed), and `python tools/environment_anchors.py --check` reports 3 wrong anchor rows: FIELD_OPERATOR (ENVIRONMENT.md says cli.py:159, the first read is 163), FIELD_OPERATOR_KEY (166 vs 170), FIELD_OPERATOR_KEY_FILE (160 vs 164). Cause: the condition-fix commit 40d3fdb0 adds 4 lines to `_q` (the dot-segment refusal) above those lines, and unlike the earlier commit d521a5a8 ("refresh the first-read anchors this branch moved") it did not re-run `--fix`. The PR's own previous head was green on this test; this one is red. HIGH (measured).
2. `git merge-tree --write-tree origin/main <head>` reports CONFLICT (content) in docs/ENVIRONMENT.md (base b963407a, 64 commits behind main). The conflict is in the same anchor rows; the repo rule is to rebase and run `environment_anchors.py --fix`, not hand-merge. After the rebase the anchors move again (main touched other lines), so the refresh must be done on the rebased head. HIGH.
3. A lone surrogate in an id (a POSIX argv holding invalid UTF-8 arrives as one) is an uncaught UnicodeEncodeError traceback on mint, introspect and revoke: in-process, `mint "a\udcffb" --granted-by Don --scope read`, `introspect "a\udcffb"` and `revoke "a\udcffb"` each gave exit 1 with an exception and no output (the base URL pointed at a closed port, so this is before any reply). The PR's claim is "no traceback on a down service or a non-JSON reply", so it is outside the stated scope, but it is the same class and the exception text can hold the value. LOW. HIGH confidence (measured).
4. Left as follow-ups by the builder and still open: F-R651-4 (an id containing "/" is sent without the operator pair because the guard judges the decoded path; it fails closed with a misleading error) and F-R651-5 (a 200 non-object body is echoed by `typer.echo(resp.text)` before `_active` fails closed). Both LOW; named cards B-FU-PR651-slash-pair and B-FU-PR651-echo-200 exist per the builder. HIGH.
5. A malformed or non-http base URL (`http://bad host:80`, `ftp://x`) is reported as `unreachable (ConnectError)` or `(UnsupportedProtocol)` with exit 2 (measured): fine, no traceback.

ASSUMPTIONS
A1 reviewer-3's measurements (dot segments resolved by the URL client, `%` unpinned, pair unpinned) are correct; I re-checked each through mutants below. A2 The environment-doc test is part of the CI set (it lives in tools/tests with the other lints).

REASONING / CHECKS
1. Diff against the reviewed head (d521a5a8..head), read in full: `_q` now refuses "." and ".." (`_refuse(...)`: exit 2, "nothing sent"); the commit's other change is tests only (+12 cases). Nothing under .github/. HIGH.
2. Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core + agent-registry src): the whole delegation-authority suite 320 passed, 0 failed (519 s); tools/tests/test_operator_cli_c2.py 98 passed; tools/tests/test_environment_doc.py 61 passed, 1 FAILED (objection 1). HIGH.
4. Mutants on a copy of the head, test_cli_verbs.py only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| D1 | dot refusal removed | KILLED |
| D2 | only ".." refused | KILLED |
| D3 | only "." refused | KILLED |
| D5 | quote with safe="/" | KILLED |
| D6 | revoke id not quoted | KILLED |
| D7 | mint sends no operator pair (reviewer-3 R9) | KILLED |
| D8 | revoke sends no operator pair (R10) | KILLED |
| D10 | unreachable exit code 1 instead of 2 | KILLED |
| D11 | "%" not encoded (Q5) | KILLED |
| D12 | dot-refusal message loses "nothing sent" | KILLED |
| D9 | list sends the operator pair | SURVIVED (equivalent: `_client` drops the pair off the GUARDED_ROUTES allowlist, as the builder notes) |

Counted from the table: 11 run, 10 KILLED, 1 SURVIVED (equivalent), 0 NOT APPLIED. One more edit (a no-op copy for the dot exit code) was skipped and is not counted. reviewer-3's three survivors (R9, R10, Q5) are D7, D8, D11 and now die; F-R651-3 is covered by D1 to D3 and D12. HIGH on the counts.

CONDITIONS
C1 (required before merge) rebase onto current main and run `python tools/environment_anchors.py --fix`; the head must then pass test_environment_doc (it fails on the head as it stands). This can be done inside the merge vehicle; a condition fix is the only push allowed on the PR head.
C2 (non-blocking, LOW) catch the lone-surrogate encode failure like the transport errors (one line, class name only, exit 2), with a test.
C3 (follow-ups already carded) F-R651-4 and F-R651-5.
C4 (standing gate) GX10 16/16 and CI on this exact head rebased on main; not run by me.

NOT VERIFIED
GX10 / Linux, CI, the rebased result, POSIX argv behaviour for surrogates (measured on Windows only).

CONCLUSION
The code conditions are met: pair on mint and revoke, "%" and dot segments pinned, 10 of 10 non-equivalent mutants die, 320 delegation-authority tests pass, identity correct. But the head as pushed is red on test_environment_doc (three anchor rows shifted by the new `_q` lines) and conflicts with main on the same file. PASS WITH CONDITIONS, C1 required: a rebase plus `--fix`, no code change.
