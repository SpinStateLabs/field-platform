# Q-04 reviewer report: tasks/todo.md open items that merged code has closed (main 7b4d6f7 plus PR 94 clone)

VERDICT: of 21 unchecked boxes (72 are checked), 9 name a headline artifact that exists on main and are almost certainly stale; 5 are gates with evidence but no recorded sign-off; 5 are Phase E documentation items (not closed by code); 2 are the deploy line and a decision for Don. I checked headline artifacts only, not each sub-bullet.

OBJECTIONS FIRST
1. "The artifact exists" does not prove every sub-item (a), (b), (c) of the box is done; closing a box needs its owner to read its sub-bullets.
2. The C and D items predate the PR workflow (single squashed history), so no PR number closes them; I name the code instead, as the backlog asked for PR numbers where they exist.
3. 1,908 lines read by their checkbox lines and a spot check of the last section, not in full.

ASSUMPTIONS
1. `git show origin/main:tasks/todo.md` (1,908 lines): 21 `- [ ]`, 72 `- [x]`. Existence checked by grep and `ls` on `~/ff-work/r08c` (main 7b4d6f7 + PR 94 test change). [HIGH]

REASONING
1. Stale, artifact on main (9): C1 line 1095 (`POST /export`: sealed-ledger api.py:441; `ledger export` cli.py:454); C2 :1132 (retention by rotation: retention.py, `/rotate` api.py:488, `/retention/check`); C3 :1221 (RACI from data: incident-replay engine.py `raci_sources`); C4 :1254 (period window and signature: attestation_reporter window.py, signing.py); D1 :1326 (throttle: spend-governor core.py `THROTTLED`, `window_retry_after`); D2 :1428 (gateway `TelemetrySummary`, force_gateway api.py:376); D3 :1505 (`scan_api_keys`, agent_registry discover.py:278); D4 :1546 (compliance-crosswalk regwatch.py); D5 :1609 (`fedbroker add-contract --pubkey`, federation_broker cli.py:44 `_pubkey_pem`). Evidence that these shipped also sits in the R-series reports (R-08, R-09, R-14, R-15, R-16). [HIGH on existence, LOW on sub-item completeness]
2. Gates (5): A-gate :875, C-gate :1309, D-gate :1647, E-gate :1828 ("full sweep (13 services + 2 packages), CI green") and the Phase G box :590. The gates are checkpoints: CI runs every service except defence-shield (C-143), and my gx10_verify runs on PR heads were green (7b4d6f7, 6f5ee96); but no dated sign-off is recorded next to the boxes. Phase G (:590, "COMMITTED, scoped"): built and deployed flags-OFF (code merged across the Phase G PRs, 58-94 hardening), not armed on any estate; the box should say "built, not armed" rather than stay a bare open box. [HIGH on the evidence, MEDIUM on what the author meant by gate]
3. Phase E (5): :598 (the words, LAST), E1 :1761 (`docs/capstone-evidence/v2-one-liners.md`: the directory holds `v2-one-liners-source.md` only, no `v2-one-liners.md`), E2 :1803 (README/ROADMAP/service READMEs), E3 :1819 (STATE.md: STATE.md exists with a "Current phase" section at :330, whether it was rewritten for v1.2 I did not read), E4 :1825. These stay open unless someone reads them; the R-/Q-series reports (R-16 F-R16-1, Q-01 pending) show the READMEs still being corrected. [MEDIUM]
4. Deploy and decision (2): :1897 "Deploy to GB10 + Fly after merge" (needs Don on rog-command, `fly auth login`): the estates have been deployed since (the coordinator's notes and memory record live deploys, GB10 and Fly), so the box is stale but the evidence is outside this repo (STATE.md says what is deployed; Q-05 covers it); :1899 "Decision (Don): portal 'Open Ops Console' link" is Don's and remains open. [MEDIUM]
5. Not found: any open box that a PR between 58 and 94 closed; those PRs are review-driven fixes with no todo boxes. [HIGH]

CONCLUSION
Check off C1-C4, D1-D5 (after the owners read their sub-bullets), record dated gate sign-offs or leave them open, change the Phase G box to "built, not armed", and decide E1's file name. Not done: sub-bullet verification and STATE.md (Q-05).
