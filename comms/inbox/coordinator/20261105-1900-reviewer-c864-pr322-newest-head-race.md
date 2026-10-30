VERDICT: PASS WITH CONDITIONS on 6ac0f8e6b414ac1138a7e52961703e5e5cd1c865
(Lane 14, cloud, no GX10: UNVERIFIED re-run. PR 322, federation-broker: five commits on main (98dba84, f6a9bbe, 935a8d0, 5ff3df4, 6ac0f8e); author and committer Don Hagell no-reply on all five. Ran here: the whole federation-broker suite, 185 passed (not the 16-suite GX10 set). CI at this head read by REST: all 7 jobs QUEUED: NOT confirmed. Builds on my C-684 (935a8d0), Lane 4's C-565 and C-578 (PASS head f6a9bbe).)

OBJECTIONS FIRST
1. The race test named "atomic across processes" uses two threads and two store objects in one process; a thread test cannot prove cross-process atomicity (Lane 10's correction stands).
2. The delta widens a hand list of invisible characters again; each round fixes what the last reviewer named.
3. Documenting a collision (joiners) is not removing it.

ASSUMPTIONS
A1. The probes ran real spawned processes (8 per round, a barrier, a fresh database per round) against the unmutated and one mutated store. A2. Conditions are Lane 4's C-565 (race, deactivated contract, re-registration, rotated index, normaliser) and my C-684 findings.

REASONING
1. What changed since 935a8d0 (git diff): engine.py adds the Mongolian free variation selectors U+180B-180D and U+180F to the dropped set and a comment stating the list is a CHOSEN SUBSET of the default-ignorable set (U+2065, U+FFF0-FFF8, most of U+E0000-E0FFF and U+16FE4 left out on purpose); the tests add those code points, their neighbours U+180A and U+1810 (kept), the two left-out ones (kept), three kept-mark name pairs (Khmer, Hindi), and four joiner-collision cases; the README documents "the joiner collision" and says two different names can be one org, a false 409, never a bypass. Store code (`save`, `for_org`, migration, index) is unchanged since f6a9bbe. HIGH.
2. Is the race still proven? Two answers. (a) IN PROCESS: tests/test_org_normalise_c483.py:122-150, `test_two_stores_on_one_file_cannot_both_register_an_active_contract`, uses two `ContractStore` connections on one file and two threads over 15 rounds; it is a real two-connection race (SQLite sees two connections), but it is one process. The mutant `BEGIN IMMEDIATE` replaced by a plain `BEGIN` is killed by the PR's tests: RED. (b) ACROSS PROCESSES: not tested by the PR. I ran it: 15 rounds, 8 spawned processes each, eight different spellings of one org (including the new Mongolian selectors and the combining grapheme joiner), a fresh database per round: 15 winners, 105 conflicts, 0 errors, exactly one active row in every round (bad rounds 0). HIGH (run).
   The same process race with `BEGIN` deferred (the mutant): 26 of 120 saves failed with an error (a locked database), still no duplicate active row in any round: the unique index is the safety net against duplicates; `BEGIN IMMEDIATE` is what turns the lock error into a clean 409. So the README's "one write transaction plus a unique index" is accurate, and the in-process test is enough to pin the transaction, but it is not a cross-process proof and its name says it is (F-C864-1).
3. C-565 conditions at this head: deactivated contract (for_org without the active filter) RED; re-registration (scopes and org key omitted from the upsert) RED; rotated database (inactive rows counted in the duplicate check) RED; `BEGIN IMMEDIATE` RED. 9 of 9 mutants RED (also: Mongolian range shortened at either end, U+034F dropped, Cf not dropped). HIGH (run).
4. My C-684 findings: F-C684-1 (Mongolian free variation selectors not merged): CLOSED (probe: all four merge into the plain name). F-C684-2 (reserved default-ignorable code points): CLOSED AS A STATED LIMIT (the comment and the README name them; pinned by tests). F-C684-3 (README silent about the subset): CLOSED. F-C684-4 (joiners merge distinct names in some scripts): STILL OPEN BY DESIGN, now documented and pinned (Persian ZWNJ words and Hindi conjuncts with ZWJ become one org with their plain spelling and the second registration is a false 409); it remains a decision for Don; the stored name is unchanged. HIGH (run).
5. Public repo: no estate address, flag value, build SHA, deploy status or credential in the diff. HIGH.

FINDINGS
F-C864-1 (LOW): the test title says "atomic across processes" and the section header too; it is two threads in one process. Rename, or add a spawned-process test (my script is a pattern: 8 spawned workers, a barrier, one file).
F-C864-2 (LOW, info): the unique index, not the transaction, prevents duplicates; the transaction prevents lock errors from surfacing (26 of 120 saves failed without it). The README could say so.
F-C864-3 (carried, Don's call): the joiner collision (documented, pinned).
CLOSED: C-684 F-1, F-2, F-3.

CONDITIONS
C1 (non-blocking): F-C864-1 naming or a real cross-process test.
C2: CI at this head (queued) and the GX10 run.
Not verified: CI; Python versions other than the sandbox's; any estate database.

CONCLUSION
The race is still proven, in the sense the README claims: processes cannot both win (0 bad rounds over 120 spawned saves) and the transaction and the index each do their job; but the PR's own test proves it for two connections in one process, and its name overstates that. The delta closes the Mongolian gap and states the list as a subset; the joiner collision is documented and pinned, not removed. PASS WITH CONDITIONS (non-blocking) on 6ac0f8e.
