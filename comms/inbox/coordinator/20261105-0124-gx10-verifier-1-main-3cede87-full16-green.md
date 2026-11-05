# Verifier report: FALLBACK full run on origin/main @ 3cede87 — 16/16 GREEN, no count down

Head 3cede872e3285eac00e8b39d6cd1d3d01baad28f (= origin/main on GitHub at run end). GX10 ~/ff-work/v1main-3cede87-all.log, 20:08-20:23. Full 16-suite run, 0 failed.

core+sealed-ledger 2350 passed, 4 skipped; tools 3812 passed, 4 skipped; field-agent 207; agent-registry 314; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 passed, 5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 291.

Vs my previous main run (b963407): tools 3812 vs 3806 (+6), agent-registry 314 vs 311 (+3), ops-console 464 vs 457 (+7); every other suite equal. No count went down. HIGH (counts from log). Same caveat as before: the runner has no vulture on its path; this head's tools suite passed without it, so I did not exercise the vulture gate tests here (LOW on whether they are present).
