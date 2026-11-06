# Review PR #787 (S8-30, renew_token helper pins) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `e9463aed73c869a2a967d498869b10d46d5506de`.

## Facts (HIGH, read from the head)
- 2 commits (68d6958a, e9463aed); 1 file: tools/tests/test_renew_token_helpers.py (+210). No production code, nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- New file: 47 passed on the head (Windows host), 0.92 s. POSIX branch of split_command is forced via `os.name` monkeypatch, so the test holds on any host (the reviewer-9 C1 fix is present).
- Targets read at tools/renew_token.py: read_secret (l.274), http_detail (l.458), clause_of (l.470), tail_lines (l.1473), split_command (l.1508). Pinned behaviour matches the code; quirks (kept `\n` of a `\r\n`, BOM refused, env value not stripped) are labelled as pinned current behaviour.

## Mutants (mine, hand-applied one at a time to renew_token.py, exact-replace with count==1 assert, file restored from backup; worktree clean after)
29 valid mutants (one id, #16, was skipped as not constructible). Counted from the run:
- RED 25: tail `<=`->`<`, `-1` removed, `+1` read removed, CR break dropped, LF break dropped, min->max, no-break returns data, `+1` dropped; split posix/nt swap, posix=False removed, outer-quote strip removed; http status==0 guard, transport default, clause accepted without fullmatch, clause_of fullmatch->match; read_secret strip, empty check, utf-8-sig, UnicodeDecodeError, isascii, isprintable, isspace, env strip, `or None`, `if secret_file` -> `is not None`.
- SURVIVED 4, all judged equivalent for reachable inputs (MEDIUM): split `len(token)>=2`->`>=1` (a lone `"` token cannot leave shlex non-posix, it raises); split quote condition `and`-chain reduced to `token[0]=='"'` (a token starting with a quote also ends with it in non-posix shlex); http_detail `isinstance(detail, dict)`->`hasattr(...,'get')` and clause_of `isinstance(clause, str)`->`str(clause)` (differ only for non-JSON objects).
- Initial run of two tail mutants was INVALID (backslash anchors collapsed by my tooling, count 0); redone with correct anchors, both RED. They are counted RED above.

## Conditions
None. LOW (optional, new PR only): none worth a PR.

## Not covered
Did not run the full tools/tests suite or CI; did not rebase on current main; Windows-only branch of kill_tree and the `nt` real-OS path of split_command not exercised on a real nt host beyond this Windows run.
