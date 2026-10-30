VERDICT: PASS on 8c48282f710495d412ab6615ec9a5918ae294aea

Card C-482, PR 303 (builder card C-468, reviewer B-04 F-B04-1), Lane 7. Head confirmed by PR read: 8c48282, one commit, two files (+60 -1): services/sealed-ledger/src/sealed_ledger/anchors.py and a new test file. The PR sits on 48acfa6 per its list entry; it cherry-picks onto current main 613ab50 with no conflict. A PASS applies to this SHA only. Two LOW notes below; none blocks.

OBJECTIONS (before evaluation)
1. An absent-file change in a shared function can break a caller that relied on "absent means none".
2. A fix to a function with no caller changes nothing in production; the real fail-open (an anchors path that is a typo) may be somewhere else.
3. Other absent-or-bad spellings (a directory, a broken link, an empty path, a corrupt or truncated file) can still read as "no anchors".
4. A first run, when no anchors file exists yet, can be broken by a raise if any step reads before it writes.
5. Two copies of the same parser can drift.

ASSUMPTIONS
A1. Production code is everything outside tests; "caller" means a reference to `load_anchors` in a non-test Python file or a doc (HIGH, `git grep` over the whole repo, plus the sibling repos Force-Field and force-field-console in this session).

REASONING
1. Every caller of `load_anchors` (the card's first attack): none. In the repo it is defined at anchors.py:93 and referenced only by its own new test file, by the C-192 test's docstring (history), and by one sentence in docs/runbooks/v1.2-deploy-rollback.md:255 (about an older image reading a rotation anchor; it does not describe the absent-file case and is still true). The sibling repos have no reference (grep). The only function that reads an anchors file in production is `verify_anchors` (anchors.py:111-), called from cli.py:415 for `ledger verify --anchors`. It does its own read and already fails on an absent file, an unreadable file, an unparseable file and an empty file (C-192), so no caller's behaviour changes (HIGH).
2. Fail-open versus fail-closed per caller: `verify_anchors` is fail-closed on all four cases (its own tests, test_verify_anchors_fail_closed_c192.py, pass). `load_anchors` is now fail-closed on the absent case and already raised on corrupt data; it still returns `[]` for an existing file with no records, which the docstring leaves to the caller and `verify_anchors` refuses (anchors.py:131-132 in the head: "holds no anchor records") (HIGH).
3. A first-run directory: `ledger anchor` calls `write_anchor`, which only appends (`append_anchor_line` creates the parent directory and opens with "a", anchors.py:60-69); nothing reads the file first, so a first run is unaffected. `ledger rotate --anchors` (cli.py ~620-640) uses `append_anchor_line` the same way (HIGH, read).
4. Other spellings, probed on the head (made-up temp files): garbage text raises JSONDecodeError; bad UTF-8 raises UnicodeDecodeError; a truncated JSON line raises JSONDecodeError; a directory path raises IsADirectoryError; an empty path "" and a path under a missing directory both raise FileNotFoundError. None reads as an empty list (HIGH).
5. Tests: whole sealed-ledger suite on main 613ab50 plus the commit (source paths on PYTHONPATH, Python 3.13): 744 passed, 5 skipped, 0 failed (147 s). The new file: 5 tests (absent raises and names the path; absent is not `[]`; present file loads in order; an existing empty file is `[]`; a blank line between records is skipped). CI on the exact head: 7 of 7 success. I did not run the whole tools suite: the PR touches nothing under tools/ or docs/ (the brief asks for it only then).
6. Mutants (hand, 9, run against the new test file plus every anchors test): 8 red / 9. Red: absent returns `[]` again, absent raises ValueError, absent raises plain OSError, the message loses the path, empty bytes also raise, the blank-line filter dropped, the records reversed, the raise never fires. Survivor: a corrupt anchors file swallowed and returned as `[]` (a `try/except ValueError: return []` around the parse). NOT equivalent: it would reopen the same fail-open shape for corrupt data, and no test pins that a corrupt file raises (the source raises today, point 4).
7. The change is correct and small. It is also a change to dead code: with no caller, the function is kept alive by its own test. The B-04 finding allowed either removing it or making it safe; the builder made it safe.

FINDINGS
- F-C482-1 LOW (test gap, mutant): add one test that a garbage line, bad UTF-8 and a truncated line each raise (not `[]`), next to the absent-file test. services/sealed-ledger/tests/test_load_anchors_c468.py. Survivor of mutant 8.
- F-C482-2 LOW (maintenance): `verify_anchors` and `load_anchors` carry two copies of the same parse (anchors.py:100-104 and the list inside `verify_anchors`). Either delete `load_anchors` (no caller) or have `verify_anchors` parse through one helper so a future change cannot fix one and miss the other, which is how this fail-open lived on after C-192.
- Note for the coordinator: the runbook sentence at v1.2-deploy-rollback.md:255 names `load_anchors` as if it were a tool an operator runs; it is a library function nothing calls. Not a defect of this PR.

CONCLUSION: PASS on 8c48282f710495d412ab6615ec9a5918ae294aea. An absent anchors file raises and names the path, no production caller depends on the old behaviour, the real checker (`verify_anchors`) was already fail-closed and still is, first runs are unaffected, the whole package suite passes (744), CI is 7 of 7 and 8 of 9 mutants are red. Coordinator still needs GX10 16/0 on the exact head.

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13; other Pythons only through CI.
- Did not run the whole tools suite (the PR touches nothing under tools/ or docs/).
- Did not read the B-04 report beyond the card text, and did not check non-Python consumers of an anchors file (shell scripts, cron jobs on an estate), which cannot call a Python function but could read the file.
- Did not examine the 5 skipped sealed-ledger tests.

CORRECTION (Lane 7): in reasoning point 2 the line for the "holds no anchor records" refusal in verify_anchors is anchors.py:136 on the head (I wrote 131-132 from memory); `verify_anchors` starts at :111 and its own read at :122. The conclusion does not change.
