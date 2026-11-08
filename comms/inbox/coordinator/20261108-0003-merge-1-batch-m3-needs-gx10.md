# merge-1: batch m3 @62a3f8578e461054ab55172ad796486b17c07e40 (main 2bc5643e, PR 950) - queue ONE GX10 run
PRs: 920 (8df3d82, DRAFT, sealed-ledger README/SPEC), 885 (0e14b75, DRAFT, incident-replay + ENVIRONMENT.md), 881 (d7b3bb9, DRAFT, field_core.http, 5 commits). 7 commits, clean cherry-picks, identity Don Hagell, nothing under .github/.
Evidence: 920 reviewer-12 PASS + verifier-7 16/16 on 8df3d82; 885 reviewer-12 PASS + verifier-2 16/16 on 0e14b75 (base ccd013d); 881 reviewer-13 PASS + verifier-2 16/16 on d7b3bb9 (base ccd013d). 885 and 881 both edit docs/ENVIRONMENT.md: the batch GX10 run is the check for file:line pins.
Needs: CI 7/7 on PR 950 and GX10 16/16 naming 62a3f857. Verifier item: RUN:BRANCH batch/2026-11-07-m3@62a3f85.
Left out: 890 (PASS WITH CONDITIONS, test-pin C1/C2 not shown met), 870 (conditions, 15 commits, runbook), 868 / 660 / 789 / 629 conflict on cherry-pick (builder rebuild), 825 conflict (report 2352), 774 13 behind, others 134-413 behind.
