# R-10 reviewer report: delegation-authority alias-mint path (`check_granted_by`, `check_explicitly_listed`) on main 444e49b

VERDICT: the gap named in C-2 condition 2 is closed. Every mutant of the alias-mint functions is killed by at least one suite; the delegation suite alone leaves 10 of 27 alive, but the field-core unit tests kill 8 of those 10. Two survivors remain in both suites (equivalent or near-equivalent).

OBJECTIONS FIRST
1. "Killed by the field-core suite" is a unit-level pin; an end-to-end API regression (foreign `granted_by` accepted at POST /tokens) would not be caught by the delegation suite.
2. The generator makes `if` and comparison mutants only.
3. Main moved to 444e49b during this work (f77bdb0's 5 alias-mint tests are in it).

ASSUMPTIONS
1. Main 444e49b, clones `~/ff-work/r08a` (delegation suite, 161+1 tests, cwd services/delegation-authority) and `r08b` (field-core suite, 977 tests). Ranges: operator_auth.py 634-665 (`check_list_bound_reach`, `check_record_authorized`) and 1425-1490 (`check_authorized`, `check_granted_by`, `check_explicitly_listed`). [HIGH]

REASONING
1. Delegation suite alone: range 634-665 9 mutants, 2 killed; range 1425-1490 27 mutants, 17 killed, 10 survived (L1428, L1433, L1435, L1462, L1476, L1478, L1483, L1484 x3). [HIGH]
2. Field-core suite alone: range 634-665 9 mutants, 8 killed (L651 `if->False` survives); range 1425-1490 27 mutants, 25 killed (L1428 and L1478 `if->False` survive). So L1462, L1433, L1435, L1476, L1483, L1484 are pinned at unit level only. [HIGH]
3. The important one: L1462 `if granted_by in auth.names:` forced True (check_granted_by). With it, a foreign `granted_by` (neither the caller's id nor one of its aliases, no `mint_for_others`) returns the alias flag instead of a 403, and the mint proceeds if the agent's manifest lists the caller. No delegation test notices; only the field-core unit test does. LOW (F-R10-1): add a POST /tokens test with a foreign `granted_by` expecting 403. [HIGH on the survival, MEDIUM on the described effect: reasoned from the code at operator_auth.py:1459-1464, not exercised end to end]
4. Survivors in both suites: L1428 (`check_authorized`: OFF/LOG-ONLY early return forced off: an unauthenticated caller would get 401 outside ENFORCE; callers appear to gate on mode first, not probed), L1478 (`check_explicitly_listed`: the unauthenticated 401 is also raised by `check_authorized` below, equivalent), L651 (`check_record_authorized` OFF guard, same shape as L1428). LOW (F-R10-2). [MEDIUM: equivalence reasoned, not probed]
5. What the alias-mint path enforces (read): ENFORCE and authenticated only; `granted_by == own id` or `mint_for_others` returns False; `granted_by in auth.names` returns True and then `check_explicitly_listed` demands the manifest name the caller (no ref or empty list is 403, unresolvable manifest 503, `bypass_operator_list` not consulted); anything else 403. [HIGH]

CONCLUSION
C-2 condition 2 is closed (mutation level). Add one delegation-level test for a foreign `granted_by` (F-R10-1, LOW). F-C2-2 stays "fixed at f77bdb0".
