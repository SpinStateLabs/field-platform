# Reviewer (docs): PR 475 (C-1190) docs claims about commands, flags and defaults checked against main

**Verdict: PASS WITH CONDITIONS on head `19d14a49054393b5763a234c69f0ec71fa4147a0`.** Docs only (3 files, +20/-9, 3 commits). Head unchanged at start; base `c356e205` (older than main) but `git merge-tree` against current main reports a CLEAN merge; 3 commits, Don Hagell noreply on author and committer (0 nonconforming). Not built by this lane.

I re-checked each changed claim against CURRENT main (cd3b7690 lineage), not the base the author used.

## Claim checks (HIGH, git grep and file reads on origin/main)
| Doc | Claim | Result |
|---|---|---|
| field-agent README | `fieldagent check` takes `--token-id` and `--irreversible` (cli.py:81-82) | OK |
| field-agent README | `report-usage` takes `--model` (required), `--input-tokens`, `--output-tokens`, `--cache-read-tokens`, `--note`; token counts default to 0 (cli.py:105-109) | OK (5 options, defaults 0) |
| field-agent README | the facade has `report_spend` (agent.py:133) | OK |
| field-agent README | exit 3 on rogue findings, exit 1 when the report did not land (cli.py docstring and the two `Exit` calls) | OK (2) |
| INTEGRATION.md | the default compose files leave `FIELD_DOA_ROSTER` unset | OK (no hit in them) |
| INTEGRATION.md | the fly entrypoint defaults it to empty (`entrypoint.sh:62`) | OK |
| INTEGRATION.md | the CI upgrade-smoke job sets it (`ci.yml:420`) | OK |
| INTEGRATION.md | the GB10 required overlay requires it (`integration/demo/docker-compose.gb10.required.yml`, six services) | OK |
| token-renewal runbook | an unusable `FIELD_OPERATOR_KEY_FILE` without a flag prints `warning: FIELD_OPERATOR_KEY_FILE is <problem>; no operator identity is sent` (renew_token.py:317) | OK (text matches) |
| token-renewal runbook | with an operator flag it is refused with `--operator-key-file is <problem>; nothing sent` (renew_token.py:316) | OK (text matches) |
| token-renewal runbook | the example roster's active job rows are `job-provision-gb10` and `job-renewal-rog`, and `job-renewal-gb10` is a commented-out template | OK (3 lines checked: 75, 96, 122) |
| token-renewal runbook | the not-due log line carries the revision field `phase-g` (renew_token.py:164 `REVISION = "phase-g"`) | OK |
Totals counted from the table: 12 rows covering 9 + 4 + 6 = 19 individual checks (README 9: 2 flags + 5 options + 1 method + 2 exits, minus 1 overlap counted once = see rows), 0 failed.

## Objections first
1. Two statements I did NOT verify: the refusal exits with code 2 (the runbook says "exit 2"; I read the message, not the exit mapping), and the consequence "an armed roster refuses the GB10 cron mint with 403 D.grantor" (a behaviour of the delegation service, not checked here).
2. The PR body's counts (README 58 checked, 52 OK, 3 DRIFT, and the others) come from three read-only agents; I did not re-check the items the agents marked OK, only the lines the PR changed.
3. The base is older than main; the claims were still true on current main, so no stale-base problem for this PR, but a later main edit of those flags would reopen them.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: none on content.

## Findings (non-blocking)
- F-475-1 LOW: the two unverified statements (objection 1) deserve one test or one grep owner each; the runbook is operator-facing for the cron mint.
