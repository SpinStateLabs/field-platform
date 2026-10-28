# TASK-QUEUE

Numbers checked against origin 2026-10-28 (no prior cards).

- C-1 OPEN reviewer: independent review of #57 feat/kr-r4a-rotator-core @09dcbcd. Report PASS/FAIL with file:line, HIGH/MEDIUM/LOW, in inbox/coordinator/.
- C-2 OPEN reviewer: same for #55 feat/machine-verifier-identity @6e78f31 (author must not review own work).
- C-3 OPEN builder: rebase feat/phase-g-check-tool onto main (4 behind), re-run its tests, report new head.
- C-4 OPEN builder: rebase feat/c20-console-key-transport onto main (5 behind), re-run tests, report new head.
- C-5 OPEN builder: open a PR for teammate-don/t1-renew-token-signed (1 commit, renew_token signs ledger appends) with tests evidence.
- C-6 OPEN reviewer: review #56 feat/alerts-ntfy @9cdef89.
- C-7 OPEN builder: branch triage, read-only. For each of the 55 unmerged remote branches (`git branch -r --no-merged origin/main`) decide merged-by-squash / open PR / abandoned using `gh pr list --state all` and diffs. Table to inbox/coordinator/. No deletions.
- C-8 OPEN builder: GB10 catch-up plan, no deploy. GB10 main is cefb81b, origin main c8ecba7 (R1, R2, R3). List changed services, tests to run, rollback, health checks, per `gb10-deploy.sh` practice. For Don's approval; coordinator deploys.
- C-9 OPEN reviewer: review ci/harden-workflows-2026-10-23 @4331864 and ci/topology-lint-2026-10-23 @fd59807 (CI security; both behind main, note rebase need).
- C-10 OPEN builder: draft a STATE.md entry covering merges #48, #50, #51, #52, #53, #54 (2026-10-27) from git log, every number sourced; branch `state/2026-10-28`, PR draft.
- C-11 OPEN reviewer: review feat/machine-verifier-identity follow-up tests (P35) only after C-2 PASS; check the stacked-on-R2 claim in its description against main.
- C-12 OPEN builder: after C-3, C-4: R4b scope note. Read #57 (R4a) docs and propose the next key-rotation slice as a card list. Plan only.
