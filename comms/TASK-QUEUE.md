# TASK-QUEUE

Numbers checked against origin 2026-10-28 (no prior cards).

- C-1 DONE reviewer (verdict in inbox/coordinator/20261028-0840-*): independent review of #57 feat/kr-r4a-rotator-core @09dcbcd. Report PASS/FAIL with file:line, HIGH/MEDIUM/LOW, in inbox/coordinator/.
- C-2 DONE reviewer (verdict in inbox/coordinator/20261028-0840-*): same for #55 feat/machine-verifier-identity @6e78f31 (author must not review own work).
- C-3 OPEN builder: rebase feat/phase-g-check-tool onto main (4 behind), re-run its tests, report new head.
- C-4 OPEN builder: rebase feat/c20-console-key-transport onto main (5 behind), re-run tests, report new head.
- C-5 OPEN builder: open a PR for teammate-don/t1-renew-token-signed (1 commit, renew_token signs ledger appends) with tests evidence.
- C-6 DONE reviewer (verdict in inbox/coordinator/20261028-0840-*): review #56 feat/alerts-ntfy @9cdef89.
- C-7 OPEN builder: branch triage, read-only. For each of the 55 unmerged remote branches (`git branch -r --no-merged origin/main`) decide merged-by-squash / open PR / abandoned using `gh pr list --state all` and diffs. Table to inbox/coordinator/. No deletions.
- C-8 OPEN builder: GB10 catch-up plan, no deploy. GB10 main is cefb81b, origin main c8ecba7 (R1, R2, R3). List changed services, tests to run, rollback, health checks, per `gb10-deploy.sh` practice. For Don's approval; coordinator deploys.
- C-9 DONE reviewer (verdict in inbox/coordinator/20261028-0840-*): review ci/harden-workflows-2026-10-23 @4331864 and ci/topology-lint-2026-10-23 @fd59807 (CI security; both behind main, note rebase need).
- C-10 OPEN builder: draft a STATE.md entry covering merges #48, #50, #51, #52, #53, #54 (2026-10-27) from git log, every number sourced; branch `state/2026-10-28`, PR draft.
- C-11 CLOSED: stacked-on-R2 claim resolved (#55 base is main, R2 merged); re-review is C-16.
- C-12 OPEN builder: after C-3, C-4: R4b scope note. Read #57 (R4a) docs and propose the next key-rotation slice as a card list. Plan only.
- C-13 OPEN builder: #55 feat/machine-verifier-identity, fix reviewer C-2 conditions 1 (row-attribute or refuse scope set without `svc-verifier-` prefix; `operator_auth.validate_rows`), 2 (test the alias-mint path in delegation `api.py`), 4 (revoke 404 vs 403 oracle). Rebase-free: push to the branch, report head.
- C-14 OPEN builder: #56 feat/alerts-ntfy, fix C-6 condition 1: empty `ProxyHandler({})` in `alerts.py` plus a test with `http_proxy` set. Report head.
- C-15 OPEN builder: #57 feat/kr-r4a-rotator-core, add the hook-based TOCTOU test for the `key_sha256` check (`rotation.py` ~1544); implement provisional D-5 (retry cap plus CRITICAL alert) as a separate commit. Report head.
- C-16 OPEN reviewer: after C-13..C-15 heads land, re-review each exact head; meanwhile read #57 `rotation.py` line by line (reviewer did not) and report findings.
- C-17 OPEN reviewer: run the remaining ~100 of #57's 111 mutants on the GX10 in your own worktree; report survivors.
- C-18 OPEN cloud-reviewer: (read-only, no GX10 needed) line-by-line read of #57 `packages/field-core/src/field_core/rotation.py` @09dcbcd (1,640 lines; the local reviewer read only diff_guard, _promote, _verify_current). Findings with file:line, HIGH/MEDIUM/LOW. Results are UNVERIFIED until the coordinator re-runs anything on the GX10. This takes the read part of C-16; the local reviewer keeps the re-reviews and C-17.
