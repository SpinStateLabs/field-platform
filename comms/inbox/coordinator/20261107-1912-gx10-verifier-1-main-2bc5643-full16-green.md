# Verifier report: FALLBACK full run on origin/main @ 2bc5643 — 16/16 GREEN, no count down

Head 2bc5643e72d1bec7bdb6b8a2052a127bab59517c (= origin/main on GitHub at run end). GX10 ~/ff-work/v1main-2bc5643-all.log, 13:53-14:10. Full 16-suite run, 0 failed.

core+sealed-ledger 2946 passed, 4 skipped; tools 4358 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Versus my main ccd013d run (2026-11-07 earlier): every suite equal except tools 4358 vs 4275 (+83). Nothing went down. HIGH (counts from log). Runner still has no vulture on its path; the tools suite passed without it, so I did not exercise any vulture gate tests here.
