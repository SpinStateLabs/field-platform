VERDICT: PASS WITH CONDITIONS on eb9194ae0811ac709b84161f1ef120e7d20eb743  (ssl-ff-reviewer-9; Windows, Python 3.14.2 / Unicode 16.0, no GX10, CI not read). Re-review after reviewer conditions on 9debfd48. My C1 (three invisible characters still passing) is met, and an exhaustive scan finds no invisible character left. The domain-halt decision stays open for Don. Notes are LOW; the standing gate stays open.

R-PR511-eb9194a, PR 511 (agent-registry: a blank name, owner or domain is a 422; padding stripped; S-B6). Applies to this head only. The fetched pull/511/head is eb9194ae: 6 commits over main; the three since my last review are 023811152 (Khmer inherent vowels U+17B4/17B5 and Mongolian U+180B-180D, 180F added), 7fe06c524 (category Cn counts as blank) and eb9194ae (merge of main). All commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. The head is 0 behind main; `git merge-tree` is clean. Against main: models.py +52, a new test file +175. Nothing under .github/.

OBJECTIONS FIRST
1. Category Cn (unassigned) is read from Python's own Unicode tables, so the rule depends on the interpreter's Unicode version (3.14.2 here = Unicode 16.0). A code point assigned in a later version is refused/trimmed on an older Python. Example: U+1C89 is category Lu on this Python (a name ending in it is kept, measured), but it is unassigned before Unicode 16, so on an older interpreter a name ending in it would be silently trimmed and a name made only of it refused. CI's matrix is stated to include 3.11 to 3.14 (not read by me). The commit text says "every code point assigned later"; the converse (assigned-but-new on an old runtime) is not mentioned. LOW-MEDIUM; HIGH on the dependence, I did not run an older Python (NOT VERIFIED).
2. Trailing trim is by design and now covers Cn: "Ag" + U+FFF0 or U+2065 is stored as "Ag" (measured); the same character inside ("A"+U+FFF0+"g") is kept; a trailing emoji variation selector is dropped ("Ag" + a face + U+FE0F stores "Ag" + the face). A Persian name keeps its inner ZWNJ (measured). By design, recorded in the code comment. LOW. HIGH.
3. Domain-halt miss still open (carried, decision for Don): padding is trimmed on write, but the kill-switch domain match is not normalised (NFKC, case, inner ignorables), so a registry domain and a kill domain can still differ by invisible or compatibility characters. Not changed by this PR. MEDIUM-LOW. HIGH that it is unchanged.
4. Legacy rows: AgentRecord (the read model) is deliberately not tightened, so an existing blank owner row still reads back; the pin card is open (carried). LOW.
5. Not verified: the whole agent-registry suite on this head, older Pythons, GX10, CI.

ASSUMPTIONS
A1 "Invisible" = renders as nothing alone (Default_Ignorable and the fillers/blanks). A2 I tested the validator through AgentCreate in-process (the shared validator also serves AgentUpdate).

REASONING / CHECKS
1. Delta read: `_IGNORABLE_CATEGORIES` gains "Cn"; `_IGNORABLE_EXTRA` gains 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F; `_stripped_non_blank` unchanged (trim both ends, refuse if empty, keep inner). HIGH.
2. Exhaustive scan on this head: every code point except surrogates that is not a printable letter/number/punctuation/symbol (959,756 tried), repeated three times as a name: 2,238 accepted, ALL of category Mn (1,757), Mc (468) or Me (13), i.e. combining marks that draw a visible mark. I checked by name that the Default_Ignorable members of those categories (U+034F, 17B4-17B5, 180B-180F, FE00-FE0F, E0100-E01EF) are covered; 0 invisible characters remain accepted. My earlier 3 (U+17B4, 17B5, 180B) are now refused. HIGH (measured, 3.14.2 only).
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1): tests/test_blank_fields_sb6.py 231 passed, 0 failed (12.6 s). I did not run the whole agent-registry suite (about 22 minutes). HIGH on what ran.
4. Mutants on a temp copy of the head, models.py, the new test file only (-x, a kill = pytest rc 1):

| group | mutations | result |
|-------|-----------|--------|
| categories | Cn, Cc, Cf, Cs, Co each dropped | 5 KILLED |
| categories | Zl, Zp, Zs each dropped | 3 SURVIVED (equivalent: str.isspace already covers every Zl/Zp/Zs) |
| extra list | U+034F, 115F, 1160, 3164, FFA0, 2800 each dropped | 6 KILLED |
| extra list | U+17B4, 17B5, 180B, 180C, 180D, 180F each dropped | 6 KILLED |
| ranges | FE00-FE0F range dropped; E0100 range dropped | 2 KILLED |
| trimming | nothing stripped; trailing end not trimmed; ignorable removed everywhere; blank not refused | 4 KILLED |
| whitespace | isspace term removed | 1 SURVIVED (equivalent, same reason) |

Counted: 28 run, 24 KILLED, 4 SURVIVED (all equivalent), 0 NOT APPLIED. HIGH.

CONDITIONS
C1 (non-blocking, new PR) pin the Unicode-version dependence: either test only code points unassigned in the oldest supported Unicode, or state the minimum Python/Unicode and refuse to depend on Cn at the trailing end (trim only default-ignorables).
C2 (decision for Don, carried) normalise the domain on write or match it normalised in the kill-switch (card B-FU-PR511-domain-normalise).
C3 (non-blocking, carried) the legacy blank-owner row pin (card B-FU-PR511-legacy-row).
C4 (standing gate) GX10 16/16 and CI on this exact head; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
Whole agent-registry suite, Python 3.11 to 3.13 behaviour, GX10 / Linux, CI.

CONCLUSION
My condition is met: no invisible character is accepted as a blank name, owner or domain on Unicode 16.0 (959,756 code points scanned; only visible combining marks pass), 231 tests pass and 24 of 28 mutants die (four equivalent), identity correct, merge clean. Left: the Cn rule follows the runtime's Unicode version, and the domain-halt decision is Don's. PASS WITH CONDITIONS on eb9194ae.
