# fp-verifier-c: batch m4a @45bd655 full 16-suite GX10 run: 16/16 green, 0 failures

Head 45bd65538 (batch/2026-11-08-m4a, exact head), 0 commits behind origin/main (main is 62a3f8578, fetched after the run). Full run, private Postgres instance.

core+sealed-ledger 3137 passed, 4 skipped; tools 4416 passed, 8 skipped; field-agent 393; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 passed, 5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 152; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Compared with the green main-baseline counts of 2026-11-08 (PR 919/917/924 full16 reports; main then 2bc5643, not re-run on 62a3f85): no count went down. Increases: core+sealed-ledger 3137 vs 2946 (+191), tools 4416 vs 4358 (+58), field-agent 393 vs 295 (+98), incident-replay 152 vs 132 (+20); consistent with a 12-PR batch under packages/ tools/ docs/ (diff not inspected, LOW). Others identical. Confidence HIGH on counts.
