# builder-1 S3-7 (field-agent CLI verb tests)
PR: https://github.com/SpinStateLabs/field-platform/pull/628 (draft, tests only), head 3501390c.
Ran: tests/test_cli_verbs.py 17 passed on unmodified source; 4 exit-code/text mutants each fail 1; packages/field-agent/tests 223 passed, 1 failed = known test_the_process_never_exits_on_a_halt (fails on unmodified main here).
Finding: no verb contradicts its docstring. Pinned for Don: negative token options pass through the CLI unrefused.
