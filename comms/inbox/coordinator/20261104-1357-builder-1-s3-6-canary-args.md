# builder-1 S3-6 (field-agent canary args)
PR: https://github.com/SpinStateLabs/field-platform/pull/626 (draft), head 3ab9b3f0.
Ran: tests/test_canary_main_args.py 21 (19 red on unmodified file); 3 mutants caught (2,2,1 failed); packages/field-agent/tests 227 passed, 1 failed = test_the_process_never_exits_on_a_halt, also fails on unmodified main in this sandbox (checked).
Decision for Don: --port 0 is now refused (card said 1..65535).
