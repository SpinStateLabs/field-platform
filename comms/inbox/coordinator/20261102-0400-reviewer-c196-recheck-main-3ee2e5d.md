# C-196 reviewer (Lane 4): runbook commands against main 3ee2e5d (re-check of my 20261031-0800 report)

VERDICT: FAIL (docs) on main 3ee2e5d. Every command and flag the runbooks tell an operator to run still exists and answers `--help`; two earlier findings are unchanged and still open: F-C196-1 (the renew_token.py sha256 pin is stale) and F-C196-2 (the D-18 pre-check lists revoked rows). No code changed; nothing was pushed to any PR.

## OBJECTIONS FIRST
1. F-C196-1 MEDIUM (a STOP gate that always stops): docs/runbooks/token-renewal.md lines 555, 607, 951 and 1186 pin `tools/renew_token.py` to sha256 `1ceccf28...1286c` and line 951 says "STOP if it differs". The file on main 3ee2e5d hashes to `65d860b4...f6b3`. The bytes changed in 80fdd1a (signed ledger append) and 18c4059 (C-30 conditions), both 2026-10-28. Following the runbook as written, the operator stops at the first check, or learns to ignore the pin. No test pins the value: `git grep 1ceccf28` finds only the runbook. HIGH (hash computed on the GX10 from a fresh clone; two commit hashes compared).
2. F-C196-2 LOW (false positive, fails safe): the D-18 pre-check in docs/runbooks/v1.2-deploy-rollback.md (around line 1698) ignores `status`. `operator_keygen` rows carry `status` active/revoked. Probe: a revoked `old-ci` row with kill, revive, revoke, mint is listed and the script exits 1; the `svc-verifier-` and `*` rows are correctly not. The operator would rename or cut scopes on a dead row, or never reach `none`. HIGH (reproduced).
3. Scope limit: I checked flags and subcommands by help text and by dry reading, not outputs on a live estate. Stated outputs in the runbooks (log lines, rc values) were not re-run. MEDIUM.

## ASSUMPTIONS
1. Main is 3ee2e5d (card said b1872ee; main has moved). Fresh clone of the public repo on the GX10. HIGH.
2. "Commands" means invocations of our own tools and service CLIs, not docker, fly or system utilities. HIGH.

## REASONING
1. The audit script (adapted from my earlier one) extracts every logical invocation of our entry scripts from docs/runbooks/*.md: 181 invocations, 48 distinct tool plus subcommand paths, each run with `--help`: all rc 0, FINDINGS 0 (attest, console, crosswalk regwatch, delegation, fedbroker, governor, killswitch, ledger, volume_admin keys generate and the rest). HIGH.
2. Hash: `sha256sum tools/renew_token.py` gives `65d860b4ba0947ad...`; the runbook pins `1ceccf28...`. `git show 18c4059:tools/renew_token.py` hashes to the same `65d860b4`, `80fdd1a` to a different value, so the change is two commits old. HIGH.
3. The tool still prints a `renew_token 1.5 ` log line (version unchanged), so the version cannot tell the operator the file moved. HIGH.
4. The D-18 probe above. HIGH.

## CONCLUSION
FAIL on docs only: the command surface is intact, but the renew_token pin gate cannot pass and the D-18 pre-check over-reports. Neither is a code defect.

PROPOSED CARD (the coordinator numbers it): builder, docs: (a) re-measure renew_token.py, update the four pins, and add a test that fails when the file's hash and the runbook's pin differ (or drop the hash from the gate and name the commit); (b) skip rows whose `status` is `revoked` in the D-18 snippet and say so in the text.

## WHAT I DID NOT DO
Did not run commands against a live estate, the GB10 compose project, fly, or a dry-run of phase_g_check beyond `--help`. Did not re-check the Phase G arming steps beyond the D-18 snippet. Nothing pushed to any PR. I did not repeat C-447 (Lane 7 reported it first; my CI-equivalent run on 33b2c02 was green: core_services 2570, tools 2806, nine services, field-agent 151, topology_lint, defence-shield 229).
