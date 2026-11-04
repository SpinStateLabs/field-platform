# Lane O reviewer: MERGE 17 (batch cb25: PRs 438, 433; main 4f731ee9 to 40aec372; 5 commits), ROLE-LOOP FALLBACK, read-only post-merge mutant review. PARTIAL. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main), naming the merged head 40aec372, for tools/environment_anchors.py (PR 438, first-read semantics, C-1122) and services/delegation-authority/src/delegation_authority/cli.py (PR 433, GuardedOperatorAuth now inherits field-core's origin test). NOT COVERED, "I do not know": the lifecycle CLI guard test (40aec372 itself, tests/test_lifecycle_service_client_guard_c1087.py) and field-core guarded_operator.py (merged earlier, MERGE 12). All 5 commits: Don Hagell noreply as author and committer (git log, HIGH). Counts, identity and verdict files for MERGE 17 were checked by Lane A's C-1200 audit (20261104-0800); that audit ran no mutants; this report does. I claimed MERGE 17 in a note (20261104-0914).

Objections first: (1) the tool now defines the FIRST read as the first line holding a string constant EXACTLY equal to the variable name; a variable first read through a helper that builds the name, or from a constant defined in another file, has no such line and is reported "no read", not fixed (read, HIGH). (2) the tool tests the anchor, not that the doc's other cells are true. (3) the weak spots below are all in the tool's edge handling: 19 of 41 mutants survive.

Run here (cloud, scratch worktree on 40aec372): tools/tests/test_environment_anchors_c1116.py 29 passed; test_cli_client_guard_c1087.py 4 passed; lifecycle guard test 2 passed. `python tools/environment_anchors.py --check` on this head and on current main: 0 wrong anchor row(s) (run on main earlier, HIGH). NOT run: the 16-suite set, CI.

Mutants (41 run in a scratch worktree on 40aec372; each against the PR's own test file, survivors against tools/tests/test_environment_doc.py or the whole delegation-authority suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 an anchor is right only at the FIRST exact read | 5 | 5 | 0 |
| B2 docstrings, f-string pieces and mere mentions are not reads | 5 | 2 | 3 |
| B3 the anchor cell must be path.py:LINE, no leading zero | 4 | 2 | 2 |
| B4 table-like rows inside a code fence are ignored | 4 | 2 | 2 |
| B5 exit codes: 0 right, 1 wrong, 3 unreadable | 5 | 3 | 2 |
| B6 the doc is rewritten atomically, line endings kept | 5 | 4 | 1 |
| B7 an unparseable source file falls back to whole-name, non-comment lines | 5 | 0 | 5 |
| B8 finding kinds and the fix target | 4 | 1 | 3 |
| B9 the delegation CLI auth inherits the field-core origin test | 4 | 3 | 1 |
| Total (counted from the rows) | 41 | 22 | 19 |

Survivors (19): 3 equivalent (docstring exclusion when the docstring would have to equal the variable name exactly, two mutants; a trailing slash on the CLI base, which the parent strips), 16 real pin gaps, the worst first:
- F-O-m17-1 MEDIUM: the SYNTAX-ERROR FALLBACK of read_lines_naming has no test at all (5 of 5 mutants survive: returning no lines, dropping the comment rule, dropping the whole-word rule, dropping the escape, narrowing the except). Any source file that does not parse takes this path.
- F-O-m17-2 MEDIUM-LOW: code-fence handling: `in_fence = True` (a fence that never closes) survives, so table rows after a closed fence would be skipped silently; a tilde-only fence regex survives (tools/environment_anchors.py parse_rows).
- F-O-m17-3 MEDIUM-LOW: a source file with no read of the variable: a mutant returning new=1 survives (the finding would claim a fix target of line 1); the "past the end of the file" and "only mentions it" wordings are unpinned (B8, 3).
- F-O-m17-4 LOW: the anchor regex without its end anchor (`foo.py:12abc` read as 12) and without `.py` survive (B3, 2).
- F-O-m17-5 LOW: exit 3 on an undecodable doc or an unwritable doc is unpinned (B5, 2); the atomic temporary-file write is unpinned (B6, 1).
- F-O-m17-6 LOW: a padded constant (` NAME `) counts as a read (B2, 1).

CONDITIONS (none blocking; on main): C1 a tests-only card for F-O-m17-1..6, F-O-m17-1 first. C2 the uncovered lifecycle CLI guard test and guarded_operator.py need a reader (the latter is from MERGE 12, which Lane A audited for counts only).

Tokens/cost line: not available to me. I do not know.
