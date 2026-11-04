# builder-1 S3-10 (conformance-sentinel @governed client lifecycle)
PR: https://github.com/SpinStateLabs/field-platform/pull/632 (draft), head 28384584.
Ran: tests/test_governed_client_lifecycle.py 8 (4 red before); 3 mutants caught (3, 1, 1 failed); services/conformance-sentinel/tests 271 passed. 50 calls now build 1 client (was 50).
Decision for Don: close() also closes a caller-supplied client.
Other: dhagell marked #621, #622, #623, #625, #626 ready for review; #571 CI red is the same main-side start_role_session lint, commented once.
