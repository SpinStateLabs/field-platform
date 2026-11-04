builder-1: B-REBUILD-PR362 built. Draft PR https://github.com/SpinStateLabs/field-platform/pull/551 "rebuild of #362", branch rebuild/pr362-alerts-observer-survivors, head f442bc6162f92c0d0381c0e9c18e6aa79ba4b46c on origin/main 97dcfec1. Old head ef852435 untouched.
MORE THAN A PLAIN REBASE: PR 362's commits 8a48d293 and 54c5b867 are already on main (0e1251a0, 2447a485); its head is a merge commit. Only b468f792 carried. Net-effect check: added/removed lines of old (acaf5f24..ef852435) equal new (origin/main..head): IDENTICAL, 2 test files, +23. GX10 not re-run by me.
Ran: field-core test_alerts_send_survivors_c159 44 passed; sealed-ledger test_operator_observer_r2 23 passed.
Range-diff:
1:  8a48d293 < -:  -------- alerts and observer tests: send-path retry table, shut-down, sent line, content labels; one retired hash at startup (C-159)
2:  54c5b867 < -:  -------- observer test: a failed retired-witness write is retried next tick (C-159)
3:  b468f792 = 1:  f442bc61 tests: HTTPException-only failures are retryable; a retired-counter decrease is witnessed (C-159, reviewer C-738)
