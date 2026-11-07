# Verifier 3: FALLBACK full 16-suite run on origin/main ccd013d: 16/16 GREEN, no suite went down
Queue EMPTY, so ran main. Head ccd013d (fetched 10:35 GX10 time; main may have moved since). GX10 ~/ff-work/wt-main-v3, log ~/ff-work/main-v3-all.log. HIGH (log read directly).
- core+sealed-ledger 2946 (4 skipped); tools 4275 (8 skipped); field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 (5 skipped); conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372
- Counts identical to my PR 825 run (head 0 behind this main). Vs my previous main run (aab217d, 2026-11-05): every suite higher or equal (e.g. core 2398 -> 2946, tools 3812 -> 4275), none lower. tools skipped 4 -> 8 is on main itself; which tests skip not examined (LOW).
No TEST_DATABASE_URL set by runbatch.sh.
