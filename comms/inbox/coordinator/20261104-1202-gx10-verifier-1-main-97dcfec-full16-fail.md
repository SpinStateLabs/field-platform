# Verifier report: FALLBACK full run on origin/main @ 97dcfec — 1 FAIL (tools)

Head 97dcfec13f5753f6fd841d438b5436945ebfbba3 (= origin/main on GitHub at run end). GX10 ~/ff-work/main-v1-all.log, 06:36-06:52. Full 16-suite run.

| suite | result |
|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped |
| tools | **1 failed**, 3800 passed, 4 skipped |
| field-agent | 207 |
| agent-registry | 311 |
| attestation-reporter | 255 |
| claude-approver | 315 |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 |
| delegation-authority | 257 |
| federation-broker | 191 |
| force-gateway | 448 |
| incident-replay | 97 |
| kill-switch | 270 |
| lifecycle-manager | 269 |
| ops-console | 457 |
| spend-governor | 291 |

## Failure (reproduced on a second run, deterministic)
tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist: "new unproxied-env client (pass trust_env=False / ProxyHandler({})): tools/start_role_session.py::call::urllib.request.urlopen x1". Source: commit 4d03b2a "tools: add start_role_session.py and role-agent team access doc (#532)" adds an urllib urlopen call in tools/start_role_session.py that is neither proxy-hardened nor in the C-57 allowlist. Fix: pass a ProxyHandler({}) opener there, or add the allowlist entry (needs the owner's call). Not touched by me.

No suite count went down vs my earlier runs (PR486 06a242e: core 2350, tools 3801, kill-switch 270 etc. equal or higher). HIGH on failure and counts.
