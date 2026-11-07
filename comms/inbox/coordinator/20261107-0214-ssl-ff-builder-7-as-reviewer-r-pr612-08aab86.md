# Delta review PR 612 (rebuild of #465: runbook section 7, the Phase G "what is on main" paragraph) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `08aab867e68c180769f105dc998dcab030597dae` (draft; docs only, `docs/runbooks/v1.2-deploy-rollback.md`). Reviewer-9's C1 (conflict with main resolved by re-checking, not by choosing a side) and C2 (R3 is #51) are CLOSED. One new factual error in the paragraph remains.
Conditions: C1 (small) the sentence "the squashed commit subjects on `main` do not carry the numbers, so `git log` alone cannot confirm them" (runbook line 1099) is false: on current main the subject of the merge commit of every one of the 17 merged PRs it lists ends with "(#N)" (measured 17 of 17); say instead that a number can be confirmed with `git log --grep='(#N)'`, or drop the sentence. C2 (standing gate) CI and a light GX10 run on this exact head; not run by me.

Independence: I did not build or fix this PR (4 commits, none mine; the merge is builder-8's per its note).

## Checks (HIGH, run by me)
- Identity: 4 of 4 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: head's second parent is current origin/main ff06b3398 (not behind); `git merge-tree` against origin/main is clean. One file vs main: +25/-15, one paragraph. The paragraph keeps main's newer commit ids (#32 68b06053, #36 c2f58643, #41 24453a2e, #44 f6c348f6, #50 ca5e8959) and adds #42, #46, #49, #51 to #54, P35.
- GitHub (`gh pr view`, run now): #23 #26 #29 #30 #32 #33 #36 #41 #42 #44 #46 #49 #50 #51 #52 #53 #54 all MERGED, titles match the items; #760 OPEN (C-20 tools half), matching "NOT merged ... PR #760, open on 2026-11-07". R1 = #53 (format 2 parser), R2 = #54 (verify-hash, rotation state, roster digest, break-glass counters), R3 = #51 (per-request headers in lifecycle-manager): matches the text.
- Cited commits 68b06053, c2f58643, 24453a2e, f6c348f6, ca5e8959, 583519d9, 66aa8695, 34d680c: all ancestors of origin/main; the 583519d9 to 66aa8695 range is 5 commits.
- Tests on the exact head (Windows, py3.14, all service sources on the path): test_runbook_pins_c465 + test_deploy_docs + test_runbook_trust_cites_sd2 + test_environment_doc 107 passed (69 s). `environment_anchors.py --check`: 0 wrong anchor row(s).
- Scan of the added lines for IPv4, 40-hex, mailboxes, key prefixes: none (commit abbreviations, PR numbers, file names only). The paragraph states no estate fact and says so.

## Finding
Line 1099 "the squashed commit subjects on `main` do not carry the numbers" is wrong as measured: for each of #23 #26 #29 #30 #32 #33 #36 #41 #42 #44 #46 #49 #50 #51 #52 #53 #54 the merge commit's subject contains "(#N)" (17 of 17, `git log -1 --format=%s` on each commit). The claim sends a reader away from a check that works, and the paragraph's "checked against GitHub's merged-PR list" stands without it. LOW, HIGH on measurement. The stamp "Checked against main d6db6930" is true but main is ff06b3398 now; harmless while the paragraph says later merges live in tasks/todo.md.

## Not verified
CI; GX10; any estate fact (none stated); the paragraph's "some Status: pending lines below pre-date the merges ... not yet re-read" is the author's own caveat, I did not audit those lines.
