VERDICT: PASS WITH CONDITIONS on 9debfd48246c56b3f3f81952f4fd82908ab644c1  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for my PASS WITH CONDITIONS on 3675644c. My required condition C1 (a blank owner was still creatable with 17 other invisible characters) is met: re-running my probe, the list that passed drops from 17 to 3 truly invisible characters. My C2 (domain normalisation) is, as the builder says, a decision still open. The remaining conditions are small and the standing gate.

R-PR511-9debfd4, PR 511 (scout S-B6: agent-registry blank name, owner or domain is a 422; padding stripped). Applies to this head only. The fetched pull/511/head is 9debfd48: one commit over the head I reviewed (3675644c); models.py +39/-12 net 27 (the five-character list replaced by a categories rule) and the test file +43. Nothing under .github/.

OBJECTIONS FIRST
1. Three invisible characters still pass as a blank name, owner and domain. Probe on this head (the same in-process `AgentCreate`, the character repeated three times as the name): U+17B4 and U+17B5 (Khmer inherent vowels, category Mn, draw nothing) and U+180B (Mongolian free variation selector, Mn) are ACCEPTED. The other five of the eight characters I tried that still pass are visible or draw something and are not defects: U+FFFC and U+FFFD (symbols with glyphs), U+20E3 (combining enclosing keycap), U+302E (Hangul tone mark), U+17D1 (Khmer sign). So the rule is no longer a five-character list but it is still a list of exceptions to the categories, and the Unicode default-ignorable set has more members than it names (U+180C, U+180D, U+180F, U+17B4/5 and others). LOW, HIGH confidence (measured, 38 characters tried: 30 refused, 8 accepted, of which 3 invisible).
2. Trimming now removes legitimate trailing characters. Measured: "Team ❤" + U+FE0F becomes "Team ❤" (the emoji variation selector is trimmed, so the emoji can render as text), and a Hebrew name ending in U+200F (right-to-left mark) becomes the bare letters. Both are the stated rule ("ignorable ends are trimmed", variation selectors included); inner ones are kept (a ZWNJ inside a Persian name, a soft hyphen inside "co-operate", the ZWJ family emoji, a combining acute and the keycap sequence all came back unchanged). LOW.
3. The domain-halt miss is unchanged and is the builder's stated decision (card B-FU-PR511-domain-normalise): GET /agents?domain=finance on this head finds only the agent registered as "finance", not "Finance", "fin\u200bance" or the full-width spelling (measured). The domain rule's stated motive is not met for those spellings. MEDIUM, a decision for Don.
4. Four mutants survive the PR's tests (below) and all four are equivalent: dropping Zl, Zp or Zs from the categories (str.isspace already covers them) and dropping the isspace test (the categories cover every whitespace character). HIGH.

ASSUMPTIONS
A1 "Truly invisible" means the character draws no glyph in common fonts, from its Unicode properties; I did not render them. A2 My earlier report's list (17 accepted) was measured on 3675644c; this report's 3 is measured on 9debfd48, with a larger set tried, so the improvement is a conservative reading.

REASONING / CHECKS
1. Diff read (3675644c..head): `_IGNORABLE_CATEGORIES` (Cc, Cf, Zl, Zp, Zs, Cs, Co), `_IGNORABLE_EXTRA` (U+034F, U+115F, U+1160, U+3164, U+FFA0, U+2800), the variation-selector ranges U+FE00 to U+FE0F and U+E0100 to U+E01EF, plus `str.isspace`; both ends are trimmed, nothing left is a 422; ignorable characters inside are kept; AgentRecord (the read model) is untouched; the decision to treat tag characters and private-use characters as blank is recorded in the code comment. HIGH.
2. Identity: 1 of 1 commit author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core + kill-switch + lifecycle-manager src): the whole agent-registry suite 491 passed, 0 failed (22 minutes; the concurrency test that failed under load on the previous head passed); `environment_anchors.py --check` 0 wrong anchor rows. HIGH.
4. Mutants on a copy of the head, test_blank_fields_sb6.py only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| C1 | Cc dropped | KILLED |
| C2 | Cf dropped | KILLED |
| C3 | Cs dropped | KILLED |
| C4 | Co dropped | KILLED |
| C5 | Zl dropped | SURVIVED (equivalent: isspace covers it) |
| C6 | Zp dropped | SURVIVED (equivalent) |
| C7 | Zs dropped | SURVIVED (equivalent) |
| X1 | U+034F dropped | KILLED |
| X2 | U+115F dropped | KILLED |
| X3 | U+1160 dropped | KILLED |
| X4 | U+3164 dropped | KILLED |
| X5 | U+FFA0 dropped | KILLED |
| X6 | U+2800 dropped | KILLED |
| V1 | U+FE00-FE0F range dropped | KILLED |
| V2 | U+E0100-E01EF range dropped | KILLED |
| S1 | nothing trimmed | KILLED |
| S2 | trailing end not trimmed | KILLED |
| S3 | ignorable characters removed everywhere, not only the ends | KILLED |
| S4 | the blank check removed | KILLED |
| S5 | isspace no longer part of the test | SURVIVED (equivalent) |

Counted from the table: 20 run, 16 KILLED, 4 SURVIVED (all equivalent), 0 NOT APPLIED. The builder's 15 mutants are among these. HIGH.

CONDITIONS
C1 (non-blocking, new PR) add U+17B4, U+17B5 and U+180B to `_IGNORABLE_EXTRA` (or use `unicodedata`-based default-ignorable detection if one is available), with a test per character; decide whether a trailing U+FE0F and U+200F should be trimmed (objection 2) or kept when something visible precedes them.
C2 (decision for Don, carried) normalise the domain on write (NFKC, case folding, ignorable characters removed everywhere) or match it normalised in the kill-switch (card B-FU-PR511-domain-normalise).
C3 (non-blocking) the legacy blank-owner row pin (card B-FU-PR511-legacy-row).
C4 (standing gate) GX10 16/16 and CI on this exact head rebased on main; not run by me. After this verdict the head is frozen except a condition fix.

NOT VERIFIED
GX10 / Linux, CI, the whole kill-switch and lifecycle-manager suites on this head (the PR body reports them), any font rendering.

CONCLUSION
My C1 is met: a blank owner is now refused for 30 of the 38 characters I tried, including every one that passed before except three Khmer and Mongolian ones that draw nothing; 20 mutants, 16 killed and 4 equivalent, 491 tests passing, identity correct. The domain-halt miss remains a decision, and trailing emoji or direction marks are trimmed by design. PASS WITH CONDITIONS: C1 and C3 optional, C2 Don's, C4 the gate.
