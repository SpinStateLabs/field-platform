# C-61 (was C-7): branch triage, read-only (teammate-don-reviewer, 2026-10-28)

Method (HIGH): git branch -r --no-merged origin/main on a fresh git fetch --prune (main c8ecba7) = 53 branches after excluding comms and the four triaged earlier (ci/harden-workflows-2026-10-23 -> #16, ci/topology-lint-2026-10-23 -> #18, feat/phase-g-check-tool -> #28, feat/claude-approver-v0 -> #35; all squash-merged). For each branch: gh pr list --state all --limit 300 matched on head branch name; 	ip=PRhead means the branch tip sha equals the PR's headRefOid (so the PR merged exactly this tip); Behind/Ahead from git rev-list --left-right --count origin/main...origin/<branch>; content in main = git merge-tree --write-tree origin/main origin/<branch> yields main's own tree (merging adds nothing). A squash merge leaves the branch 'unmerged' by commit graph, hence the 53. Nothing deleted, nothing pushed to any branch.

## Summary
- 46 branches: PR MERGED and branch tip = the PR head -> merged-by-squash (safe delete candidates for C-50, Don's approval). Of these 18 also pass the content-in-main test; the other 28 differ only because main moved on (the branch is stale, not missing work).
- 3 branches: PR CLOSED unmerged and superseded by a merged PR: claude/adr-0072-estate-kill-watcher (#11 closed, superseded by #12, same tree: diff empty), claude/adr-0074-crosswalk-gate-controls (#10 closed, superseded by #13; the closed branch holds 23 lines the successor lacks: dropped on purpose in r2, not verified), feat/pg-s0-guards (#40 closed, 'superseded by #41' per #41's title; #40 has 205 lines #41 lacks and I did NOT verify that each hunk landed via #41/#42/#45: needs one look before deleting).
- 3 branches: OPEN PRs, active: #55 feat/machine-verifier-identity 6e78f31, #56 feat/alerts-ntfy 9cdef89, #57 feat/kr-r4a-rotator-core 09dcbcd (all reviewed, CONDITIONS).
- 1 branch: no PR yet: fix/renew-token-signed 8269445 (C-19/C-30/C-31 live work; do not delete).
- Abandoned with no PR and no merged successor: none found.

## Table (sorted: merged-by-squash by date, then closed, open, no-PR)

| Branch | Tip | main-only/branch-only | Last commit | Content in main | PR | Disposition |
|---|---|---|---|---|---|---|
| feat/field-core-gate-1.2-lockstep | cdbe9c0 | 52/2 | 2026-10-02 | no | #2 MERGED tip=PRhead | merged-by-squash |
| fix/ci-canary-scope | 474565f | 51/2 | 2026-10-03 | no | #3 MERGED tip=PRhead | merged-by-squash |
| claude/field-op-console-features-o54e47 | 955b54c | 48/2 | 2026-10-05 | no | #4 MERGED tip=PRhead | merged-by-squash |
| claude/fly-image-estate-probe | fb4b5f3 | 47/1 | 2026-10-05 | no | #5 MERGED tip=PRhead | merged-by-squash |
| claude/defence-shield-incident-retro | eae2237 | 46/1 | 2026-10-10 | no | #7 MERGED tip=PRhead | merged-by-squash |
| fix/defence-shield-0.1.1-review2 | 40d7d6b | 45/2 | 2026-10-12 | yes | #8 MERGED tip=PRhead | merged-by-squash |
| claude/adr-0071-field-core-lockstep | b001447 | 44/2 | 2026-10-21 | no | #9 MERGED tip=PRhead | merged-by-squash |
| claude/adr-0072-estate-kill-watcher-r2 | 3abeaef | 43/3 | 2026-10-21 | no | #12 MERGED tip=PRhead | merged-by-squash |
| claude/adr-0074-crosswalk-gate-controls-r2 | a2c33f7 | 43/4 | 2026-10-21 | yes | #13 MERGED tip=PRhead | merged-by-squash |
| claude/probe-a2-signed-window | bfdd03e | 40/1 | 2026-10-21 | yes | #15 MERGED tip=PRhead | merged-by-squash |
| claude/runbook-canary-grantor | 1f661e7 | 41/1 | 2026-10-21 | no | #14 MERGED tip=PRhead | merged-by-squash |
| claude/state-fly-ops-console-0.2.0 | 219c4ca | 39/6 | 2026-10-21 | yes | #6 MERGED tip=PRhead | merged-by-squash |
| chore/remove-stray-basetemp-dir | 93c447b | 34/1 | 2026-10-23 | yes | #22 MERGED tip=PRhead | merged-by-squash |
| claude/fix-time-of-day-flake | 81755e6 | 31/1 | 2026-10-23 | yes | #24 MERGED tip=PRhead | merged-by-squash |
| claude/phase-g-operator-auth | fcd0749 | 31/6 | 2026-10-23 | no | #23 MERGED tip=PRhead | merged-by-squash |
| claude/runbook-a2-sentence-2026-10-23 | 01bd072 | 37/1 | 2026-10-23 | yes | #17 MERGED tip=PRhead | merged-by-squash |
| feat/deployment-agent-skeleton | 266a2c5 | 35/4 | 2026-10-23 | yes | #21 MERGED tip=PRhead | merged-by-squash |
| feat/probe-registry-readonly | 0ecc968 | 36/2 | 2026-10-23 | no | #19 MERGED tip=PRhead | merged-by-squash |
| test/redteam-ledger-mint-2026-10-23 | bfc9aa5 | 36/3 | 2026-10-23 | no | #20 MERGED tip=PRhead | merged-by-squash |
| brand/ops-console-force-field | e94694e | 29/1 | 2026-10-24 | no | #25 MERGED tip=PRhead | merged-by-squash |
| feat/gb10-caddy-tls-internal | 1e723b9 | 24/5 | 2026-10-25 | no | #30 MERGED tip=PRhead | merged-by-squash |
| feat/operator-auth-plumbing | 8d99691 | 28/3 | 2026-10-25 | no | #26 MERGED tip=PRhead | merged-by-squash |
| feat/ops-console-setup | 927f8d5 | 28/2 | 2026-10-25 | no | #27 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-clients | 1a1328a | 25/4 | 2026-10-25 | no | #33 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-compose | b5229a1 | 25/2 | 2026-10-25 | no | #29 MERGED tip=PRhead | merged-by-squash |
| fix/upgrade-smoke-isolation | e015a3a | 24/3 | 2026-10-25 | no | #31 MERGED tip=PRhead | merged-by-squash |
| docs/runbook-stage0-alignment | 109a6ab | 19/3 | 2026-10-26 | no | #37 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-cli | 362c462 | 20/6 | 2026-10-26 | no | #36 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-core | 3a963c5 | 16/13 | 2026-10-26 | no | #32 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-followups | 5339208 | 13/7 | 2026-10-26 | no | #42 MERGED tip=PRhead | merged-by-squash |
| feat/pg-s0-guards-2 | c921765 | 14/10 | 2026-10-26 | no | #41 MERGED tip=PRhead | merged-by-squash |
| fix/ledger-reader-rotation-window | 9c9baa3 | 21/3 | 2026-10-26 | no | #34 MERGED tip=PRhead | merged-by-squash |
| fix/small-followups | 9bdd46d | 17/2 | 2026-10-26 | no | #39 MERGED tip=PRhead | merged-by-squash |
| fix/topology-lint-etxtbsy | 5894ccc | 19/1 | 2026-10-26 | yes | #38 MERGED tip=PRhead | merged-by-squash |
| feat/c20-console-key-transport | fa95f96 | 5/5 | 2026-10-27 | yes | #50 MERGED tip=PRhead | merged-by-squash |
| feat/field-agent-fieldclient | 731d527 | 8/1 | 2026-10-27 | yes | #48 MERGED tip=PRhead | merged-by-squash |
| feat/kr-r1-format2-parser | 0db2106 | 4/2 | 2026-10-27 | no | #53 MERGED tip=PRhead | merged-by-squash |
| feat/kr-r2-verify-hash | 7c0b99f | 1/10 | 2026-10-27 | yes | #54 MERGED tip=PRhead | merged-by-squash |
| feat/kr-r3-lifecycle-headers | f8f836f | 4/1 | 2026-10-27 | yes | #51 MERGED tip=PRhead | merged-by-squash |
| feat/pg-c5-fly-identity | 562cb32 | 12/3 | 2026-10-27 | yes | #44 MERGED tip=PRhead | merged-by-squash |
| feat/pre-stage3-followups | fbfcc28 | 12/5 | 2026-10-27 | no | #46 MERGED tip=PRhead | merged-by-squash |
| feat/price-book-55-session-ids | 16a5576 | 12/5 | 2026-10-27 | yes | #43 MERGED tip=PRhead | merged-by-squash |
| fix/doa-roster-job-rows | ab19ddd | 8/4 | 2026-10-27 | yes | #49 MERGED tip=PRhead | merged-by-squash |
| fix/ledger-verify-missing-path | 1203d4d | 8/3 | 2026-10-27 | yes | #47 MERGED tip=PRhead | merged-by-squash |
| fix/signed-operator-ledger-events | 41284d7 | 4/3 | 2026-10-27 | yes | #52 MERGED tip=PRhead | merged-by-squash |
| fix/stage0-hardening-pins | a5ee1a7 | 12/7 | 2026-10-27 | no | #45 MERGED tip=PRhead | merged-by-squash |
| claude/adr-0072-estate-kill-watcher | cc68dc1 | 44/5 | 2026-10-21 | no | #11 CLOSED tip=PRhead | closed, superseded |
| claude/adr-0074-crosswalk-gate-controls | edf22f3 | 44/3 | 2026-10-21 | no | #10 CLOSED tip=PRhead | closed, superseded |
| feat/pg-s0-guards | a15e893 | 16/19 | 2026-10-26 | no | #40 CLOSED tip=PRhead | closed, superseded |
| feat/alerts-ntfy | 9cdef89 | 0/2 | 2026-10-28 | no | #56 OPEN tip=PRhead | open PR |
| feat/kr-r4a-rotator-core | 09dcbcd | 0/6 | 2026-10-28 | no | #57 OPEN tip=PRhead | open PR |
| feat/machine-verifier-identity | 6e78f31 | 0/8 | 2026-10-28 | no | #55 OPEN tip=PRhead | open PR |
| fix/renew-token-signed | 8269445 | 0/1 | 2026-10-28 | no | no PR | no PR, live |

## For Don / C-50
- Delete list (needs Don's go): the 46 'merged-by-squash' rows; evidence line per branch = its PR number and 'tip=PRhead'. Plus (after the check noted above for feat/pg-s0-guards) the 3 'closed, superseded' rows. Plus the four earlier ones. None of the 'open PR' or 'no PR' rows.
- Unknown: whether any branch still holds an unpushed-to-PR commit beyond the PR head: for the 46 the tip equals the PR head, so none; for the 3 closed ones see above.

