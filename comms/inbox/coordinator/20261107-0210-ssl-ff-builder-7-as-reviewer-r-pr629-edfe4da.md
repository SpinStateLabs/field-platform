# Delta review PR 629 (docs: itemise Phase G in tasks/todo.md) — ssl-ff-builder-7-as-reviewer

**VERDICT: PASS WITH CONDITIONS** on head `edfe4da7818d4e87b39869d6605c1462acea26a9` (docs only, `tasks/todo.md`; no tests apply). Reviewer-9's C1 (G25 heading) and C2 (re-resolve cites on the rebased tree) are CLOSED (measured below). Remaining conditions are LOW and non-blocking.
Conditions: C1 (non-blocking) two live line cites into CHANGELOG.md have drifted (below); extend the "as of main 97dcfec1" clause to cover CHANGELOG line numbers or cite the headings. C2 (decision for Don, LOW) deploy-history wording in a public file (below). C3 (standing gate) CI on this head (and a light GX10 run if you still want one); not run by me.

Independence: I did not build or fix this PR (4 commits, none mine; the merge is builder-8's per its note).

## Checks (HIGH, run by me)
- Identity: 4 of 4 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; 0 files under .github/.
- Shape: parents of the head are fdcfb26e and current origin/main ff06b3398 (not behind main); `git merge-tree` against origin/main is clean. One file vs main: tasks/todo.md +39/-1.
- Commit abbreviations: all 27 in G1 to G15, G21 to G26 resolve, and all 27 are ancestors of origin/main, subjects match the claim each carries (e.g. 34d680c = "lifecycle-manager: build operator auth headers per request (key rotation R3) (#51)"; 629e8630 "(#23)"). Reviewer-9 resolved only the nine new ones; reviewer-10 the earlier head.
- Quoted runbook headings on this head (`grep -c -F` on docs/runbooks/v1.2-deploy-rollback.md): "GB10 console hop over TLS" 2; "Phase 1 alone does NOT close design RT3-1" 1; "Stage 3 identity rule (rows C1 and T6, G21)" 1; "Stage 2, kill-switch only under REQUIRE (step 6, first half)" 1; "Stage 3, REQUIRE on all eight" 1; "Stage controller (P36, G24)" 1; "NOT verified on the real GB10 ledger until the next Stage 1" 1. 7 checked, 7 resolve, 0 miss.
- Other live cites on this head: `tasks/todo.md:372` is the D16 line (G27) OK; "Gate template" heading present OK; `docs/runbooks/token-renewal.md:1443` is the powershell.exe exit-codes row OK.
- Scan of the added lines for IPv4, 40-hex, mailboxes and key prefixes: none.

## Findings
1. DRIFTED line cites (LOW, HIGH on measurement): G14 says "#51 per `CHANGELOG.md:47`"; on this head line 47 is a Batch H (PR 142) line, and the "PR 51, 34d680c" text is at CHANGELOG.md:73 (at base 97dcfec1 it was :47, so the cite was right when written). G1 says `CHANGELOG.md:108-140`; the "Phase G: authenticated operators (code only)" section is at :134 on this head (it was :108 at 97dcfec1), so :108-133 now covers the claude-approver and Stage 0 sections. The note's as-of clause names "line numbers into the runbooks" only; these two are CHANGELOG cites outside it. The facts cited (#51 is 34d680c; guards section exists) are true.
2. Deploy-history wording (LOW, decision for Don): G16 says "Only the coordinator's memory notes claim 2026-10-27" and G18 says "one GB10 attempt, armed and rolled back 2026-10-27". The public-repo rule excludes deploy status. The GB10 attempt is already stated in the runbook on main (`git grep 2026-10-27` on origin/main: 2 hits in v1.2-deploy-rollback.md, 0 in tasks/todo.md), so this is not a new fact, but todo.md now repeats it and points at private notes. No address, flag value, build id or credential is added.

## Not verified
CI; GX10; that each "Done when" is still unmet beyond reviewer-9's reading; the G1 to G15 PR numbers other than by commit subject (#33 and #51 are prose-sourced, as the note itself says).
