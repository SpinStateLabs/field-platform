# Verifier report: PR383 @ defb7ea (full 16-suite run)

Head defb7eaf5c705a820471b1c8904d1f3c4d44d167 (equals open PR head at start, in worktree, and on GitHub at run end). Title: All 14 services, one startup WARNING when a service starts open, naming the setting never a value (C-804). OLD BASE (core ~1.9k, tools ~3.2k), so counts are not comparable to current main b963407. GX10 ~/ff-work/pr383v1-all.log, 16:20-16:35.

core+sealed-ledger 1891 passed, 4 skipped; tools 3198 passed, 4 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353 passed, 5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

0 failed, 0 errors. HIGH. Against my PR374 run (same old base): tools 3198 vs 3130 (+68, this PR's tests); core 1891 vs 1908 (-17) is PR374's own core additions not being in this branch, not a loss from this PR (MEDIUM: I did not diff the two bases). Needs a rebuild on current main before merge.
