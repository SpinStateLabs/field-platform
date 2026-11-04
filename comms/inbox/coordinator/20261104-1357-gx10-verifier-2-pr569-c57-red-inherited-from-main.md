# Verifier report: PR 569 (rebuild of #456) full 16-suite run, head c1b60ca — 1 RED in tools, inherited from main

Verifier: gx10-verifier-2. Head tested: c1b60ca4ef9b2fc46fdd7ded6b9d25bd1f39a19c (worktree ~/ff-work/wt-pr569v2). PR head at report time: c1b60ca4ef9b2fc46fdd7ded6b9d25bd1f39a19c. Merge-base with origin/main (as fetched on the GX10) = 97dcfec.
Run: full 16-suite run on the GX10, 08:34-08:53, Postgres port 55435, log ~/ff-work/pr569v2-all.log.

## FAILURE (HIGH, reproduced with --lf on this head)
tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist: new unproxied-env client tools/start_role_session.py::call::urllib.request.urlopen x1. Same as main 97dcfec (20261104-1153), PR 582 and PR 577. Not caused by this PR.

| suite | result | vs main 97dcfec |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 1 failed, 3835 passed, 4 skipped | +35 passed |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 255 | same |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 263 | same |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 448 | same |
| incident-replay | 97 | same |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

No suite count went down vs main. tools +35 is the rebuilt change. The other 15 suites are green.
