# Lane 11 addendum to C-1199 (part 2): per-unit line coverage, measured locally

Method: pytest-cov (line, `--cov=<package src>`) per unit on origin/main cd3b7690, Windows, shared venv, tests run per unit with relative PYTHONPATH. Percent = line coverage over the unit's own `src`, all statements. Measured, HIGH for the numbers; MEDIUM as a picture of CI, because units marked * had local failures or errors from this machine (missing typer in that venv, a path collision, Windows-only tests) that lower their totals.

| unit | line % | statements | lowest-covered files (>=10 stmts) |
|---|---|---|---|
| ops-console | 93.1 | 464 | cli 0 |
| claude-approver | 90.5 | 917 | cli 0, core 91 (client.py under 10 stmts; C-1203 / PR 483 now covers it) |
| force-gateway* | 90.3 | 927 | cli 0 |
| incident-replay* | 89.2 | 372 | cli 0 (C-1204 / PR 485 now covers it; run predates the PR) |
| field-core | 89.1 | 2917 | cli 0, alerts 52 |
| compliance-crosswalk* | 78.5 | 1216 | cli 3, api 70, regwatch 87 |
| federation-broker | 74.2 | 384 | cli 0 |
| kill-switch* | 73.7 | 589 | cli 4 |
| lifecycle-manager* | 69.9 | 896 | cli 4, engine 82 |
| agent-registry | 68.8 | 711 | cli 0, discover 55, redaction 70 |
| attestation-reporter | 65.9 | 701 | cli 0, signing 30, render 73 |
| delegation-authority* | 62.5 | 539 | cli 4 |
| sealed-ledger* | 49.3 | 3521 | cli 0, retention 30, witness 34 |
| conformance-sentinel* | 37.3 | 780 | cli 0, engine 23, governed 33 |

Pattern: every unit's `cli.py` is at 0 to 4 percent (typer commands untested); beyond that the lowest are sealed-ledger retention (30) and witness (34), attestation-reporter signing (30), conformance-sentinel engine (23) and governed (33). The conformance-sentinel and sealed-ledger totals are the least trustworthy (9 and 1 collection errors locally).

NOT RUN or no number: field-agent (pytest rc 4, nothing collected here), spend-governor (killed by my 25-minute limit, no coverage file), tools suite, and the packages other than field-core. No CI coverage figure exists in what I read; I do not know the CI numbers.
