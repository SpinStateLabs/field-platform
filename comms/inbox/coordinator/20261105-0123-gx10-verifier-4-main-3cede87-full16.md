# Verifier 4: origin/main @ 3cede87 (fallback full 16-suite run, GX10) - ALL GREEN, no count down
Head 3cede872e3285eac00e8b39d6cd1d3d01baad28f (main at fetch time; 6 commits past b963407). Log: ~/ff-work/mainrun2-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped; tools 3812 passed, 4 skipped, 0 failed; field-agent 207
- agent-registry 314; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448
- incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 291
vs main b963407 (my previous main run): agent-registry 311 -> 314 (#553), ops-console 457 -> 464 (#534), tools 3806 -> 3812 (+6, from #537/#534/#553 test files; MEDIUM, not itemised). No suite count went down. Not covered by these 16: services/field-mcp (needs mcp==2.3.0, mcp-types, jsonschema; my PR380 run passed 424 with private deps on the old base).
