VERDICT PASS on 355312178e940a31a03d064b6d3341026b0d4837 (PR 375, Q-29, Lane 15 reviewer; delta b5e74e2..3553121 on the C-984/C-1048 conditions plus an independent invariant probe of the verifier-prefix rule; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. The rule is a definition by scope set (kill, revive, revoke with mint or mint_for_others, no "*"); a row that holds a different but equally powerful combination is not caught. The set is Don's ruling D-18, so this is design, not a defect; it is the whole coverage.
2. The delta is tests only (one file, +15 lines): it cannot make the rule correct, only show that two named mutants die.
3. The builder's "raw-id" mutant is one of TWO `str(...)` sites; the new test kills only one (below), so "both survivors closed" is accurate for the survivors named by C-1057 but not for the class.
4. F-C1048-2 (the estate's real operators file must hold no verifier-prefixed row with bypass_operator_list before deploy) is a fact about a file I cannot see; nothing here verifies it.
ASSUMPTIONS: head current (git ls-remote = full sha above); delta = test_verifier_prefix_c805.py +15 (git diff b5e74e2..head --stat); made-up key and ids only.

REASONING
1. Baselines: the three operator-auth test files (verifier prefix, format 2, machine verifier) 198 passed (HIGH, run).
2. Independent invariant probe through the real loader (parse_registry, format 1 and format 2): 18 operator ids (exact prefix, no suffix, uppercase, svc-verify-, verifier-, leading and trailing space, non-ASCII hyphen, zero-width space, extra letter, underscore) x 906 scope sets (every combination of up to five scopes from kill, revive, revoke, mint, mint_for_others, bypass_operator_list, drill, attest, ledger_attribute, sweep_kill and "*", plus the verifier set with and without "*" and bypass) x 2 statuses x 2 formats = 65232 documents. 30813 loaded, 34419 refused (RegistryUnavailable), 0 other exceptions. Invariants checked on every loaded active row: (I1) holding kill, revive, revoke and a mint scope without "*" implies the id starts with exactly `svc-verifier-`; (I2) an id starting with that prefix never holds bypass_operator_list. 0 violations (HIGH for this corpus). The loader accepts only the known scope names and statuses "active" or "revoked" exactly (operator_auth.py:200, :989, :1113), so a scope or status spelled differently cannot slip past the comparison (HIGH, read).
3. PR tests plus probe against 16 mutants of the rule: 14 killed by the PR tests. Killed: any-of-core instead of all, mint requirement dropped, mint_for_others dropped (the probe shows 91 invariant violations under it), revoke dropped from the core, star exemption removed, status default flipped (the delta's `status-required`), status check dropped, prefix compared case-insensitively or stripped (16 violations each), the prefixed-with-bypass rule off (1595 violations) or ignoring status or lowercase-insensitive, scoped-without-prefix rule off (208 violations), non-list scopes guard, and (b) the second `str(...)` below. SURVIVED both the tests and the probe: (a) `list_bound` without the `authenticated` test (whether an unauthenticated OperatorAuth can carry a prefixed id was not examined; pre-existing, outside the delta), and (b) `str(...)` removed in `_verifier_scoped_without_prefix` (operator_auth.py:691) (HIGH, run).
4. The delta's `raw-id` claim, checked: removing `str(...)` in `_verifier_prefixed_with_bypass` (operator_auth.py:700-701) survives the pre-delta test file (57 passed) and is killed by the new non-string-id test (1 failed): closed. The same removal in `_verifier_scoped_without_prefix` is not reached by that test (its scopes do not complete the verifier set) and survives.
5. merge-tree: clean against main and with PRs 325, 348, 352, 356, 369, 381, 394, 401, 402, 410; CONFLICT with PR 355 in packages/field-core/tests/test_operator_auth_format2.py (test file, content).

FINDINGS
- F-Q29-1 LOW: a non-string operator id holding the full verifier scope set is untested (survivor b); behaviour today is a refusal text via `str(...)`, which a refactor could turn into an AttributeError.
- F-Q29-2 INFO: survivor (a), the `authenticated` test in `list_bound`, is unpinned; confirm an unauthenticated OperatorAuth never carries an id.
- F-Q29-3 INFO: conflict with PR 355 in a test file; mechanical.
- Carried: F-C1048-2 (Don's confirmation of the estate's real operators file before deploy); F-C1048-3 (format 1 accepts unknown scope strings: not seen in the probe, where unknown scopes were not generated for format 1; not re-checked).

NOT VERIFIED: CI, GX10, the estate's real operators file, behaviour through a real request path with ENFORCE (probe stops at the loader).

CONCLUSION: PASS. 65232 probed documents, 0 violations of either invariant; the delta closes `status-required` and `raw-id` as named; one LOW unpinned site and two INFO.
