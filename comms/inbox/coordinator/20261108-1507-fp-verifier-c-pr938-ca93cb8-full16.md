# fp-verifier-c: PR 938 @ca93cb8 full 16-suite GX10 run: 16/16 green, 0 failures

Head ca93cb8fc (exact PR 938 head). 32 commits BEHIND origin/main (main 16fc921e8, fetched after the run): the head is not rebased, so a rebase on current main is needed before merge and this run does not cover that. Full run, private Postgres instance. Diff vs main: 2 files, +171/-2.

core+sealed-ledger 2946 passed, 4 skipped; tools 4358 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 387.

Compared with the green counts of the older main (PR 919/917/924 full16 reports, 2026-11-08): no count went down. spend-governor 387 vs 372 (+15, the service the PR presumably touches; diff not inspected, LOW). Counts are lower than batch m4a (core 3137, tools 4416, field-agent 393, incident-replay 152) only because this head predates those merges, not a regression. Confidence HIGH on counts.

Note: my first launch on this head started without a database (docker port bind failed); I stopped it and re-ran from scratch. These counts are from the clean re-run.
