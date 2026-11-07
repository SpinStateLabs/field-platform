# Verifier 3: FALLBACK full 16-suite run on origin/main 2bc5643: 16/16 GREEN, no suite went down
Queue EMPTY, so ran main. Head 2bc5643 (fetched 14:47 GX10 time; main may have moved since). GX10 ~/ff-work/wt-main-v3, log ~/ff-work/main-v3-all.log. HIGH (log read directly).
- core+sealed-ledger 2946 (4 skipped); tools 4358 (8 skipped); field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 (5 skipped); conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372
- Vs my previous main run (ccd013d): tools +83 (4275 -> 4358); every other suite equal; none lower.
- Note: PR 857 (ssl-fp agents) showed lifecycle-manager 460 vs 450 here; main has no such +10, so those come from PR 857 or its base, not main.
No TEST_DATABASE_URL set by runbatch.sh.
