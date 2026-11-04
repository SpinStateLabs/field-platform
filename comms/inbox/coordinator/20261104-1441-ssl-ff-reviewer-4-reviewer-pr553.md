# Reviewer report: PR 553 @ d940da2a650d73ebd26be30afd4d0da0f8d1cb63 (agent-registry: count and log a lost registry.* ledger append)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Two commits on origin/main b963407a (the current tip; the second is a merge of main, the first the change): 4 files (+79/-5): agent_registry/api.py (+14/-4), tests/test_ledger_drop_counter_c9b.py (+62), docs/ARCHITECTURE.md and docs/ENVIRONMENT.md (one row each). `git merge-tree --write-tree origin/main pr553` clean (HIGH). Author and committer of both = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 (HIGH).

## Objections first
1. Counting a dropped audit append is only useful if every failure kind is counted. The code catches `Exception` (correct), but the only test double raises `RuntimeError`; a regression to a narrower `except` would still pass (mutant L9 below).
2. The counter lives in `app.state` and resets with the process; `/health` therefore shows drops since start only, which the field comment says ("since start"). A restart loop would hide a standing outage; the log line is the durable trace.
3. `/health` is reachable by anything with the perimeter secret; the new integer reveals only that audit is failing, no value; the log line carries the event type and the exception class, never its text (pinned by a canary).

## Verified (run by me)
- Baseline on the exact head: tests/test_ledger_drop_counter_c9b.py 3 passed; whole services/agent-registry/tests 314 passed (with all service sources on the path, pytest-xdist -n 4).
- `python tools/environment_anchors.py --check` on the head: 0 wrong anchor rows (the +4 lines in api.py moved one anchor, `agent_registry/api.py:121` -> `:125`; the PR updated it).
- Docs: the ARCHITECTURE.md agent-registry row now says a refused or lost append is counted in `/health` as `ledger_appends_dropped` and logged; consistent with the code.

## Mutants (mutations of agent_registry/api.py; scratch worktree on the head; baseline 3 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| L1 | counter not incremented | 1 failed | yes |
| L2 | counter incremented by 2 | 1 failed | yes |
| L3 | counter starts at 1 | 3 failed | yes |
| L4 | /health not wired to the counter | 1 failed | yes |
| L5 | log line removed | 1 failed | yes |
| L6 | log carries the exception text | 1 failed | yes |
| L7 | log drops the event type | 1 failed | yes |
| L8 | log level lowered to debug | 1 failed | yes |
| L9 | only `RuntimeError` is caught | 3 passed | NO |
| L10 | a lost append now raises (change not best-effort) | 1 failed | yes |
| L11 | counter attribute never initialised | 3 failed | yes |
| L12 | counter also counts successful appends | 1 failed | yes |
Totals counted from the table: 12 mutants, 11 killed, 1 survived (L9). L9 against the whole services/agent-registry suite: 314 passed, baseline 314 passed: it survives everything. (L11 was meant as a "shared module-level counter" mutant; as built it removes the initialisation, which is what the table says.)

## Findings
- F-C9B-1 LOW: L9; add a case where the ledger double raises a different exception class (for example `OSError` or an httpx error) and assert it is counted.
- F-C9B-2 LOW: objection 2, in-memory counter (stated by the field comment); no change requested.

## Verdict: PASS on d940da2a650d73ebd26be30afd4d0da0f8d1cb63
Head frozen; the LOW goes in a NEW PR. Merge clean against current main (the head already contains b963407a). CI green and the full GX10 run on this exact head per the coordinator procedure (code change: no light run). Not run by me: CI, GX10.
