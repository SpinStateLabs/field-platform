VERDICT: PASS WITH CONDITIONS on main acaf5f24 (C-1078, services/agent-registry and services/delegation-authority; reviewer Lane 17, local, own mutants RUN; no bypass found; earlier survivors partly closed on main, partly open)

OBJECTIONS FIRST
1. 80 mechanical mutants is a sample (operator swaps on lines, one per site), not a coverage figure; the DOA pool was 101 sites, 83 of them in cli.py, so doa.py and store.py got only 4 mutants each (their whole pool was 9 each).
2. A service suite can be green while field-core behaviour it relies on is unpinned (C-527 showed it); I did not mutate field-core here.
3. Reading is not measuring: findings F-L17-1..3 are PROVEN by probe on main; the rest of the "read" list is code reading only.

ASSUMPTIONS
A1 Tree = origin/main acaf5f24, clean worktree. A2 Suites run from each service dir with relative PYTHONPATH; copies of the service plus field-core src per worker. A3 Probes use real apps via TestClient, temp stores, made-up ids and one fake marker. A4 Operator layer OFF, no shared secret. A5 Public repo: file:line and class only.

WHAT EARLIER REPORTS ALREADY COVERED (not repeated)
agent-registry: C-155 (api.py, store.py, 69 mutants, retired-reactivation gap), C-225 (PR 109 pins), C-528 (api, store, models; 13 mutants; id grammar, manifest staleness and containment, PATCH ref check). delegation-authority: C-194 (api.py, store.py; 87 mutants), C-527 (mint, revoke, introspect; 19 mutants, field-core delegation.py). Not mutated before, my scope: registry discover.py, redaction.py, cli.py, models.py (first mutation of the first three); DOA doa.py, store.py (re-run), cli.py.

REASONING / RESULTS
1. Baselines on main: agent-registry 304 passed (233 s); delegation-authority 213 passed (298 s). HIGH (run).
2. agent-registry, 40 mutants over discover.py (10/10 killed), models.py (4/4), redaction.py (7/9), cli.py (14/17): 35 killed, 5 survived (full suite run on every survivor). delegation-authority, 40 mutants over cli.py (32/32), store.py (4/4), doa.py (4/4): 40 killed, 0 survived. HIGH (run).
3. Survivors (agent-registry), each with the one test that kills it:
   S1 redaction.py:121 mask prefix `len(value)//4` changed to `//3` (reveals a third of a secret instead of a quarter): LOW-MEDIUM. Test: assert the exact masked form of a 40-char value.
   S2 redaction.py:92 anthropic pattern `{32,}` to `{31,}`: LOW. Test: a 31-char and a 32-char body, one hit.
   S3 cli.py:244 default `--port` 8001 to 8000: LOW. Test: the option default is 8001.
   S4 cli.py:228 `typer.echo(f"error: {exc}", err=True)` to stdout: LOW. Test: a failing scan, stderr holds the message and stdout is empty.
   S5 cli.py:126 `if not records` inverted: LOW. Test: `list` on an empty registry prints the empty message and exit 0.
4. F-L17-1 (PROVEN, MEDIUM-LOW): delegation-authority api.py:197-200 returns `DOA roster unavailable — refusing to mint: {exc}` where doa.py:112-125 builds exc from the YAML or pydantic error text. Probe: a roster file with a bad YAML line and one with an extra key both come back in the 503 body WITH the file's own text (marker present), the wrong-type roster echoes the offending input values; the roster PATH is not echoed. A mint caller can read roster contents (grantor names, scopes). Kill: assert a marker placed in a bad roster is absent from the 503 body (log the detail, return a fixed string).
5. F-L17-2 (PROVEN, LOW-MEDIUM): doa.py `max_ttl_days: int = Field(gt=0)` has no upper bound: `max_ttl_days: 1000000000` loads, then every mint is HTTP 500 "Internal Server Error", 0 tokens, 0 ledger events (fails closed but wrong class and no named cause). Also `max_ttl_days: true` is accepted as 1 day, and `max_spend_usd: .inf` loads and then every mint returns 502 "ledger unreachable — refusing to mint: Out of range float values are not JSON compliant" (misleading cause). Kill: a roster test per value expecting a 503 roster error at load.
6. F-L17-3 (PROVEN, LOW, carried C-528 F-2): registry ids "a1.", "a..1", "a_1" and a 5000-char id register (201) on main; "A1" is now refused 422 (C-528 F-1 closed or pinned on main; the uppercase mutant was not re-run). manifest_ref "../outside.yaml" and "/etc/passwd" are refused 422 here, but those files do not exist as valid manifests, so C-528 F-4 (containment with a VALID manifest) is NOT re-tested. Open PRs: PR 371 (id grammar, manifest_ref containment, content-keyed cache, C-635) and PR 349 (idempotent ledger-first revoke, exact introspection id, expiry and covers pinned) address the C-528 and C-527 findings; neither is merged, so those remain open on main.
7. Fail-closed reads (code, not run): doa.py load_roster raises DoaRosterError on unreadable, bad YAML, empty, non-mapping and invalid shape, all refused before any ledger write (api.py:197-201); `find` is exact-string (near-misses, upper-case and padded grantor, all 403 by probe); store.py takes `_lock` on every use of the shared connection (the lock-coverage test pins it). HIGH for the probed parts, MEDIUM for the read-only parts.
8. Public safety: no estate address or credential in this report; probe values are fake. HIGH.

FINDINGS AS PROPOSED BUILDER CARDS (tests, not code)
F-L17-1 MEDIUM-LOW: DOA roster 503 echo (api.py:197-200, doa.py:112-125) - test in 4.
F-L17-2 LOW-MEDIUM: roster bounds (doa.py max_ttl_days, max_spend_usd) - tests in 5.
F-L17-3 LOW: id grammar on main until PR 371 merges; re-check containment with a valid manifest after it.
S1 LOW-MEDIUM, S2-S5 LOW: pins in 3 (tests: services/agent-registry/tests, files not named by me: the existing scan CLI tests did not catch them).

CONDITIONS
C1: cards for F-L17-1 and F-L17-2 (code decision: fixed 503 text; bounds on the roster model). C2: S1 pin. C3: after PR 371 and PR 349 merge, re-run the C-528 and C-527 survivors. Not verified: GX10 16-suite run, field-core mutation, concurrent revoke (PR 349 scope), Python versions other than 3.14.

CONCLUSION
No path mints, revokes or registers around a check in the code read and probed; discover.py and the DOA cli are tightly pinned (42 of 42 killed). The gaps are an operator-file error echoing roster text to a mint caller, unbounded roster numbers that turn a typo into a 500, a secret-mask fraction nobody pins, and the C-528 id-grammar items that wait on PR 371. PASS WITH CONDITIONS.
