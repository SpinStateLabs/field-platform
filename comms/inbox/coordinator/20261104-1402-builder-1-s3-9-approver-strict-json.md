# builder-1 S3-9 (claude-approver strict JSON maps)
PR: https://github.com/SpinStateLabs/field-platform/pull/631 (draft), head 3889a7a7.
Ran: tests/test_agent_map_strict_json.py 13 (10 red on unmodified config.py); 3 mutants caught (6, 4, 2 failed); services/claude-approver/tests 328 passed.
Decision for Don: an existing map file that repeats a key now empties the whole map (fail closed) instead of loading the last value.
Other: #568/#584 CI red is the same main-side start_role_session lint; commented once on #584 (568 already).
