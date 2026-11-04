# builder-1 S4-5 (clause ids registered, tests only)
PR: https://github.com/SpinStateLabs/field-platform/pull/653 (draft), head 53b3a144.
Ran: packages/field-core/tests/test_clause_ids_registered.py 8 passed on main; 20 ids found, only D.manifest_expired unregistered (in KNOWN_PENDING, commented). Verified on the real tree, each reverted: fake id in drift.py fails (names path:line); KNOWN_PENDING emptied fails; id added to CLAUSES fails exactly the stale-pending test; bad key fails. packages/field-core/tests 1552 passed, 2 skipped.
Finding: D.manifest_expired (delegation_authority/api.py MANIFEST_EXPIRED, PROVISIONAL) is emitted but not in CLAUSES, so clause_text() prints '<unknown clause>' for it. NOT added (owner's ruling).
Decision for Don: register D.manifest_expired or rule on another id.
