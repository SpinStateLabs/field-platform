VERDICT: PASS on 4c81fa611fa592b8b7b3723702d9f86274fe0914  (ssl-ff-reviewer-9; Windows, no GX10, CI not read). Re-review of the condition fix for the Lane O review (PASS WITH CONDITIONS on 97a86272). The docs-pin condition is met; the GX10 gate stays open.

R-PR707-4c81fa6, PR 707 (S6-7, agent-registry docs: PATCH resolves manifest_ref when an operator mode is armed). Applies to this head only. The fetched pull/707/head is 4c81fa61.

OBJECTIONS FIRST
1. Docs claims drift silently unless pinned; the Lane O review showed 7 of 9 wrong doc edits passing. The fix asserts exact sentences. I re-ran all 7 survivors and the 2 earlier kills against the new head (item 4): all 9 die. HIGH.
2. A README sentence still carries one unpinned detail: changing "unkillable, 503" to "unkillable, 500" passes all 16 tests (my extra mutant D10). The 503 is the status a later request gets when an agent whose manifest_ref does not resolve is looked up (api.py comment line 269-270); it is a claim about a different code path than the PATCH tests. LOW.
3. Base is ebb027a2, 60 commits behind main (the Lane O review saw it 0 behind). `git merge-tree --write-tree origin/main <head>` is clean (tree id printed, no conflict lines); the touched files are agent-registry README/SPEC/api.py comment and two test files. HIGH.
4. The change in api.py is a comment only; behaviour pinned by the tests was the Lane O baseline. I did not diff the code against main beyond the comment lines and the code mutants below. HIGH.

ASSUMPTIONS
A1 The Lane O baseline (22 mutants: B1 armed 7, B2 off 3, B3 resolvable 3, B4 docs 9) is the reference; I re-ran its 9 doc mutants and 3 code mutants of my own for B1/B2.

REASONING / CHECKS
1. Diff: the condition-fix commit 4c81fa61 is one file, tests/test_patch_manifest_ref_by_mode.py, +41 (git diff 97a86272..head). README row, SPEC and the api.py comment are unchanged from the head Lane O reviewed. Nothing under .github/. HIGH.
2. Identity: 2 of 2 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Doc claims re-derived from code on the head: operator_auth.mode() returns ENFORCE when FIELD_OPERATOR_REQUIRE is on, LOG_ONLY when FIELD_OPERATOR_REGISTRY is set, else OFF; the PATCH handler resolves manifest_ref only inside `if needs and operator_auth.mode() != OFF` and raises 422 with the unresolvable_manifest_ref payload; patch.manifest_ref, owner or domain each add the registry_edit need. The README and SPEC sentences match. HIGH.
4. Tests on the exact head (D:/venvs/field-mcp-l1, PYTHONUTF8=1, head src + field-core src): new file 16 passed; whole agent-registry suite 327 passed, 0 failed (742 s). HIGH.
5. Mutants on a copy of the head, new file only, -x, a kill = pytest rc 1:

| id | mutation | result |
|----|----------|--------|
| D1 | README: log-only and enforce variables swapped | KILLED |
| D2 | README: "Declared only (... Enforced in code when armed)" parenthetical removed | KILLED |
| D3 | README: registry_edit -> registry_read | KILLED |
| D4 | SPEC: "log-only or enforce" -> "enforce only" | KILLED |
| D5 | SPEC: off clause flipped to "it is too" | KILLED |
| D6 | SPEC: refused 422 -> 409 | KILLED |
| D7 | api.py comment: armed -> OFF | KILLED |
| D8 | README: refuses it with 422 -> 409 | KILLED |
| D9 | README: "does NOT check it" -> "checks it" | KILLED |
| D11 | README: mode OFF -> mode ON | KILLED |
| C1 | code: armed check removed | KILLED |
| C2 | code: check runs even with the mode OFF | KILLED |
| C3 | code: refusal status 422 -> 409 | KILLED |
| D10 | README: unkillable, 503 -> 500 | SURVIVED (objection 2) |

Counted from the table: 14 run, 13 KILLED, 1 SURVIVED, 0 NOT APPLIED. The 7 Lane O survivors (D1-D7) are all KILLED now. Per behaviour: doc statements 10 mutants (9 killed), armed refusal code 3. HIGH on the counts.

CONDITIONS
C1 (standing gate) GX10 16/16 on this exact head rebased on main; not run by me. After this PASS the head is frozen; the optional LOW (the 503 detail) goes in a new PR if wanted.

NOT VERIFIED
GX10 / Linux, CI, the 503 claim's own code path beyond the comment line.

CONCLUSION
The Lane O condition (pin the exact doc sentences) is fixed: all 7 earlier survivors now die, a tests-only change, behaviour unchanged, 327 tests pass, identity correct, merge clean. One LOW survivor remains (the 503 figure). PASS on 4c81fa61; the GX10 gate remains the coordinator's.
