# builder-1 S3-11 (sealed-ledger GET /events limit tests)
PR: https://github.com/SpinStateLabs/field-platform/pull/633 (draft, tests only), head 1e2c304e.
Ran: tests/test_events_limit.py 19 passed on unmodified source; 4 mutants caught (6, 2, 1, 3 failed); services/sealed-ledger/tests 821 passed, 5 skipped, 1 error = test_operator_observer_c6_serve (ledger serve exited early; errors on unmodified main here too, checked with my file removed).
Finding: none; README line 15 says "last N matches globally".
Other: #572 and #580 (3.11) CI red is the same main-side start_role_session lint; commented once on #572.
