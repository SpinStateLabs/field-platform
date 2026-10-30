VERDICT: PASS WITH CONDITIONS on 191affb8a9c89fa59506ec30029ce4b5c4857ca7 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's test file ran: 118 passed)

Head matches the card. One commit on main; author and committer are the no-reply identity. One file: packages/field-core/tests/test_operator_auth_format2.py (+68), tests only. Test-only change: no production code to regress.

OBJECTIONS FIRST
1. Case and look-alike identities are accepted. In format 2: an id "Don" next to "don" is ACCEPTED; an alias "DON" on another row (the id is "don") is ACCEPTED; an alias "don hagell" beside "Don Hagell" on another row is ACCEPTED. The rules compare exact strings, so these are distinct identities, but a human reading the file sees a collision. If any consumer lower-cases ids or names (events and headers are lower-cased elsewhere in the module: operator_auth.py:411, :552, :588, :1301 are event prefixes and header names, not ids) the rules would not catch the collision. I did not find an id comparison that folds case; treated as a design question. LOW, MEDIUM confidence.
2. Aliases with surrounding space or doubled star (" *", "**") are accepted: they are not "*", so the star rule does not apply, and I found no glob matching of lists that would make them equivalent. LOW.
3. The boundary tests prove exactly the cap and over the cap. The card asks for cap-1, cap and cap+1; cap-1 is not tested. It cannot behave differently from the cap case in this code (no eviction below the cap), so the missing test is cosmetic. LOW.
4. The tests reset the cap by monkeypatching MAX_RETIRED_HASHES to 2, not at the shipped value 4096; the logic is size-independent, but the real constant is not exercised. LOW.
5. The new tests read private state (oa._retired_state keyed by absolute path) to assert contents; a refactor of that dict breaks them without a behaviour change. LOW.

ASSUMPTIONS
A1 The three ambiguity rules in scope are: a duplicate operator_id, an alias equal to another row's id, the alias "*" (operator_auth.py validate_rows :678-712). A2 Probes call parse_registry on the file's own test document (made-up ids, hashes of made-up keys). A3 Mutants applied to operator_auth.py in a scratch worktree and restored.

REASONING
1. Probe table (format 2 document, outcome): duplicate id: refused "ambiguous"; alias equal to another row's id: refused; alias "*": refused (also twice in one row); alias shared by two rows: refused; alias equal to the row's own id: refused; empty alias: refused (malformed); alias that is the break-glass id on an ordinary row: refused; id "*": refused (malformed charset); trailing-space id, Cyrillic look-alike id: refused (malformed, the id charset is [A-Za-z0-9._@-], operator_auth.py:86); non-string id: refused; names as a string: refused; one key hash in two rows: refused ("ambiguous", operator_auth.py:1025). ACCEPTED: id "Don" beside "don"; id "DON"; alias "DON"; alias "don hagell"; alias " *"; alias "**"; the same alias twice in one row. HIGH for every probe row.
2. Mutants (each alone, restored, nothing committed): duplicate-id check off -> 1 failed; alias-equals-id check off -> 1 failed; alias-star check off -> 1 failed; shared-alias check off -> 1 failed (existing test); cap condition raised by one -> 1 failed; eviction keeps one fewer -> 1 failed; eviction keeps the oldest -> 1 failed; eviction removed -> 1 failed. One mutant survives: changing the cap test from > to >= (operator_auth.py:1258) is an EQUIVALENT mutant: with exactly cap entries the slice keeps all of them, so no test can distinguish it. HIGH.
3. The eviction rule itself (operator_auth.py:1258-1261: sort by generation, keep the last cap): at cap the oldest generation goes first; the PR's expectation [43, 44] after retiring three with cap two holds. HIGH.
4. Consequence of eviction (not tested): a hash evicted from retired memory is no longer refused if it returns; the new test asserts it is gone from the table but does not assert that the key then authenticates again. The runbook of PR 351 states the limit. LOW.
5. Diff scan: only made-up key strings ("fok_test-... not-a-real-key" style) and invented ids; no real address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The new tests are sharp for the three ambiguity rules and the cap behaviour (every non-equivalent mutant is red). Conditions, none blocking:
- C1 F-C702-1: decide whether ids and aliases that differ only by case should be refused as ambiguous; if yes, a rule and a test; if no, document that case is significant.
- C2 F-C702-2: assert in the over-cap test that the evicted key authenticates again, so the consequence is pinned (or state that it is out of scope).
- C3 F-C702-3: add the cap-1 case for completeness (cosmetic) and keep the equivalent mutant noted.

FINDINGS
F-C702-1 LOW, packages/field-core/src/field_core/operator_auth.py:691-711 (validate_rows: exact-string comparison; "Don"/"don", alias "DON" accepted). PROVEN.
F-C702-2 LOW, packages/field-core/tests/test_operator_auth_format2.py (over-cap test does not pin re-admission of the evicted key). HIGH.
F-C702-3 INFO, operator_auth.py:1258 (> versus >= is an equivalent mutant). HIGH.
F-C702-4 LOW, same test file (private state access, cap shrunk to 2). HIGH.

NOT VERIFIED: that no consumer folds case when comparing ids or names; CI; the rest of the field-core suite.
