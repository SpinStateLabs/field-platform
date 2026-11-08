# fp-verifier-c: PR 928 @bdf220e full 16-suite GX10 run: 16/16 green, 0 failures

Head bdf220ec3 (exact PR 928 head), 0 commits behind origin/main (fetched after the run). Full run, private Postgres instance. Diff vs main: 2 files, +119/-3.

core+sealed-ledger 2946 passed, 4 skipped; tools 4358 passed, 8 skipped; field-agent 321; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Compared with the green main-baseline counts in PR 919/917/924 full16 reports (2026-11-08): no count went down. field-agent 321 vs 295 (+26; consistent with a 2-file change touching field-agent, diff not inspected, LOW). Others identical. Confidence HIGH on counts.
