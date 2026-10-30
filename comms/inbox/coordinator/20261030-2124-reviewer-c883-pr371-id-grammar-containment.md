VERDICT: FAIL on 8eb5c87205347ff55acfe0ce3f2b6a21da796569
Card C-883. PR 371 at its newest head (fetched this session: unchanged since Lane 15's C-807 and my reading of C-860). Cloud reviewer, no GX10, CI not read: UNVERIFIED until re-run.

OBJECTIONS FIRST
1. The "remaining Lane 15 C-807 conditions" are all still open: the head did not move. C-807 C1 (absolute refs accepted anywhere, and the missing/invalid oracle for them) and C2 (unbounded resolver read) are blocking and unchanged. I re-probed both on a scratch copy (below), so this is not carried forward on trust.
2. The PR's own comment (agent_registry/api.py, `_ref_is_inside_manifest_dir`, `if target.is_absolute(): return True`) calls absolute refs "a decision, not made here". No ruling is on file that I could find in comms; a PR that ships a security guard with an acknowledged hole and no ruling is not mergeable as "containment".
3. Failure conditions: (a) a caller registers an absolute ref to any readable manifest-shaped file; (b) an absolute ref to a never-ending device file makes the resolver raise MemoryError (new `path.read_bytes()`, clients.py, was an mtime stat before); (c) a PATCH of manifest_ref is not confined in the default mode (pinned as a limit by the PR's test, F-C528-6).
Steelman: refusing absolute refs failed hundreds of tests in seven suites and the estate form is absolute; the PR is honest about it and everything else in C-528 is closed. That is a fair reason to take a ruling from Don, not a reason to call the card done.

ASSUMPTIONS
A1 Head = 8eb5c87 (git fetch of pull/371/head this session). A2 Linux only; no Windows junction or drive-letter run. A3 Probes use the PR's own app on a temp directory with a throwaway store.

REASONING (probes at 8eb5c87, scratch copy)
1. Absolute ref to a valid manifest outside the directory: 201 (accepted). HIGH.
2. Oracle: absolute existing non-manifest file 422 "invalid"; absolute nonexistent 422 "missing". Relative `../` valid file and nonexistent: both 422 "missing" (no oracle). Symlink file pointing out: 422 "missing". HIGH.
3. Resolver on /dev/zero under a 2 GB address-space limit: MemoryError after 8.9 s (not caught: the except covers OSError and ValueError only). HIGH. Main answers "invalid".
4. Id grammar: tests cover upper case, trailing/doubled separators, the 64 cap, the no-echo of the id in the 422. Migration (C-860): stored legacy ids list, get and patch fine; only new ids are checked. A new `a.1` registered 201 while a legacy `a..1` can exist in storage: confusable pair possible by migration (LOW, reasoning, not probed with a legacy row this time).
5. Mutants (applied by hand, restored with git checkout, tree clean after): baseline field-core cache test 4 passed, agent-registry c635 plus d3b 49 passed.
   M1 cache compare `cached[0] == digest` -> True: RED (killed).
   M2 digest -> mtime string: RED (killed).
   M3 drop `max_length=MAX_AGENT_ID_LENGTH`: RED (killed).
   M4 `.resolve()` -> `.absolute()` in the containment check: RED, 4 failures (killed).
6. Overlap: `git merge-tree` of PR 371 with main, 369, 374 and 380: all clean. Commits: 3, author and committer Don Hagell no-reply.

FINDINGS
F-C883-1 (HIGH, BLOCKS): absolute manifest_ref accepted outside FIELD_MANIFEST_DIR plus the invalid/missing oracle for absolute paths. api.py `_ref_is_inside_manifest_dir`. Needs Don's ruling (C-807 C4) or confinement with fixture moves.
F-C883-2 (HIGH, BLOCKS): the resolver's `read_bytes()` is unbounded and uncaught for MemoryError; add a regular-file check and size cap before the read. clients.py (ManifestResolver, the digest line).
F-C883-3 (MEDIUM, no block): stored refs are not re-checked on resolve; PATCH is unconfined outside ENFORCE (pinned). 
F-C883-4 (LOW): legacy ids can collide confusably with new ones; docs should say stored ids are not migrated.
F-C883-5 (LOW): ENVIRONMENT.md rows show line-number drift only; no content change to check.

CONDITIONS
C1 blocks: F-C883-1. C2 blocks: F-C883-2. C3, C4 do not block.

NOT VERIFIED: GX10 full set, CI at this head, Windows junctions and drive letters, FIFO read behaviour, attest on legacy ids.

CONCLUSION
Every earlier blocker is still present at the same SHA; the probes and four mutants reproduce them. FAIL on 8eb5c87, UNVERIFIED.
