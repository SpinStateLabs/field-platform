# Review PR 409 (C-642b SDK transport read cap, stacked on PR 372) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `fdc2ec853742bc76d989e4722056c0bbbcd08f70`.
Conditions: (1) structural: the base is PR 372's branch (`fix/upstream-error-field-agent-c642`, tip `1b8f9e3f7d45...`, which equals this PR's parent; 372 is OPEN with PASS WITH CONDITIONS from reviewer-6 on that head). 409 cannot land before 372, then retarget. (2) CI green and full GX10 16/16 on the head as landed (rebased on main).

## Objections first
1. Blast radius: `AuthedClient` is the single transport for liveness, usage, federation, bootstrap and the agent's sentinel client; a streaming rewrite changes every SDK call path at once.
2. The rebuilt `httpx.Response` drops framing headers by design and loses `elapsed`/`history`; any caller relying on them regresses silently (I found none in the package; MEDIUM).
3. `ResponseTooLarge` is not an `httpx.HTTPError`; correctness depends on every caller catching `Exception`. I read every caller: liveness (2), usage (4), federation (2), bootstrap (4) catch `Exception`; the sentinel path (services/conformance-sentinel governed.py:96) catches `Exception` and raises `ActionBlocked`, i.e. fails closed (HIGH, read).
4. The PR is far behind main (parent 63e91b21): the full branch conflicts with current main in docs/ENVIRONMENT.md and liveness.py, but those conflicts come from PR 372's commits, not this PR's two.

## Checks (HIGH, run by me)
- Identity: all 5 commits above main (3 of 372, 2 of 409) author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; the 4 with trailers say Sonnet 5.5, none Fable. .github/: 0 files. Own diff vs 372: 2 files (_transport.py +36/-3, new test +142), 2 commits.
- This PR's own 2 commits cherry-pick CLEAN onto current main (scratch worktree, not pushed): so after 372 lands, or even without it, the patch applies.
- Tests: exact head, `test_read_cap_c642b.py` 11 passed (PR says 8 originally; the second commit added 3). On main + these 2 commits, the whole field-agent suite: 240 passed (273 s).
- Code read: counts decoded bytes while streaming, so a missing/false Content-Length and a gzip bomb do not bypass; stops pulling at the chunk that crosses the cap; response closed by the context manager; exception text fixed (cap number only, no body); no-stream injected clients get an after-the-fact length check.

## Mutants (17 on _transport.py vs the 11 tests; counted from the table)
| # | mutant | result |
|---|---|---|
| T1 | cap constant doubled | SURVIVED |
| T2 | cap minus one | KILLED |
| T3 | stream check `>=` | KILLED |
| T4 | stream check cap+1 | KILLED |
| T5 | stream check removed | KILLED |
| T6 | total reset per chunk | KILLED |
| T7 | whole stream read before check | KILLED |
| T8 | fallback check removed | KILLED |
| T9 | fallback `>=` | KILLED |
| T10 | fallback cap+1 | KILLED |
| T11 | Content-Length trusted | KILLED |
| T12 | message echoes body | KILLED |
| T13 | status code lost | KILLED |
| T14 | headers dropped | KILLED |
| T15 | get() bypasses the cap | KILLED |
| T16 | post() bypasses the cap | SURVIVED |
| T17 | patch() bypasses the cap | SURVIVED |
Totals: 17 mutants, 14 killed, 3 survived (14+3 = 17).

## Findings (LOW-MEDIUM, optional new PR)
- T16/T17 (real gap): only GET is pinned. The usage/heartbeat wrapper tests pass even when POST bypasses the cap, because the oversize JSON fails to parse and the wrapper catches that, so they do not prove the cap. A direct `AuthedClient.post` and `.patch` oversize test would kill both.
- T1 (LOW): the tests import `MAX_RESPONSE_BYTES`, so the literal "1 MiB" is unpinned; assert the number 1_048_576 once.

## Not verified
CI/GX10; Linux; other services' suites that reach the SDK; the 372 review's own conditions (not re-checked here).
