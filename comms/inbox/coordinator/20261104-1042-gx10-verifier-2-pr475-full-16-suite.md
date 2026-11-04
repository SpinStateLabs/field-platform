# Verifier report: PR 475 (C-1190) full 16-suite run, head 19d14a4

Verifier: gx10-verifier-2. Head tested: 19d14a49054393b5763a234c69f0ec71fa4147a0 (worktree ~/ff-work/wt-pr475v2). PR head at report time: 19d14a49054393b5763a234c69f0ec71fa4147a0.
Run: full 16-suite run on the GX10, 05:24-05:40, Postgres port 55435, log ~/ff-work/pr475v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result |
|---|---|
| core+sealed-ledger | 2346 passed, 4 skipped |
| tools | 3776 passed, 4 skipped |
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
| kill-switch | 242 passed |
| lifecycle-manager | 269 passed |
| ops-console | 457 passed |
| spend-governor | 291 passed |

Baseline: none compared (no last-green counts available to this verifier), so no count-regression check was made. Other batches ran concurrently on the GX10 (load ~2.3 at start); no failures seen. Queue note said "Reviewer PASS, no run".
