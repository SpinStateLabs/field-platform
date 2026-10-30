VERDICT: PASS WITH CONDITIONS on main 5808a5cd6186566a2233105beaf3913b1ae11e51

C-527 delegation-authority standing re-audit (Lane 7). Scope: services/delegation-authority api.py (mint, revoke, /introspect, /oauth/introspect), field-core delegation.py status/covers; the introspect and scope contract conformance-sentinel relies on (engine.py:146-147, :544-561).

OBJECTIONS FIRST
1. Token expiry, revocation precedence and scope matching live in field-core, not in this service; a service suite can be green while those are unpinned.
2. Introspection answers "active" for a token of a killed agent; whether that is safe depends on a second check in another service.
3. Two introspection endpoints with different input handling invite a bypass by choosing the lenient one.

ASSUMPTIONS
A1 Tree = main 5808a5c, clean. A2 Real apps via TestClient, temp stores, made-up ids, roster unset unless stated. A3 field-core suite run for the survivors (1119 passed).

REASONING / RESULTS
1. Suites: delegation-authority 213 passed; field-core 1119 passed, 1 skipped [HIGH]. 19 hand mutants on this service plus field-core delegation.py: 15 killed in the service suite, 1 more (revoke before expiry order) killed by field-core. 3 survive both suites (below).
2. Killed: unknown token active (both endpoints), revoked token active on oauth, oauth missing token 400 dropped, past expiry mint allowed, naive expires_at left naive, ledger fail-open on mint, roster unreadable open, manifest-scope check off, grantor TTL cap off, manifest-expiry cap off, inactive grantor allowed, revoke made non-idempotent, spend ceiling dropped, oauth token strip removed.
3. F-C527-1 SURVIVOR, ledger fail-open on revoke [HIGH, mutant]: replacing the 502 at api.py:387 by `pass` keeps 213 green. A revoke during a ledger outage is meant to be refused ("unauditable authority must not exist" holds for mint, tested). Revoke is safety-reducing authority, so act-first could be argued (kill-switch does that, C-525); the code and the README disagree on intent or the test is missing. Severity LOW-MEDIUM. Decision for Don: refuse-on-outage (as coded) or act-first with a log line; either way pin it with a test.
4. F-C527-2 SURVIVOR, expiry boundary [HIGH, mutant]: `now >= expires_at` (field-core delegation.py:55) changed to `>` survives both suites. A token is meant to be dead at the instant of expiry. Severity LOW. Fix: one test with now == expires_at.
5. F-C527-3 SURVIVOR, scope prefix matching [HIGH, mutant]: `covers` (delegation.py:72-74, "exact match") changed to startswith survives both suites. Only incident-replay calls covers; the sentinel does exact `in` on the introspected list (engine.py:549), so no live path today. Severity LOW; pin it.
6. F-C527-4 concurrent revoke [HIGH, probe]: two simultaneous revokes of one token (ledger append held at a barrier) returned two distinct revocation_ids and wrote two delegation.revoke ledger events; the stored row carries one of them. The sequential case is idempotent (same id). Cause: read-modify-write at api.py:337-389 with no lock or compare-and-set. Severity LOW (the token is revoked either way; the audit has a duplicate and one id is orphaned).
7. F-C527-5 input handling [HIGH, probe]: /introspect is exact (" id", "id ", upper-case, truncated all answer revoked, fail closed); /oauth/introspect strips whitespace, so "token=%20<id>%20" answers active, other spellings inactive; duplicate token fields take the first (token=zzz&token=<id> inactive); a JSON body is 400; invalid UTF-8 inactive. Both fail safe; the leniency is only whitespace. Severity LOW.
8. F-C527-6 roster unset [HIGH, probe]: with FIELD_DOA_ROSTER unset a mint accepts scope [""], [" "], duplicates, a 100000-char scope entry, expires_at 9999-12-31 and ttl 10**11 s (year 5195). Roster armed bounds scope by manifest, grantor TTL and manifest expiry (mutants killed). TTL above ~3*10**11 s and 10**30 are 422 (OverflowError handled). Severity LOW-MEDIUM; this is the documented unarmed mode, but an empty-string scope is a footgun. Decision: min_length on scope entries.
9. Killed agent [HIGH, probe]: after PATCH status killed, /introspect of an existing token stays active:true and a new mint is 409. The sentinel checks registry status separately (engine.py:485-497), so the combination holds; the introspect answer alone does not mean the agent may act [MEDIUM on the sentinel side, I read lines only].
10. GET /tokens and GET /tokens/{id} are open to any perimeter-secret holder (13 ids listed in the probe): already recorded (C-116).

CONCLUSION: mint, fail-closed introspection and the DOA clauses are well pinned; revoke-on-outage, the expiry instant and scope matching are not. PASS WITH CONDITIONS: tests for F-C527-1..3, the revoke-on-outage decision, and a lock or compare-and-set for F-C527-4.

What I did NOT do: no wire/auth run; no real DOA roster file run beyond the suite; no sentinel end to end; no store-level tz round-trip mutants; no cli.py audit; no GX10; no whole tools suite.
