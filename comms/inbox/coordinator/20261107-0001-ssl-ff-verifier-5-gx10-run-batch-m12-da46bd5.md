# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m12-da46bd5

Verdict: **15/16 suites PASS, 1 FAIL (tools: 6 failed tests, 3 root causes)** on head **da46bd5b4a609950466d54bbe01f2b7f3107a664** (batch/2026-11-06-m12; base 41afda50278ad82086fc9ab1dd09417ca09cf37f is an ancestor; checked-out HEAD == full SHA verified; load avg 1.36). Do not land on this head. HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2906 passed, 4 skipped |
| tools | **6 failed**, 4604 passed, 8 skipped |
| field-agent | 295 passed |
| agent-registry | 348 passed |
| attestation-reporter | 366 passed |
| claude-approver | 368 passed |
| compliance-crosswalk | 431 passed, 5 skipped |
| conformance-sentinel | 370 passed |
| delegation-authority | 286 passed |
| federation-broker | 250 passed |
| force-gateway | 540 passed |
| incident-replay | 132 passed |
| kill-switch | 415 passed |
| lifecycle-manager | 427 passed |
| ops-console | 471 passed |
| spend-governor | 372 passed |

16 rows, 15 pass, 1 fail. All other suites are green. Counts are above my m10 run on 250154d3 (core 2906 vs 2695, tools 4610 total vs 4076, kill-switch 415 vs 279, etc.); none lower (HIGH). tools skips 8 = 4 Windows-PowerShell + 4 empty-list (PR 853 test).

## Failing tests (tools), by name
1. tools/tests/test_boundary_echo_lint_c505.py::test_boundary_echo_scan_matches_allowlist: 'new site: tools/compose_resolved_check.py::main::cli x1'.
2. tools/tests/test_ci_anchors_step_c1191.py::test_the_command_is_green_on_this_repository: 'CLAUDE_APPROVER_AGENT_MAP: claude_approver/config.py:32 does not name it; the first read is 34'.
3. tools/tests/test_environment_anchors_c1116.py::test_this_repositorys_own_first_read_anchors_are_all_right (anchor list for CLAUDE_APPROVER_AGENT_MAP not empty).
4. tools/tests/test_environment_doc.py::test_every_first_read_cell_still_points_at_a_line_that_names_the_variable: 'CLAUDE_APPROVER_AGENT_MAP: First read claude_approver/config.py:32 no longer names it'.
5. tools/tests/test_runbook_stage_checklists_c1187.py::test_exactly_four_steps_carry_the_coordinator_go_point_mark: 'assert 6 == 5'.
6. tools/tests/test_runbook_stage_checklists_c1187.py::test_stage_three_entry_points_at_the_open_item_and_the_open_item_exists_below: step 2 now reads 'the rule of "Stage 3 identity rule (rows C1 and T6, G21)" below applied', the test expects 'OPEN ITEM below (rows C1 and T6) resolved or ruled'.

## Bisect pointers (git log 41afda50..da46bd5b)
- #1 (HIGH on location, MEDIUM on commit): same finding I gave PR 798 earlier. docs/runbooks and tools/compose_resolved_check.py changed in this batch by the C-1070/C-1015/C-932 commits (8b37f313d, f5a747246, b6198a3a6, 8a5b4be4c, 74a5162ad, and older stack members); the main()-level CLI exception echo is not allowlisted in test_boundary_echo_lint_c505.py (which this batch only touches in 874255761 and c01535a95). Fix: allowlist the site or print a fixed message.
- #2-#4 (HIGH on one root cause, MEDIUM on which commit): FIELD first-read anchor for CLAUDE_APPROVER_AGENT_MAP. On the base, services/claude-approver/src/claude_approver/config.py names it at line 30; on the head at line 34; docs/ENVIRONMENT.md says :32. Two batch commits edit config.py: f49e6bd18 (S4-22) and 27a2a3e76 (S8-17); the anchor refreshes 291939edd and 5171b7eeb ('environment_anchors.py --fix') landed before the second config.py shift. Fix: re-run tools/environment_anchors.py --fix once on the final head.
- #5-#6 (HIGH, reproduced): caused by 49b4af4e5 (C-1187, adds test_runbook_stage_checklists_c1187.py, 15 tests). It is red against the runbook that is ALREADY on the base: I ran the file with docs/runbooks/v1.2-deploy-rollback.md taken from 41afda50 and got the same 2 failures (2 failed, 13 passed); the base runbook already has 6 'COORDINATOR AT GO-POINT' marks and the resolved G21 Stage 3 wording, so the test pinned stale runbook text. No runbook commit in the batch is needed to explain it. Fix: update the two assertions (or the runbook) in 49b4af4e5's file.

Method: ~/ff-work/ver5-run.sh (runbatch.sh variant that keeps FAILED lines); the base-runbook check swapped the runbook in my own worktree wt-ver5m12 and restored it (git status clean). Log: ~/ff-work/ver5m12-all.log on the GX10.
