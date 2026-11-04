# Verifier report: PR 577 (rebuild of #467) full 16-suite run, head 9cf70b9 — 1 RED in tools, inherited from main

Verifier: gx10-verifier-2. Head tested: 9cf70b92e61f5a0f75ec4916650644b9dce23f4f (worktree ~/ff-work/wt-pr577v2). PR head at report time: 9cf70b92e61f5a0f75ec4916650644b9dce23f4f. Merge-base with origin/main = 97dcfec, which is still origin/main's tip at 08:30.
Run: full 16-suite run on the GX10, 08:12-08:30, Postgres port 55435, log ~/ff-work/pr577v2-all.log.

## FAILURE (HIGH, reproduced with --lf on this head)
tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist: new unproxied-env client tools/start_role_session.py::call::urllib.request.urlopen x1. Identical to the failure on main 97dcfec (report 20261104-1153) and on PR 582 (20261104-1311). Not caused by this PR. Main still carries it as of 08:30; fixing main unblocks every rebuilt head.

| suite | result | vs main 97dcfec |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 1 failed, 3800 passed, 4 skipped | same |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 255 | same |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 280 passed | +17 |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 448 | same |
| incident-replay | 97 | same |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

No suite count went down vs main. conformance-sentinel +17 is the rebuilt change. The other 15 suites are green.
