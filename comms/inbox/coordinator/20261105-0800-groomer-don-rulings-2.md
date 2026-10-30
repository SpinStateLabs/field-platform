# Don's rulings, round 2 (groomer, Lane 9, interview with Don, 2026-11-05). These are Don's own answers.
- D-12: build the internal-only secret (FIELD_INTERNAL_SECRET, C-54 plan) as a Phase G Stage 2 prerequisite; per-agent secrets later.
- D-19: BLOCK keyless contracts now in federation-broker; replay binding deferred.
- D-20: REFUSE a catch-all (/0) allowlist in defence-shield.
- D-21: startup WARNING when a service starts open; keep the demo compose defaults; no refusal.
- D-18: REJECT a verifier-scoped row without the exact svc-verifier- prefix.
- D-6: KEEP halting (fail closed) until an R9 reconcile exists (C-29, PR 57 rework C-496).
- C-478: DEFER hash-pinned requirements until C-459 has soaked.
- Soak item 1 (25 h scheduler soak): shorten the scheduler intervals for the soak run by environment override only.
Cards: D-12 and D-19 to D-21 and D-18 and the soak docs are the six new builder cards at the end of the queue before the lane block (see TASK-QUEUE.md). Not asked, still open for Don: D-16 (six more branch deletes), D-25 (38 more branch heads), the broader 245-branch delete, the repository variable COMMIT_IDENTITY_ALLOW_DOMAIN, soak items 2 (C0 cadence: already ruled every 5 minutes on 2026-11-02, C-495), 3 (PR 57 `_soak` 24 h to 1 h, waits on PR 57) and 4 (owner of scripts outside the repo).
