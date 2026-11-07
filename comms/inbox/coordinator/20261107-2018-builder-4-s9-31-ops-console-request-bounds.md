S9-31 -> https://github.com/SpinStateLabs/field-platform/pull/936
S9-31: ops-console request models now mirror the kill-switch bounds (operator 200, reason 1000, resolver 200) and reject whitespace-only values; one 422, zero upstream calls (100-agent bulk with 201-char operator was 100 failing calls).
Tests: new test_request_bounds.py 83 cases, 82 red on main, all green now; existing ops-console tests 144 passed with it. environment_anchors --fix applied (docs/ENVIRONMENT.md).
Decision for Don: resolver bound 200 is the console's choice (governor has none on main; #661 adds 200).
