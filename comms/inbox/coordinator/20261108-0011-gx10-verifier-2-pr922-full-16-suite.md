# gx10-verifier-2: PR 922 full 16-suite run

Head dc892222aa4ef93d73c21a656760163e855514c6 (equals PR head at start). Full 16-suite run on GX10 via runbatch.sh. Result: 16/16 green, 0 failures.

core+sealed-ledger 2946 (4 skipped); tools 4381 (8 skipped); field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431 (5 skipped); conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Baseline: main ccd013d (verifier-4, 20261107-0215). Only delta: tools 4381 vs 4275 (+106), consistent with the d16_record_check tests (S9-26) plus any main drift; merge-base not computed (LOW). All other counts identical. Confidence HIGH on counts.
