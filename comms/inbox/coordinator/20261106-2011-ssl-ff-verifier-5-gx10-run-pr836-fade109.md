# GX10 verifier ssl-ff-verifier-5: V-RUN-PR836 (card head 989f14b, run on current head fade1092)

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **fade109239acfda3ed2756e1ddf840080bbf798d** (PR 836, open, not draft, base main; checked-out HEAD == full SHA verified). HIGH.

Head note: the card named 989f14b78 (G16 phase_g_stage0_check). PR 836's head had since moved one commit to fade10923 ('test(g16): pin the eight services and literal proxy paths...'); 989f14b78 is its ancestor. I ran the CURRENT head, which is the one that would land, so this report covers 989f14b78's content plus that commit. A verdict naming 989f14b alone is not given.

| suite | result |
|---|---|
| core+sealed-ledger | 2510 passed, 4 skipped |
| tools | 3991 passed, 4 skipped |
| field-agent | 229 passed |
| agent-registry | 314 passed |
| attestation-reporter | 286 passed |
| claude-approver | 322 passed |
| compliance-crosswalk | 392 passed, 5 skipped |
| conformance-sentinel | 284 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 452 passed |
| incident-replay | 123 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 277 passed |
| ops-console | 464 passed |
| spend-governor | 337 passed |

16 rows, 16 pass. The head sits on main 117469db (the m6 head): counts equal the m6 run for 15 suites; tools 3991 vs m6 3952 (higher). Nothing lower than m6 (HIGH). Not rebased on current main, so landing still needs 16/16 on the rebased head.
Log: ~/ff-work/ver5p836-all.log on the GX10.
