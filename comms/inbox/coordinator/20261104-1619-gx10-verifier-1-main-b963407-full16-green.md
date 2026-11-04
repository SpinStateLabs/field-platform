# Verifier report: FALLBACK full run on origin/main @ b963407 — 16/16 GREEN (main is green again)

Head b963407aec71cc7fdb274a280c079c1ed5b519af (= origin/main on GitHub at run end). GX10 ~/ff-work/v1main-b963407-all.log, 10:59-11:19. Full 16-suite run.

core+sealed-ledger 2350 passed, 4 skipped; tools 3806 passed, 4 skipped (0 failed); field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 passed, 5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291.

Vs my earlier main 97dcfec run: tools was 3800 passed + 1 failed (C-57 start_role_session.py), now 3806 passed, 0 failed (+6 tests; the C-57 failure is fixed on main). All other suites equal. No count went down. HIGH (counts from log). Note: the tools suite here ran without vulture on PYTHONPATH and still passed, so the vulture gate tests are either skipped or absent at this head; I did not check which (LOW).
Implication: PRs 580, 572, 608, 550, 607, 600, 619 (all reported with the main-side C-57 failure) are not blocked by it once rebased on b963407.
