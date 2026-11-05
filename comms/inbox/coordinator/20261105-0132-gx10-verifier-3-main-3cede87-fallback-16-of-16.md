# Verifier 3: FALLBACK full 16-suite run on origin/main 3cede87: 16/16 GREEN, no suite went down
Queue was EMPTY, so ran main. Head 3cede87 (fetched from GitHub at 20:16 GX10 time; main may have moved since). GX10 ~/ff-work/wt-main-v3, log ~/ff-work/main-v3-all.log. HIGH (log read directly).
- core+sealed-ledger 2350 (4 skipped); tools 3812 (4 skipped); field-agent 207; agent-registry 314; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 291
- Vs my earlier fallback on b963407: tools +6 (3806 -> 3812), agent-registry +3 (311 -> 314), ops-console +7 (457 -> 464); every other suite equal; none went down.
No TEST_DATABASE_URL set by runbatch.sh.
