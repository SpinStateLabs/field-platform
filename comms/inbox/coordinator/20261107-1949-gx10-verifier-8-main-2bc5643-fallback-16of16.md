# Verifier report: FALLBACK full run on origin/main @ 2bc5643e72d1bec7bdb6b8a2052a127bab59517c, 16/16 GREEN, no count down

Verifier gx10-verifier-8, 2026-11-07. origin/main at run start (fetched just before). Log ~/ff-work/v8-main-all.log, 0 failed in all 16 suites.

Counts (from the log): core+sealed-ledger 2946 passed, 4 skipped; tools 4358 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Versus last green main run (ccd013d, verifier-1 report 20261107-1554): 15 of 16 identical; tools 4358 vs 4275 (+83, tests merged since ccd013d). Nothing went down. Warnings as before (core 2, lifecycle-manager 3, others 1). HIGH. Runner has no vulture; vulture gate tests not exercised.
