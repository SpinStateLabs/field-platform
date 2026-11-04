# Verifier 4: PR355 @ 640e1bd (full 16-suite run, GX10) - 16/16 green, STALE BASE
Head 640e1bd15adef48d582a1974d8cf5fdfc7a31294 (equals open PR head at run start). Log: ~/ff-work/pr355-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 1875 passed, 4 skipped (the PR's suite; 1865 on PR343 which shares this base, +10)
- tools 3129 passed, 4 skipped; field-agent 151; agent-registry 304; attestation-reporter 135; claude-approver 282
- compliance-crosswalk 353 (5 skipped); conformance-sentinel 256; delegation-authority 213; federation-broker 105
- force-gateway 443; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242
Failures: 0. Caution: base is 236 commits behind main b963407 (same old base as PR343), so counts are not comparable with main; PR343's tools 3308 vs 3129 here is PR343's +1 big test file (MEDIUM, inferred from its diff). Diff vs main = 2 field-core test files, +125 lines. Green here does not prove green on current main; needs rebuild and re-run for the merge path.
