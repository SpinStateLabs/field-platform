# fp-verifier-c: PR 925 @cd3fcf4 full 16-suite GX10 run: 16/16 green, 0 failures

Head cd3fcf4da (exact PR 925 head), 0 commits behind origin/main at run time. Full run, Postgres on a private instance.

core+sealed-ledger 2946 passed, 4 skipped; tools 4376 passed, 8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Compared with the latest green reports (PR 919 / PR 924 / PR 917 full16, 2026-11-08): no count went down. tools 4376 vs 4358 (+18, presumably PR scope; not checked against the diff, LOW). conformance-sentinel 370 (PR 919 showed 385 with its own +15 tests; main baseline is 370). Others identical. Confidence HIGH on counts.
