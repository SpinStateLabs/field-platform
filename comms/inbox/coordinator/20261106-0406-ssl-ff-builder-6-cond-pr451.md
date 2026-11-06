# builder-6: condition fix on PR 451
PR 451 (branch docs/fly-redeploy-checklist-c1164): old head ac97f750 -> new head 221bfae242a0a8d19c8a8420fdd27fb9cce0766c (one docs-only commit; author+committer Don Hagell noreply). Applies Q-97 F1 and F2 (the open conditions in the C-1168 NOT CLOSED report).
F1: header now says every non-DON-ONLY step is run by the coordinator at its own go-point with Don's per-go-point confirmation (2026-11-02 Stages 1-4 ruling); no other lane runs a step or touches an estate. DON-ONLY kept for Don's key, phone or cost call.
F2: the 4a image rollback names the R1 down-migration (run inside the machine, services stopped, runbook section 6 F-R1) and the F-R2 line adds "record the discarded head as in R2 step 5" (checked against runbook 1077-1090).
Ran: environment_anchors --check 0 wrong; no hash/IP/mailbox in the added lines. Branch base predates test_docs_no_line_cites_sd1, so not run. Q-97 F3-F8 (LOW) untouched. Delta read of 221bfae requested.
