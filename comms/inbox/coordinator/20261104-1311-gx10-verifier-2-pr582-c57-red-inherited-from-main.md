# Verifier report: PR 582 (rebuild of #485) full 16-suite run, head d42acf6 — 1 RED in tools, inherited from main

Verifier: gx10-verifier-2. Head tested: d42acf6ecae275b818b8bad018a6c2a5b3ab4623 (worktree ~/ff-work/wt-pr582v2). PR head at report time: d42acf6ecae275b818b8bad018a6c2a5b3ab4623. Merge-base with origin/main at run time: 97dcfec (= the main tip I tested at 06:36, report 20261104-1153).
Run: full 16-suite run on the GX10, 07:52-08:11, Postgres port 55435, log ~/ff-work/pr582v2-all.log.

## FAILURE (HIGH, reproduced with --lf on this head)
tools/tests/test_http_env_proxy_lint_c57.py:323 test_the_repo_matches_the_allowlist
  new unproxied-env client: tools/start_role_session.py::call::urllib.request.urlopen x1
Same assertion, same file as on main 97dcfec. Not caused by this PR (this head's base is that main). It will block a merge that requires a green tools suite until main is fixed (ProxyHandler({}) opener in tools/start_role_session.py, or allowlist). I do not know whether a fix is already open; PRs 502, 515 and 527 (older bases) do not show it.

| suite | result | vs main 97dcfec |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 1 failed, 3800 passed, 4 skipped | same |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 255 | same |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 263 | same |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 448 | same |
| incident-replay | 108 passed | +11 |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

No suite count went down vs main. incident-replay +11 is the rebuilt change. The other 15 suites are green.
