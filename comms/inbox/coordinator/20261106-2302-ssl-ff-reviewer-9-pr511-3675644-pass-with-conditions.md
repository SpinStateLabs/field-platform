VERDICT: PASS WITH CONDITIONS on 3675644cfbb95f66fd9741e4d9162caab64d1029  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for the Lane O PASS WITH CONDITIONS on c42b3488. Its condition C2 (zero-width characters) is met for the five characters it named. But the PR's stated purpose, that no agent has a blank human owner, is still bypassable with many other invisible characters (measured), and the domain-halt miss that motivated the domain rule is not closed. C1 below is a required fix or a ruling.

R-PR511-3675644, PR 511 (scout S-B6: agent-registry blank name, owner or domain is a 422; padding stripped). Applies to this head only. This fix changes code (models.py). The fetched pull/511/head is 3675644c.

OBJECTIONS FIRST
1. The blank rule is a list of five characters, so the registry's "one hard rule" (a human owner) is still bypassable. In-process on this head, `AgentCreate(agent_id="a1", name=<c>*3, owner="o", domain="d")` is ACCEPTED, and stored, when <c> is any of: U+00AD soft hyphen, U+2800 braille blank, U+3164 Hangul filler, U+115F Hangul choseong filler, U+FFA0 halfwidth Hangul filler, U+180E Mongolian vowel separator, U+200E and U+200F (left and right marks), U+202A and U+202E (bidirectional embedding and override), U+2062 invisible times, U+034F combining grapheme joiner, U+FE0F variation selector, U+E0020 (a tag character), U+E000 (private use), U+0000 NUL and U+007F DEL. Refused in the same probe: U+200B, U+FEFF, U+2060 (of the five), U+2028, U+0085, U+3000, U+202F and a lone surrogate (U+200C and U+200D are covered by mutants V4 and V5, not by this probe). The same tests apply to owner and domain (one shared validator). So an owner of "⠀⠀⠀" or "ㅤ" renders as blank and is stored. HIGH (measured, 25 characters tried; 17 accepted, 8 refused). The repo already has the better rule in another PR: PR 665's org.py refuses the Unicode categories Cc, Cf, Zl and Zp (the same rule the crosswalk signer uses).
2. The reason the PR gives for the domain rule is not closed either. The kill-switch halts a domain with `list_agents(domain=domain)` (kill_switch api.py line 669), an exact string match on the stored value (measured through GET /agents?domain=finance: it returned only the agent registered as "finance"). Agents registered as "Finance", "fin\u200bance" (an invisible character INSIDE, which this fix deliberately keeps), the full-width "ｆｉｎａｎｃｅ", "finance\u2800" and "fin\u00adance" were all created (201) and stored unchanged, and none of them is found by the domain "finance". So a halt for "finance" still misses five spellings of it; only the padded " finance" is now caught. The PR says case folding was not investigated. MEDIUM, HIGH confidence (measured, 6 registrations, 1 found).
3. Mutant V11 (a `None` on PATCH refused) survives the new test file (67 passed); the Lane O review says older tests kill it, which I did not re-run. LOW.
4. A full agent-registry run on the head: 377 passed, 1 failed (tests/test_registry_store_concurrency.py::test_concurrent_reads_and_writes_..., "8 worker threads still running after 60 s: deadlock"). It failed twice (once in the 17-minute run, once alone at 130 s) while this box was running my other jobs, then PASSED on a re-run (68 s) with the box quieter; on main it passes (106 s). The test has a 60 s join budget for 8 threads; the PR changes only request-boundary validators, not the store. I judge it load-induced, but I did not run it ten times: MEDIUM confidence that it is unrelated, and it should be watched on the GX10.
5. Base is cd3b7690, 67 commits behind main; `git merge-tree --write-tree origin/main <head>` is clean (tree id only). HIGH.

ASSUMPTIONS
A1 "Blank" for a human owner means "renders as nothing"; I did not decide which of the accepted characters a deployment wants as a name (a tag character or private-use character is not invisible by every font). A2 The kill-switch matching is read at line 669 and measured through the registry list filter it calls.

REASONING / CHECKS
1. Diff against the reviewed head (c42b3488..head), read in full: models.py adds `_INVISIBLE` (U+200B, U+200C, U+200D, U+2060, U+FEFF) and the shared validator now loops `v.strip().strip(_INVISIBLE)` until stable (so interleaved padding goes), then refuses an empty result; an invisible character inside a value is kept. AgentRecord (the read model) is untouched, as the PR says. Nothing under .github/. HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core + kill-switch + lifecycle-manager src): test_blank_fields_sb6 67 passed (it passes inside the full run); whole agent-registry suite 377 passed, 1 failed (objection 4: passes alone on re-run). HIGH on the counts.
4. Mutants on a copy of the head, test_blank_fields_sb6.py only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| V1 | invisible strip removed | KILLED |
| V2 | single pass only (no loop) | KILLED |
| V3 | U+200B dropped from the set | KILLED |
| V4 | U+200C dropped | KILLED |
| V5 | U+200D dropped | KILLED |
| V6 | U+2060 dropped | KILLED |
| V7 | U+FEFF dropped | KILLED |
| V8 | whitespace strip dropped | KILLED |
| V9 | invisible characters removed everywhere (not only the ends) | KILLED |
| V10 | blank check removed | KILLED |
| V11 | None on PATCH now refused | SURVIVED (older tests, per Lane O) |
| V12 | stripped value not returned (the original is stored) | KILLED |

Counted from the table: 12 run, 11 KILLED, 1 SURVIVED, 0 NOT APPLIED; one more edit of mine (V13, dropping the validator from the PATCH domain) did not match the code and is not counted. The builder's 7 mutants are V1, V2, V4 to V7 and V8/V9 and die here. The mutants test the five-character design; the design is what objections 1 and 2 question. HIGH on the counts.

CONDITIONS
C1 (required, or a ruling by Don before merge) objection 1: make "blank" mean what the PR says, with the categories rule the repo already uses (PR 665's org.py: refuse Cc, Cf, Zl, Zp, and decide the Hangul fillers, the braille blank and the combining joiner), applied to the stored owner/name/domain and tested with one example per class; or state in the PR and models.py comment that only five characters are covered and that the blank-owner protection is therefore cosmetic. A condition fix is the only push allowed on the head.
C2 (decision for Don or a follow-up card) objection 2: normalize a domain on write (NFKC, case folding, invisible characters removed everywhere, not just at the ends) or match it normalized in the kill-switch; today a domain halt misses five spellings.
C3 (non-blocking) pin that a legacy row with a blank owner still lists (the Lane O optional point, carded as B-FU-PR511-legacy-row), and watch the concurrency test on the GX10.
C4 (standing gate) GX10 16/16 and CI on this exact head rebased on main; not run by me.

NOT VERIFIED
GX10 / Linux, CI, the other suites (kill-switch and lifecycle-manager run by the PR body at 270 and 269 passes; not re-run), whether the concurrency test failure repeats on a quiet machine.

CONCLUSION
The Lane O condition is met: the five zero-width characters are stripped at both ends, interleaved padding is handled, the read model is untouched, 11 of 11 non-surviving mutants die and 67 tests pass. But a blank owner is still creatable with at least seventeen other invisible or non-printing characters, and the domain-halt miss that motivated the domain rule remains for five spellings. PASS WITH CONDITIONS: C1 required (a categories rule or a stated limit), C2 Don's, C3 optional, C4 the gate.
