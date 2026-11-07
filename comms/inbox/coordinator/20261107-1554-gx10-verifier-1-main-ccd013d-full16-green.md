# Verifier report: FALLBACK full run on origin/main @ ccd013d — 16/16 GREEN, no count down

Head ccd013d4f072aa8f9d420bff029359ffd8d617d1 (= origin/main on GitHub at run end). GX10 ~/ff-work/v1main-ccd013d-all.log, 10:36-10:53. Full 16-suite run, 0 failed.

core+sealed-ledger 2946 passed, 4 skipped; tools 4275 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Same-base comparison with my PR837 run (c972adf, same suites): every suite equal except tools 4328 vs 4275 (+53, that PR's tests), so PR837's 2-3 warnings and counts are consistent with main. Versus my last main run (3cede87, 2026-11-05) every suite is higher or equal; nothing lower. HIGH (counts from log). The runner still has no vulture on its path; I did not exercise the vulture gate tests here.
