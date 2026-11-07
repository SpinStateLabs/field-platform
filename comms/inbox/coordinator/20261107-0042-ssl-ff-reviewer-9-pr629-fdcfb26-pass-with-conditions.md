VERDICT: PASS WITH CONDITIONS on fdcfb26ed9e93883696d26a9f316d6fd5ca8d0aa  (ssl-ff-reviewer-9; docs-only, read against the repository at this head and at origin/main; no tests apply). Re-review of the condition fix for reviewer-10's PASS WITH CONDITIONS on d16a5768. Their C1 (four "not done" items contradicting main) is fixed correctly; their C2 (drifting cites) is fixed for line numbers into the runbook but the fix introduced one heading cite that does not exist and left others that no longer resolve on main.

R-PR629-fdcfb26, PR 629 (docs: itemise Phase G in tasks/todo.md). Applies to this head only. The fetched pull/629/head is fdcfb26e; the condition-fix commit changes tasks/todo.md only (9 insertions, 9 deletions). Base 97dcfec1 is 171 commits behind main; `git merge-tree` of the head into origin/main is clean. Nothing under .github/.

OBJECTIONS FIRST
1. The G25 entry cites a runbook heading that does not exist: `docs/runbooks/v1.2-deploy-rollback.md`, "Stage 2, REQUIRE on the kill-switch only". `grep -c` of that exact text on the head's tree and on origin/main: 0 and 0. The runbook's heading is "*Stage 2, kill-switch only under REQUIRE (step 6, first half).*" (main line 1470). This is the defect the cite-drift condition was meant to remove, introduced by the fix; a reader searching the runbook for the quoted text finds nothing. MEDIUM-LOW, HIGH confidence (measured).
2. Cites that resolve on the PR head's tree but not on current main (checked with grep -c on both): "Resolve before Stage 3" (head 1, main 0); the quoted phrase "image rollback until operator keys are required" (0 and 0: it is the todo's own words, cited as if from the runbook, in the G26 text); and the G23 and G24 entries still cite `docs/runbooks/ntfy-alerts.md:16,51,81-82` by line, which on main are an unrelated ledger-event-types line, a topic sentence and a token-file row. Conversely "Stage controller (P36, G24)", cited for G26, is on main (1) but not on the head's tree (0), so it resolves only after the merge. The note says line numbers are "as of main 97dcfec1", which covers the line cites honestly; the heading and phrase cites above carry no such caveat. LOW-MEDIUM.
3. The "Landed since" clauses are correct. I checked all nine commits as ancestors of current main (`git merge-base --is-ancestor`: yes for 9a2417c0, f3b6870c, 9944ee35, d5dd8238, fd0ac135, ede21674, b1b229f1, 75085ae3, b77408cb) and read each subject: lifecycle edit_refused naming don-admin (G21), the hash-verified internal secret and its test-order fix (G22), senders for the six production classes (G23), the stage controller with dry-run default and its two red-team fixes (G24), the Stage 3 irreversibility notice and rollback rehearsal (G26). The builder deliberately did NOT tick G21 to G24; that is defensible: the estate halves are open. HIGH.
4. All itemised states are "as of main 97dcfec1" by the note; main is now far beyond it, so the page will keep drifting (reviewer-10 raised this). The addition-only structure of the original review is unchanged. LOW.

ASSUMPTIONS
A1 "Resolves" means the exact quoted text occurs in the cited file on the named tree; I did not judge whether a nearby heading would serve. A2 No test reads tasks/todo.md (the builder's check; I grepped tools/tests, packages/*/tests and services/*/tests on main for "tasks/todo.md": no hit).

REASONING / CHECKS
1. Diff read in full (d16a5768..head): the Phase G note now says the "Evidence of state" lines are as of main 97dcfec1 and that headings are the stable cite; G21, G22, G23, G24 and G26 gain a "Landed since" clause; the runbook line cites in G17, G20, G25, G26 become section-heading cites. HIGH.
2. Identity: 3 of 3 commits author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailers Co-Authored-By Claude Sonnet 5.5 only. HIGH.
3. Public safety: a scan of the added lines for IPv4 addresses, 40-hex strings, mailboxes, key prefixes and tokens found none; only commit abbreviations (8 hex), PR numbers and file names. HIGH.
4. Cite resolution, measured with `grep -c -F` on the runbook:

| quoted cite | PR head tree | origin/main |
|-------------|--------------|-------------|
| "GB10 console hop over TLS" | 2 | 2 |
| "Phase 1 alone does NOT close design RT3-1" | 1 | 1 |
| "Stage 3, REQUIRE on all eight" | 1 | 1 |
| "Stage controller (P36, G24)" | 0 | 1 |
| "Resolve before Stage 3" | 1 | 0 |
| "Stage 2, REQUIRE on the kill-switch only" | 0 | 0 |
| "image rollback until operator keys are required" | 0 | 0 |

Counted from the table: 7 cites checked, 3 resolve on both trees, 1 resolves only on main, 1 only on the head, 2 on neither. HIGH.

CONDITIONS
C1 (required, small) correct the G25 cite to the heading that exists ("Stage 2, kill-switch only under REQUIRE (step 6, first half)"); a condition fix is the only push allowed on the head.
C2 (required with the rebase onto main) re-resolve the other cites on the rebased tree: "Resolve before Stage 3" and the ntfy-alerts.md line cites (G23, G24), or mark them "as of main 97dcfec1" like the line numbers; drop the quotation marks on the todo's own phrase in G26.
C3 (standing gate) CI and a light GX10 run on this exact head; not run by me.

NOT VERIFIED
That every commit abbreviation in G1 to G15 still resolves (reviewer-10 checked them on the earlier head; I resolved the nine new ones only); CI; GX10.

CONCLUSION
Reviewer-10's C1 is fixed with correct, checkable evidence (nine ancestor-of-main commits, subjects match the claims). Their C2 is half fixed: the runbook line cites became heading cites, but one of those headings does not exist and others no longer resolve on main. Docs only, identity correct, nothing public-unsafe. PASS WITH CONDITIONS: C1 and C2 are small docs fixes, C3 the gate.
