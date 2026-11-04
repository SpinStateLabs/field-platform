# Reviewer report: PR 399 @ 653a4d457941f91c34972bb07c295cf26ed34e43 (C-757, spend-governor retired-agent meter)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base acaf5f24 (old); 8 commits; files: spend_governor/api.py (+127), cli.py (+7), README (+8), docs/ENVIRONMENT.md (1 row), tests/test_retired_agent_warn_c757.py (+404). Author and committer of all 8 = Don Hagell 13129187+dhagell@users.noreply.github.com; trailers say Sonnet 5.5 (HIGH). `git merge-tree --write-tree origin/main pr399` is clean (HIGH). No agent id, estate address, flag or credential in the log line or tests.

## Objections first
1. The retired-agent path adds a thread pool, a condition lock, three dicts and background tasks to a meter whose contract is "never refuse": every added moving part is a way for a spend call to stall or raise. The design answers this (lookup off the request path, bounded, fail open), so the review below tests exactly those properties.
2. `_status_cache` and `_log_state` evict the oldest key at 1024 agents (FIFO), so under churn a retired agent can log more often than once per interval; the README says "at most once per agent per 5 minutes" without that qualifier (MEDIUM-LOW, not pinned).
3. The executor is created per `create_app` and never shut down (idle workers exit with the process); a test suite that builds many apps leaves idle threads. LOW.
4. The README numbers (5 minutes, a minute, 10 seconds) are not pinned by value: see A4, A8.

## Verified
- Baseline on the exact head: tests/test_retired_agent_warn_c757.py 28 passed (relative PYTHONPATH `../../packages/field-core/src:src`; uvicorn had to be installed in my scratch venv or 2 `serve` tests error on import, environment, not counted); whole services/spend-governor/tests 270 passed.
- Code read: the lookup never runs on a request thread; `_note_if_retired` only reads the cache or queues work; failures (`except Exception`) give False for the 10 s failure TTL; `_lookup` clears `_pending` in `finally` (F-Q34-1); the log line is fixed text and integers.

## Mutants (scratch worktree on the head; baseline 28 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| A1 | counter adds 0 | 5 failed | yes |
| A2 | log line names the agent | 1 failed | yes |
| A3 | log interval 5 min -> 0 | 1 failed | yes |
| A4 | log interval 5 min -> 10 h | 28 passed | NO |
| A5 | "calls held back" off by one | 1 failed | yes |
| A6 | retired test inverted | 15 failed | yes |
| A7 | failure cached as long as an answer | 1 failed | yes |
| A8 | status TTL 60 s -> 600 s | 28 passed | NO |
| A9 | failure TTL 10 s -> 0 | 1 failed | yes |
| A10 | pending bound `>=` -> `>` | 1 failed | yes |
| A11 | joined calls not counted | 1 failed | yes |
| A12 | `_pending` not cleared in finally | 22 failed (113 s: the bound fills) | yes |
| A13 | only one exception class swallowed | 1 failed | yes |
| A14 | status cache unbounded | 1 failed | yes |
| A15 | lookup workers 2 -> 1 | 1 failed | yes |
| A16 | registry-None guard removed | 1 failed | yes |
| A17 | PUT /caps does not note retired | 9 failed | yes |
| A18 | POST /spend does not note retired | 6 failed | yes |
| A19 | cache hit never trusted | 2 failed | yes |
| A20 | serve builds a registry client always | 1 failed | yes |
| A21 | serve never builds a registry client | 1 failed | yes |
| A22 | /health field not wired | 5 failed | yes |
| A23 | remembered answer expires at once | 2 failed | yes |
| A24 | held-back calls not accumulated | 1 failed | yes |
| A25 | lookup records only when more than 5 wait | 8 failed | yes |
Totals counted from the table: 25 mutants, 23 killed, 2 survived (A4, A8). Both survivors run against the whole spend-governor suite: 270 passed each, baseline 270 passed, so both survive everything. Cause: the tests advance the clock by the module's own constants (`gov_api.RETIRED_LOG_INTERVAL`, `REGISTRY_STATUS_TTL`), so the literal values the README states are not pinned, only their relations.

## Findings
- F-C757-1 LOW: A4 and A8, the stated 5-minute interval and 60-second TTL are unpinned by value (a test with literal timedeltas would pin the README).
- F-C757-2 LOW: objection 2, FIFO eviction means "at most once per agent per interval" holds only below 1024 tracked agents; say so in the README or pin the behaviour.
- F-C757-3 LOW: objection 3, executor never shut down.

## Verdict: PASS on 653a4d457941f91c34972bb07c295cf26ed34e43
Head frozen; LOWs go in a NEW PR. Merge is clean against current main (base acaf5f24 is old, so the coordinator's rebase and GX10 run on the exact head are required). Not run by me: CI, GX10, a rebased head.
