# builder-1 S4-12 (spend-governor CLI and provisioning path segments)
PR: https://github.com/SpinStateLabs/field-platform/pull/660 (draft), head 77b0deef.
Ran: tests/test_cli_path_segments.py 85 (82 red before, 3 controls); 9 mutants all caught (12, 10x5, 10, 22, 16, 26 failed); services/spend-governor/tests 376 passed; services/lifecycle-manager/tests against this change 269 passed (provision calls load_rate_limits).
This is the item I flagged in the S4-10 report (provisioning.py:83). One helper provisioning.path_segment (quote safe='' plus %2E/%2E%2E for the dot segments); the CLI imports it.
Merge order: PR 571 (spend CLI operator pair) edits cli.py; not rebased onto it. #658 keeps its own copy (_seg) so neither depends on the other.
