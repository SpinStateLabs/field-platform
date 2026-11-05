VERDICT: PASS WITH CONDITIONS on 68d6958a97786fa10a7c27330df7836f605a2ed2  (ssl-ff-reviewer-9; Windows only, no GX10, CI not read)

R-PR787-68d6958, PR 787 (S8-30, tools tests pinning renew_token tail_lines, split_command, http_detail, clause_of, read_secret; tests only). Applies to this head only.

OBJECTIONS FIRST
1. One of the PR's tests FAILS on Windows: tests/test_renew_token_helpers.py::test_split_command_posix_quoting_and_backslashes (1 failed, 99 passed with test_renew_token_pins_c212.py). It calls renew_token.split_command with no os.name patch, so on Windows the nt branch runs: `'a "b c" d\ e'` gives ['a','b c','d\','e'], not the asserted ['a','b c','d e']. The two nt-branch tests patch os.name to "nt"; the POSIX one needs the symmetric patch to "posix". On Linux (CI, GX10) it should pass: I did not run it there (inference from reading shlex.split semantics; MEDIUM). The test is therefore platform-dependent, and renew_token is a tool used on Windows. HIGH on the failure, MEDIUM on "passes on Linux".
2. Mutants I can reach on this box do not exercise the POSIX branch of split_command at all (the nt branch runs): my mutant S1 (POSIX branch uses str.split) cannot be evaluated here. Whether the POSIX test kills it on Linux: not shown. NOT VERIFIED.
3. "Quirks pinned, not changed" means two arguably buggy behaviours are now locked by tests: tail_lines starts with a stray "\n" after a "\r\n" cut, and read_secret refuses a UTF-8 BOM file (R5 below shows the test would fail if that were fixed to utf-8-sig). Fixing either later requires editing these tests; the PR flags both and asks Don about the BOM. Not a defect; a decision. MEDIUM.
4. The test file mutates module state with monkeypatch only (VERIFY_OUTPUT_MAX, os.name inside a context): no leakage found by reading. LOW.
5. Base is 13 commits behind main; the diff is one new test file; `git merge-tree` is clean. HIGH.

ASSUMPTIONS
A1 PR body figures (47 cases, 14 hand mutants) are the author's; I recount below. A2 A kill counts only when pytest returned 1 with the Windows-failing POSIX test deselected, so a baseline failure cannot read as a kill.

REASONING / CHECKS
1. Diff: one new file, tools/tests/test_renew_token_helpers.py +208; tools/renew_token.py untouched; nothing under .github/. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, python run from tools/): helpers file + test_renew_token_pins_c212.py = 99 passed, 1 failed (objection 1). With that one deselected, the helpers file is 46 passed. HIGH.
4. Mutants on a copy of renew_token.py with the same file set, the failing test deselected, a kill = rc 1:

| group | ids | result |
|-------|-----|--------|
| tail_lines | T1 `<=`->`<`; T2 drop seek +1; T3 whole window on no break; T4 drop CR break; T5 drop the +1 after the break; T6 no extra byte read; T7 min->max; T8 drop LF break | 8 of 8 KILLED |
| split_command (nt branch) | S2 keep outer quotes; S3 posix=True; S4 drop empty token | 3 of 3 KILLED |
| split_command (POSIX branch) | S1 str.split | NOT EVALUABLE on this box (objection 2) |
| http_detail / clause_of | H1 transport shows body; H2 no fullmatch (http_detail); H3 clause_of any string; H4 body echo condition; H5 clause_of match not fullmatch; H6 http_detail match not fullmatch | 6 of 6 KILLED |
| read_secret | R1 skip empty-file check; R2 drop isprintable; R3 `value` not `value or None`; R4 strip env value; R5 read utf-8-sig; R6 drop isascii; R7 no strip of file value; R8 env wins over file | 8 of 8 KILLED |

Counted from the table: 25 mutants run on evaluable code, 25 KILLED, 0 SURVIVED, 0 NOT APPLIED (T4 and T8 were re-run with a corrected edit after my first script did not apply them); 1 more (S1) not evaluable. The 4-per-behaviour bar is met for tail_lines (8), http_detail/clause_of (6) and read_secret (8); split_command has 3 evaluable plus the one I could not run. HIGH on the counts.

CONDITIONS
C1 (required, small) patch os.name to "posix" inside test_split_command_posix_quoting_and_backslashes (as the nt tests patch it to "nt") so the test passes on Windows; a condition fix is the only push allowed on the head. Re-run on Linux (GX10) to confirm.
C2 (decision for Don, as the PR asks) whether read_secret should read utf-8-sig; if yes, a follow-up changes code and test R5's pin together.
C3 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me.

NOT VERIFIED
Linux behaviour of the POSIX split test and S1; the PR's own 14-mutant list (I used my own 25); CI.

CONCLUSION
The tests pin the five helpers well: 25 of 25 evaluable mutants killed, tests only, identity correct. One test fails on Windows because it is not isolated from os.name. PASS WITH CONDITIONS: C1 is a one-line condition fix; C2 is Don's decision; C3 the gate. Head frozen except the condition fix.
