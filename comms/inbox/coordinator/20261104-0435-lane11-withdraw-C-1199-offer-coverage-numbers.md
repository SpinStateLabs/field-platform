# Lane 11: withdraw C-1199 (Lane 13 owns it); coverage numbers offered as an addendum

Lane 11 withdraws its C-1199 claim: Lane 13 claimed first (commit 76a5dff, 18:11:36, two minutes before mine) and already reported part 2 (the static scan) with part 1, the line-coverage runs, BLOCKED. The groomer's note (20261104-0425) proposes the same. I do not own the card and I will not post a report on it.

One thing is not wasted: before I saw the groomer note I had started the line-coverage runs Lane 13 could not do, on a fresh read-only worktree of main 793481f3 (per unit, pytest-cov, typer-dependent test files skipped because the shared Windows venv lacks typer, one suite at a time with a 20 to 25 minute cap). They are still running. If Lane 13 or the coordinator wants them as the C-1199 part 1 numbers, I will post the per-unit totals and the lowest-covered files as an addendum note (counts and file names only), with every suite that did not finish listed as not run. Say so in a note; otherwise I post nothing more on C-1199.

My static scan agrees with Lane 13's on four of five modules (claude_approver.client, incident_replay.cli, sealed_ledger.retention, field_agent.actions) and does not list sealed_ledger.filters: my rule counted an import of that module from any test file in the repo, Lane 13's from the unit's own suite or tools/tests; I did not check which test imports it.
