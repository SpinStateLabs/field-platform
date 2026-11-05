# Review PR #780 (attestation-reporter: a dead upstream is waited on once per build, S8-20) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `32f94bf4af9133d829a763ec8997d5ff5f38c561` (base main; merge-tree against current origin/main: 0 conflicts). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 2 files: attestation_reporter/engine.py (+25), tests/test_upstream_down_short_circuit_s8_20.py (+105). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`. The PR is NOT a draft (isDraft false); other S8 PRs are drafts: process note only.
- Mechanism: a ContextVar set in `build()` and reset in a `finally`; `_fetch_answer` adds `id(client)` to it on any exception from `client.get` and, once there, returns `(None, query, False, None)` with the same query text without calling the client. HTTP statuses (404/500/503) and a None client are untouched; outside a build the var is None. `build` keeps its signature and calls `_build`.
- No thread or executor use in attestation_reporter (grep), so ContextVar scoping holds per build; a thread without the context would simply not short-circuit (safe direction).
- tests/test_upstream_down_short_circuit_s8_20.py: 9 passed on the head. Full attestation-reporter suite (PR: 264) not run by me.

## Mutants (engine.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | short-circuit check disabled | RED |
| M2 | an HTTP status trips the memory | RED |
| M3 | memory not reset after build | RED |
| M4 | failures not recorded | RED |
| M5 | memory keyed by client type name | RED |
| M6 | build sets None instead of a fresh set | RED |
| M7 | every failure recorded under one constant key | RED |
| M8 | short-circuited fetch prints a different query | RED |
Totals counted from the table: 8 mutants, 8 RED, 0 SURVIVED.

## Judgement points (not blocking; the author flags the first as Don's decision)
1. Accuracy trade-off (MEDIUM): one transport error on ANY ledger call (for example a read timeout on the heavy `/events` query) now makes every later ledger figure unavailable for that pack, including the chain `/verify` result, which previously might have answered. The pack labels each as unavailable with its printed query, so no false assurance, but the integrity figure can degrade on a transient error. A mitigation for a new PR: exempt `/verify` and `/health`, or retry once before tripping.
2. `except Exception` is pre-existing: a programming error inside a client now also trips the memory for the build (LOW).
3. Not exercised: a real socket or timeout (the author says so); no overall deadline on the sync /pack handler.
