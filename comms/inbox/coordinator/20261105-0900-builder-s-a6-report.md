# Report: S-A6 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no note for this card; branch origin/lane16/c1129-ssl-agents-origin edits the same file (origin concern): textual conflict possible, NOT checked.
PR 513 (draft): https://github.com/SpinStateLabs/field-platform/pull/513, branch fix/provision-ssl-tokens-ttl-sa6, head 0e3ee05c38b47811c013f5426770d30bec1dbce0 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A: tools).
Bug (R, 23 red tests): FIELD_TOKEN_TTL_DAYS=abc raised at import; a non-dict tokens file failed AFTER tokens were minted (never saved); corrupt JSON, non-UTF-8, directory = tracebacks. Fix: TTL and tokens-file checks right after the PROXY check, before any request; one named stderr sentence, exit 2, file never rewritten; blank TTL = 30 (repo convention); messages carry file name and exception type only.
Process note: the boundary-echo lint (test_boundary_echo_lint_c505) caught my first draft (print sites 1 -> 2); fixed by one print site and returning problems instead of raising, allowlist untouched. This is the second lint (after environment_anchors) that only a tools test run catches: I now run tools tests touching the file plus anchors --check before every push.
31 tests; neighbouring tools suites 298 passed 1 skipped, ssl_renewal + job_grantors 15 passed 1 skipped; anchors --check 0 wrong; two mutants killed (8 red, 7 red).
Not run: full tools suite, other suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505, 507, 510, 511, 512, 513; none merged by me.
Scout round 2 left: S-B4 only (needs your/Don's decision: /halt returns 200 with errors vs 502; tests would pin whichever is chosen).
