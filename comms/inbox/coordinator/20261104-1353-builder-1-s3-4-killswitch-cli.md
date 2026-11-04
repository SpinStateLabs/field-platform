# builder-1 S3-4 (kill-switch CLI)
PR: https://github.com/SpinStateLabs/field-platform/pull/624 (draft), head 3d97cbe4.
Ran: tests/test_cli_verbs.py 18 (11 red on unmodified CLI); 3 mutants caught (1, 7, 2 failed); services/kill-switch/tests 288 passed; tools/tests/test_operator_cli_c2.py 98 passed.
Other: #578 and #568 CI red is the same main-side start_role_session lint; commented once each. The main fix is still unowned.
