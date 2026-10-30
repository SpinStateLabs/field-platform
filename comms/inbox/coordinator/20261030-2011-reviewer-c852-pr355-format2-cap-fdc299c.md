VERDICT: PASS WITH CONDITIONS on fdc299ca3f5b00e6365e6f905c77df0737dc22fa  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-852, PR 355 (field-core tests: format 2 ambiguity rules, retired-hash cap boundary; C-51) at fdc299c. One commit on 191affb (my C-702 and C-744 head): two test files, +91 lines, no source change. This SHA only. I did not find a "builder Lane 13 corrected report" beyond the notes 20261030-1710 and -2000; I compared against C-690, C-702 and C-744 instead.

OBJECTIONS FIRST
1. The cap boundary is pinned only at cap and cap+1, never cap-1, and `>` versus `>=` cannot be told apart. test_operator_auth_format2.py:936-945 (cap 2: two retired entries kept; three retired entries drop the oldest). `if len(retired) > MAX_RETIRED_HASHES` changed to `>=` survives (244 passed): it is an equivalent mutant (keeping the last `cap` of `cap` entries changes nothing). A cap-1 case cannot differ either. So the three-point boundary the card asks for is: cap-1 and cap behave the same by construction; cap+1 is pinned and kills six real mutants (slice from the front, slice `cap-1`, sort reversed, `> cap+1`). HIGH.
2. The sightings cap is unpinned. `len(_retired_seen) < MAX_RETIRED_HASHES` changed to `<=` survives all 244 tests. This is a second bound (distinct sightings counted in `retired_hash_seen`), different from the retired-entry bound the new tests pin. LOW-MEDIUM.
3. Eviction consequence still unpinned (C-702 F-C702-2, C-744 F-C744-2): the over-cap test asserts the evicted entry is gone from the table, not that the evicted key is then accepted again. That acceptance is the security consequence of the cap. Nothing in the new commit adds it. LOW-MEDIUM (PROVEN in C-744).
4. Ambiguity cases that still pass (probe through parse_registry on the test fixture, exact-string rules): two operator ids differing only by case ("Don" next to "don"); an alias equal to another id except for case or a trailing space; the same alias twice in one row; the same alias in two rows differing by case; a whitespace-only alias; alias " * " and "**"; "all"; an alias holding a NUL. Refused: exact duplicate id; an id with a trailing space, full-width letters or a Cyrillic lookalike (id grammar); alias equal to own id; alias shared exactly between two rows; empty alias; non-string alias; 300-character alias; one hash on two ids. Matching is exact (no lower-casing or stripping in the key-match path, operator_auth.py grep), so the accepted variants do not collide at match time; the risk is human confusion in logs and lists. C-702 F-C702-1 stands. LOW.
5. The break-glass alias rule survives removal when only the two PR test files run (`if n == BREAKGLASS_ID and ...` changed to `if False:`: 244 passed). It is pinned elsewhere per the code comment (C-76/C-86), which I did not run. Not this PR's change. INFO.

ASSUMPTIONS
A1 Card scope: boundary at cap-1, cap, cap+1; ambiguity cases that still pass. A2 The cap is MAX_RETIRED_HASHES (4096) in production; tests shrink it by monkeypatch.

REASONING / CHECKS
- Tests: test_operator_auth_format2.py and test_rotation_events_r2.py: 244 passed.
- New in fdc299c: generation 1 accepted and 0 refused for rotation events (`_gen` is `>= 1`), operator_ids at MAX_OPERATOR_IDS (64) accepted and 65 refused. Mutants: `v >= 1` to `v > 1` KILLED; to `v >= 0` KILLED; `len <= MAX` to `<` KILLED; to `<= MAX+1` KILLED.
- Earlier tests (191affb) kill: duplicate id check removed KILLED; alias `*` rule removed KILLED; alias-equals-id rule removed KILLED; shared alias rule removed KILLED.
- Mutant totals (15, each restored, nothing committed): 12 killed, 3 survived: the `>=` on the entry cap (equivalent), the sightings-cap `<=` (objection 2), the break-glass alias rule (objection 5, pinned elsewhere unverified).
- Commits: 2 on the branch, author and committer Don Hagell no-reply; no address, flag value, credential or deploy status in the diff.

CONDITIONS
C1 (non-blocking) Pin that an evicted hash is re-admitted (or state it as the accepted cost) and pin the sightings cap at its boundary.
C2 (non-blocking, carried) Decide whether ids and aliases compare case-insensitively (C-702 F-C702-1); if not, state it.
C3 (non-blocking, carried) C-744 F-C744-2: same-generation file with different content is not covered by the retired memory.

NOT VERIFIED
GX10 full set, CI by run id, the other tests that pin the break-glass rule, behaviour at the real cap of 4096.

CONCLUSION
The new commit closes C-690 F-C690-2 and F-5 for the rotation-event bounds (4 of 4 mutants die) and the retired-entry cap is pinned at cap+1. Eviction consequences, the sightings cap and case-variant ids remain open, all low. PASS WITH CONDITIONS, UNVERIFIED.
