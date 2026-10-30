VERDICT: PASS WITH CONDITIONS on 935a8d002f454d6efb266f8d18bcfc6d1c773abd
(Lane 14, cloud, no GX10: UNVERIFIED re-run. Production change in services/federation-broker (engine.py normaliser, README, one test file): delta f6a9bbe to 935a8d0 is 3 files, +81 -9, one commit. Author and committer Don Hagell no-reply on all three PR commits. Ran here: the whole federation-broker suite, 169 passed at this head (not the 16-suite GX10 set). CI at this head read by REST: 4 of 6 listed jobs success, tests (3.11) in progress, compose-smoke queued: NOT confirmed. Delta read against the C-565 report (20261103-0930...) and the C-578 report (20261103-1400...), then probed independently.)

OBJECTIONS FIRST
1. The delta widens a list of "invisible" characters by hand; a hand list is complete only for the characters its author thought of. The C-578 round already showed one gap; this round can leave another.
2. Changing the normaliser changes the org key that the one-active-per-org index and the 409 depend on; any conditions that rest on the key (race, rotation, legacy-duplicate migration) must be re-proved at the new head, not assumed from the old one.
3. The README now promises both what is merged and what is kept; each word in that promise is a claim a Unicode table can falsify.
4. Merging more characters can turn a distinct pair of names into one org (a false 409) for scripts where the character carries meaning.

ASSUMPTIONS
A1. "Invisible" = the Unicode Default_Ignorable_Code_Point set, from my training data of the property file (MEDIUM); Python 3.13's Unicode 15.1 tables (`unicodedata`) used for categories. A2. The probes call `normalize_org` and the store directly on a scratch database; nothing reaches a service. A3. The "conditions" of C-565 are the four findings F-C565-1..4 that C-578 re-verified plus the normaliser decision F-C565-5.

REASONING
1. What changed: `git diff f6a9bbe 935a8d0 -- engine.py` has one hunk, in `normalize_org` (engine.py:254-272): a new `_invisible()` and the table `_INVISIBLE_NOT_CF`. `ContractStore.save`, `for_org`, `_migrate_org_key` and the index are byte-identical to the C-578 head. HIGH.
2. C-565 conditions, re-proved at this head:
   - Two-process race (F-C565-1): 20 rounds, 6 spawned processes per round on one SQLite file with a barrier, each registering a different spelling of one org (including new invisibles: combining grapheme joiner, a variation selector): 20 winners, 100 conflicts, 0 errors, exactly one active row in every round. HIGH (run).
   - Deactivated contract (F-C565-2): mutant for_org without the active filter goes RED. HIGH.
   - Re-registration (F-C565-3): mutants omitting allowed_scopes and org_key from the upsert go RED. HIGH.
   - Rotated database (F-C565-4): mutant counting inactive rows in the duplicate check goes RED. HIGH.
   - BEGIN IMMEDIATE replaced by a deferred BEGIN goes RED (the transaction is pinned). HIGH.
3. The new normaliser, probed on 15.1 tables: dropped: every Cf character; U+034F; U+FE00-FE0F; U+E0100-E01EF; U+115F and U+1160 (and U+3164, U+FFA0 through NFKC, which maps them to U+1160); U+17B4-17B5; U+2800. Kept (README says kept): U+20DD enclosing circle, U+0E31 Thai vowel, U+093F Devanagari vowel sign, U+0300 combining accent, U+00B7 middle dot, Cyrillic look-alikes. The stored counterparty_org keeps the caller's spelling (probe: `'A​cme͏ Corp'` listed back as typed) while `for_org("ACME  corp ️")` finds it. Whitespace of every kind is a separator, not dropped (so a space-like character inside a word makes a different org; intended). HIGH.
4. Mutants on the delta (each must go red): Cf no longer dropped; each list entry removed or off by one (U+034F, FE0F end, E01EF end, U+1160, U+17B5, Braille blank); first NFKC removed; casefold and second NFKC removed; whitespace collapse removed: 10 of 10 RED; with the five C-565 mutants, 15 of 15 RED. HIGH.
5. What the list still misses, in the Default_Ignorable set I know: the Mongolian free variation selectors U+180B, U+180C, U+180D and U+180F (category Mn; U+180E is Cf and is dropped). Probe: `Acme<U+180B> Corp` is a different org from `Acme Corp`: for_org returns None. Four code points, same class and same effect as the gap C-578 reported (F-C684-1). Also unmerged: reserved default-ignorable code points that Unicode 15.1 has not assigned (U+2065, U+FFF0-FFF8, most of U+E0000-E0FFF, 3769 code points in all): they render as nothing in some fonts and are not typeable in real text; LOW. U+16FE4 (Khitan small script filler, Mn) is blank and is not merged; LOW.
6. Consequence, to state it plainly: a counterparty who can register contracts could spell one org two ways with U+180B and hold two "active" contracts for it. That defeats the one-active-per-org rule (a registration-time policy), not authentication (the key and signature checks are separate). MEDIUM-LOW.
7. README (federation-broker/README.md): the merged and kept lists match the code and the probes above (item 3); the 409 sentence is unchanged. One word, "invisible Unicode characters ... a listed set", is accurate as a list, but the README does not say the list is not the whole Default_Ignorable set; add it.
8. Public repo: diff has no estate address, flag value, build SHA, deploy status or credential. HIGH.

FINDINGS
F-C684-1 (LOW-MEDIUM, non-blocking): engine.py:_INVISIBLE_NOT_CF omits U+180B, U+180C, U+180D and U+180F (Mongolian free variation selectors, Mn, default-ignorable). PROVEN by probe. Fix: add (0x180B, 0x180D) and (0x180F, 0x180F); or switch to the full Default_Ignorable property from a vendored table so a future Unicode version needs no edit.
F-C684-2 (LOW): reserved default-ignorable code points and U+16FE4 are not merged. PROVEN for the 15.1 tables; not realistic input.
F-C684-3 (LOW): the README does not state that the list is a chosen subset of the default-ignorable set, so a reader may read "invisible" as "all". Say so and name F-C684-1's four code points if they are left out on purpose.
F-C684-4 (design, carried from C-565): merging joiners (ZWJ and ZWNJ) can turn two distinct names in some scripts into one org (a false 409, not a bypass). Still flagged for Don; not re-decided here.
F-C684-5 (info): no new test for a Hindi, Thai or Khmer name that must stay distinct beyond the three kept marks I probed; the PR's own test file adds 51 lines around the list.

CONDITIONS
C1 (non-blocking): F-C684-1, a two-line change plus a probe test.
C2 (non-blocking): F-C684-3 wording.
C3: the GX10 full run and CI at this head (one job in progress, one queued when read).
Not verified: the Default_Ignorable list is from memory of the Unicode data file, not read from one; no estate contracts; the 16-suite GX10 set.

CONCLUSION
Every C-565 condition still holds at 935a8d0: the store code is untouched since the C-578 PASS head, the race gives one winner in 20 of 20 rounds, and each prior mutant still goes red. The delta closes the C-578 invisible-character gap for the characters it lists (10 of 10 delta mutants red) and keeps visible marks distinct as promised, but a hand list left four default-ignorable code points out (F-C684-1). PASS WITH CONDITIONS (non-blocking) on 935a8d0.
