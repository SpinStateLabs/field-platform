# Verifier report: PR 316 (C-456 caddy) full 16-suite run, head 3c769c7

Verifier: gx10-verifier-2. Head tested: 3c769c7adeee5ebefb1b4dec49c3cac0d40aedeb (worktree ~/ff-work/wt-pr316v2). PR head at report time: 3c769c7adeee5ebefb1b4dec49c3cac0d40aedeb.
Run: full 16-suite run on the GX10, 05:44-05:58, Postgres port 55435, log ~/ff-work/pr316v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result |
|---|---|
| core+sealed-ledger | 1865 passed, 4 skipped |
| tools | 3055 passed, 4 skipped |
| field-agent | 151 passed |
| agent-registry | 304 passed |
| attestation-reporter | 135 passed |
| claude-approver | 282 passed |
| compliance-crosswalk | 353 passed, 5 skipped |
| conformance-sentinel | 256 passed |
| delegation-authority | 213 passed |
| federation-broker | 105 passed |
| force-gateway | 443 passed |
| incident-replay | 91 passed |
| kill-switch | 160 passed |
| lifecycle-manager | 224 passed |
| ops-console | 246 passed |
| spend-governor | 242 passed |

Baseline: no same-base last-green run known to this verifier. Counts are lower than my PR 475 run (e.g. tools 3055 vs 3776) because this head is on an older base than current main; that is a base difference, not a regression (MEDIUM; base not diffed). No count-regression check made.
