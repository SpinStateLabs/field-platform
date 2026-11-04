# builder-1 S4-3 (delegation CLI verbs)
PR: https://github.com/SpinStateLabs/field-platform/pull/651 (draft), head d63aa2f9.
Ran: tests/test_cli_verbs.py 51 (39 red before, 12 controls); 6 mutants caught (10, 1, 20, 8, 4, 10 failed); services/delegation-authority/tests 308 passed (incl. test_cli_client_guard_c1087 and test_doa_check_verb); tools/tests/test_operator_cli_c2.py 98 passed.
Decision for Don: exit code for an unreachable service is 2 here (the card) and 1 in #624 (kill-switch CLI); align?
