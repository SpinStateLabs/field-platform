# fp-verifier-c: PR 932 @effb1ec full 16-suite GX10 run: 16/16 green, 0 failures

Head effb1ece1 (exact PR 932 head), 0 commits behind origin/main (fetched after the run). Full run, private Postgres instance. Diff vs main: 3 files, +165/-6.

core+sealed-ledger 2981 passed, 4 skipped; tools 4358 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Compared with the green main-baseline counts (PR 919/917/924 full16 reports, 2026-11-08): no count went down. core+sealed-ledger 2981 vs 2946 (+35, in the PR's scope area presumably; diff not inspected, LOW). Others identical. Confidence HIGH on counts.
