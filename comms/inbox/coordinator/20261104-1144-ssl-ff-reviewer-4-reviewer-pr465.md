# Reviewer report: PR 465 @ d6fa23898d49fa5655956526ab2d03e7936492e3 (C-1186)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Docs only: one file, docs/runbooks/v1.2-deploy-rollback.md, +19/-17, one commit.

## Objections first
1. The paragraph is prose with no pin test: a wrong PR number or a stale claim cannot fail CI (shown by the mutant table).
2. It is anchored to main 6385f877; main is now 97dcfec1, so "checked against main" is a statement about an older sha.
3. It now says #36 and the guards slice are merged while `Status: pending PR #36` (line 1128) and `Status: pending the guards slice ... (C-12)` (line 1803) remain in the same file: a reader meets a contradiction.

## Verified (git log on 6385f877, full history fetched)
- All 13 PR numbers (#23 #26 #28 #29 #30 #32 #33 #36 #41 #42 #44 #46 #50) appear in merged commit subjects on 6385f877 with the matching content (HIGH). The C-1..C-20 ids cited per PR match those subjects.
- #41 touches services/kill-switch api.py and tests/test_c19_kill_switch.py: "kill-switch half of C-19" is supported (HIGH). #36 subject names renew_token, provision_ssl_agents, estate_probe, service CLIs, DOA job grantors (HIGH).
- C-20 tools half: no commit subject names it; tools/estate_probe.py:954 and tools/phase_g_check.py:748 on origin/main still describe "non-loopback, non-private" http handling, so "not known to be merged" is the honest statement (MEDIUM; the doc says "I do not know", which is correct).
- Identity: author and committer both Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No estate address, flag value, build id or deploy status in the diff (HIGH).
- Merge with current main 97dcfec1: `git merge-tree --write-tree` returned a tree, no conflict (HIGH).

## Mutants (docs claims, scratch worktree on the head, relative PYTHONPATH)
Suite: tools/tests/test_deploy_docs.py, test_runbook_pins_c465.py, test_gb10_caddy_tls.py, test_operator_mounts_b6.py. Baseline (unmutated head) = 5 failed, 102 passed; identical on main (5 failed, 102 passed): the 5 baseline failures are a missing-dependency environment issue, not counted as kills.

| # | Mutant | Result | Killed |
|---|---|---|---|
| M1 | guards slice #41 -> #40 | 5 failed, 102 passed | no |
| M2 | pre-Stage-3 follow-ups #46 -> #47 | 5 failed, 102 passed | no |
| M3 | (sed did not apply; invalid, excluded) | n/a | n/a |
| M4 | checked-against sha 6385f877 -> 1111111 | 5 failed, 102 passed | no |
| M5 | #50 description dropped | 5 failed, 102 passed | no |
| M6 | Fly identities #44 -> #45 | 5 failed, 102 passed | no |

Totals counted from the table: 5 valid mutants, 0 killed, 5 survived (M3 excluded). Survivors were run against the four-file set above (the same run); I did not run the whole 16-suite set. Expected for a prose PR; the coordinator ruling on C-1187 treated a missing pin for checklist prose as a follow-up, so I treat this as LOW, not blocking.

## Findings
- F-C1186-1 MEDIUM-LOW: docs/runbooks/v1.2-deploy-rollback.md:1128 and :1803 still carry `Status: pending` for merged work (#36, guards slice). The new paragraph discloses this ("not yet re-read") but does not fix it. Follow-up PR, not blocking.
- F-C1186-2 LOW: no pin test for the merged-PR list (see mutants).
- F-C1186-3 LOW: sha anchor 6385f877 is behind main 97dcfec1; merge is clean.

## Verdict: PASS WITH CONDITIONS on d6fa23898d49fa5655956526ab2d03e7936492e3
Conditions (coordinator): CI green on this exact head; GX10 light run "docs only" per the 2026-10-29 ruling; head unchanged at merge time. Not run by me: CI, GX10.
