# Verifier report: PR 627 (docs: reconcile todo ticks) full 16-suite run, head 4c94826 — 1 RED in tools, main-caused (base 97dcfec)

Verifier: gx10-verifier-2. Head tested: 4c948260251c25718beba2042f1c310dcb5d9550 (worktree ~/ff-work/wt-pr627v2). PR head at report time: 4c948260251c25718beba2042f1c310dcb5d9550. Merge-base = 97dcfec, the old main that still has the C-57 failure; origin/main is now b963407 (clean).
Run: full 16-suite run on the GX10, 17:50-18:06, Postgres port 55435, log ~/ff-work/pr627v2-all.log.

## FAILURE (HIGH, reproduced with --lf on this head)
tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist: new unproxied-env client tools/start_role_session.py::call::urllib.request.urlopen x1. Main-caused: identical to main 97dcfec (20261104-1153), fixed on main b963407 (20261104-1630). A rebase onto b963407 should clear it; not re-tested.

Counts equal main 97dcfec in all 16 suites (core+sealed-ledger 2350/4 skipped; tools 1 failed, 3800 passed, 4 skipped; field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291). No count went down. The other 15 suites are green. The change is docs only.
