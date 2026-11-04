# Verifier 4: PR372 @ 1b8f9e3 (full 16-suite run, GX10) - 16/16 green, STALE BASE
Head 1b8f9e3f7d453e95848b6a3cae0a271223421410 (equals open PR head at run start). Log: ~/ff-work/pr372-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 1882 passed, 4 skipped; tools 3130 passed, 4 skipped
- field-agent 204 passed, 1 skipped (151 on PR343/355: this PR's SDK tests; one skip is new, reason not inspected: I do not know)
- agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353 (5 skipped)
- conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447
- incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242
Failures: 0. Caution: base is 233 commits behind main b963407, so counts are not comparable with main (field-agent 207 on main). 11-file diff vs main touches field-core, field-agent, conformance-sentinel (cli.py) and tests. Needs rebuild on main and re-run for the merge path.
