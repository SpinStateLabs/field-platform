# Review PR 606 @ 9d6b163fb3e312b438e420c3403ee0e6073519f2 (conformance-sentinel: upstream bodies of the wrong shape BLOCK) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head 9d6b163f. UNVERIFIED (cloud, no GX10). Condition 1 pins the docstring's no-echo promise.

## Objections first
1. This is a policy enforcement point: a wrong-shaped body must never ALLOW. The fail-open paths I attacked: missing `spent_cents` read as 0 (T4), a bool or float passing as a whole number (T1, T2), a string scope turning `in` into a substring test (C1), a client left unwrapped (O7-O9). All killed.
2. The docstring promises "a fixed text that never carries the body". Nothing pins that promise (O5, O6 survive).
3. Both the "not JSON" and "not an object" branches raise `ConnectionError`, so the sentinel's existing handler turns them into the unreachable-upstream BLOCK. I read that handler's behaviour only through the tests, not the code (not read).

## Facts (HIGH)
- Head fetched via refs/pull/606/head = 9d6b163f; 1 commit; contains origin/main 97dcfec1; author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. `engine.py` +36 -5 (`_object_body`, a `spent_cents` check, a scope check), `tests/test_upstream_body_shapes.py` +183 (new).
- Baseline unmutated: whole conformance-sentinel suite 319 passed (relative `PYTHONPATH` incl. every sibling service `src`). The new file alone: 56 passed with each survivor tested against the whole suite as well.

## Mutants (new file first with `-x`; any survivor then ran the whole suite; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| `_object_body`: non-object refused, non-JSON refused, message holds no body, no chained cause (O1-O6) | 6 | 2 (O1, O2) | 4 (O3, O4, O5, O6) |
| all three upstream clients use it (O7-O9) | 3 | 3 | 0 |
| `spent_cents`: missing, bool, float, negative refused; zero allowed; BLOCK on E.spend_cap; no value echoed; ceiling `>=` (T1-T9) | 9 | 9 | 0 |
| scope: string, non-string entries refused as D.scope; None is the ordinary out-of-scope path; no value echoed (C1-C7) | 7 | 5 | 2 (C3, C4) |
Totals counted from the table: 6+3+9+7 = 25 rows; killed 2+3+9+5 = 19; survived 4+0+0+2 = 6; anchor failures 0.

## Survivors (each also survives the whole suite)
- F-R606-1 MEDIUM-LOW (O5): the "not an object" message can carry `{body!r}` and nothing fails. The docstring and the PR title say the body is never carried; the reason line is a sentinel verdict text a caller may read. Pin: a distinctive marker in the body, assert it is absent from the verdict reasons (the spend-total and scope reasons have this pin: T8, C6).
- F-R606-2 LOW-MEDIUM (O6): `from None` removed passes; a chained cause could expose the original exception in a traceback.
- F-R606-3 LOW (O3, O4): a non-JSON 200 returning `{}` or raising a different exception type passes. I did NOT prove these are equivalent (an empty object might still BLOCK downstream: not traced); the test file has no non-JSON-text case for the `introspect` and `totals` clients (not checked per client).
- F-R606-4 LOW (C3, C4): a `None` scope refused as D.scope, or a falsy scope coerced to `[]`, still BLOCKs; only the clause label differs; the test for the ordinary out-of-scope block does not distinguish the clause. Near-equivalent.

## Conditions
1. Pin F-R606-1 (and ideally F-R606-2) before this lands, or the coordinator rules them follow-ups.
2. GX10 16/16 and CI on this head.
