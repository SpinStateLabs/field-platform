# GX10 verifier ssl-ff-verifier-5: V-RUN-PR771-0cf53a3

Verdict: **15/16 suites PASS, 1 FAIL (tools)** on head **0cf53a31dffff89e5fd6acd72a9112537e9897e9** (PR 771, draft; base is the stacked branch fix/spend-governor-text-bounds-s2-2, not main; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped |
| tools | **1 failed**, 3800 passed, 4 skipped |
| field-agent | 207 passed |
| agent-registry | 311 passed |
| attestation-reporter | 255 passed |
| claude-approver | 315 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 448 passed |
| incident-replay | 97 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 457 passed |
| spend-governor | 316 passed |

Failure: tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist: 'new unproxied-env client: tools/start_role_session.py::call::urllib.request.urlopen x1'. Re-ran that file alone on the head: same single failure (HIGH).
Cause (HIGH): not this PR. The PR diff (spend-governor api.py + 2 spend-governor test files; stack merge-base with main 97dcfec1) touches nothing under tools/. main commit b963407a ('start_role_session.py sends its API key through a no-proxy, no-redirect opener (fixes the C-57 lint red on main since #532)') fixes that exact red and is not in this head's base. Expected to go green once the stack is rebased on current main; unverified until a rebased head is run (MEDIUM).
spend-governor 316 passed and ops-console 457 passed reflect the stacked S2-2 + S8-10 tests on the older base; no spend-governor failure.
Landing needs a 16/16 on the head rebased on current main. Log: ~/ff-work/ver5p771-all.log on the GX10.
