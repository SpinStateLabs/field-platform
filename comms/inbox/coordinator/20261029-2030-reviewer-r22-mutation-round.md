# R-22 reviewer report: adversarial mutation round on the code of PRs 58, 59, 61, 63 (main b92ec10 + 70fa59f tests)

VERDICT: 74 mutants run (generator v2, operator classes the first one lacks), 58 killed, 16 survived. The break-glass sealed rules (PR 58) are fully pinned (20 of 20). The survivors are in the alerts retry classification (PR 59), the retired-hash witness payload (PR 61) and a cosmetic error label (PR 63).

OBJECTIONS FIRST
1. "20 new mutants each" was requested; I ran 20, 15, 19, 20: five PR 63 and one PR 59 candidates were discarded because the line-level string mutation produced invalid Python (an implicit string concatenation), a mutator limitation, not a kill.
2. A seeded random sample of candidates (63, 33, 65, 90 candidates; seed 22) is not an exhaustive round.
3. Survival in a narrow test set (the PR's own suites) says the PR's tests do not pin it; another suite may.

ASSUMPTIONS
1. Clone state: main b92ec10 plus PR 87 test file (70fa59f); `~/ff-work/mutate_gen2.py`: `and`<->`or`, `not` removal, bool and int constant changes, short-string-to-empty, `return X` -> `return None`, call-statement deletion, `raise` deletion; harness honours PYTHONPATH (the C-67 fix). [HIGH]
2. Test sets: PR 58/63: field-core `test_operator_auth*.py`, `test_operator_rotation_r2.py` (439+ tests, 5 s); PR 59: `test_alerts_ntfy.py`; PR 61: `test_operator_observer_r2.py`, `_c6.py`, `_c6_fetch.py` (30 s). [HIGH]

REASONING
1. PR 58 (break-glass id must be sealed, operator_auth.py:940-1010 `parse_format2` sealed rules): 20 mutants, 20 killed. [HIGH]
2. PR 63 (alias squat, operator_auth.py:678-740 `validate_rows`, `_malformed`): 15 run, 13 killed, 2 survived: L706 (an alias error message string emptied) and L723 `elif isinstance(oid, str) and oid:` -> `or` (the "(id not shown)" label for a non-printable string id: with `or` a non-string truthy or an empty-string id also gets the label). Both change a diagnostic label, not a validation decision: INFO (F-R22-3). The alias rule itself `n == BREAKGLASS_ID and r["operator_id"] != BREAKGLASS_ID` (:702) and `n == "*"` were in range and not among survivors. [HIGH on the survival; MEDIUM that no decision is affected: read]
3. PR 59 (alerts: empty ProxyHandler opener, send path; alerts.py:400-520): 19 run, 9 killed, 10 survived. Survivors: the `_send` result tuples' retryability flag: L490 (`return False, "timeout", None, True`: return -> None and two bool flips), L493, L495 (`"network"`), L498 (`status in _RETRY_STATUSES`): no test pins which failures are retryable (a timeout or network error marked non-retryable, or an HTTP 400 marked retryable, passes); L511 `conn.close()` deleted (connection not closed); L407 `lines.append(f"sent: ...")` deleted (the "sent" line of the alert body); L415, L417 tag content-problem check separator/label. The opener itself (the PR's point) is pinned (C-6/F-C6 history). LOW (F-R22-2). [HIGH]
4. PR 61 (observer self-witness, operator_observer.py:418-471): 20 run, 16 killed, 4 survived: L463 `n > 0` -> `n > 1` (the first sighting of exactly ONE retired hash at startup would not be witnessed), L464 and L466 (payload field names: `"service"`, `"startup"`, `"observed_from"` emptied: the witness payload shape is unpinned), L413 `return written` -> None (the caller does not use the count). The retired-hash event is the observer's evidence of a hash reuse; its payload fields and its boundary should be pinned. LOW-MEDIUM (F-R22-1). [HIGH]

CONCLUSION
No decision-affecting survivor in PR 58 or 63. Add tests for the alert retryability table, the one-retired-hash startup witness and its payload fields. Not done: the other 30 candidates per range; arithmetic mutants in other modules.
