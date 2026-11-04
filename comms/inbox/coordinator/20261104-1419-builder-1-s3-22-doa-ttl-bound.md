# builder-1 S3-22 (generate_doa_roster --max-ttl-days bound)
PR: https://github.com/SpinStateLabs/field-platform/pull/642 (draft), head 1190b304.
Ran: tools/tests/test_generate_doa_roster_ttl_bounds.py 9 (6 red before); 3 mutants caught (3, 2, 1 failed); the three DOA tools test files 47 passed.
Ceiling check vs PR 584 (read its diff): service bound le=999_999_999; generator 3650 sits inside it, so merge order does not matter.
Decision for Don: keep 3650 (card's number, a policy choice) or align to 999_999_999.
One existing test changed: test_a_roster_the_service_model_rejects_is_never_written used --max-ttl-days 0, now refused earlier; it forces the service-model rejection by patching DoaRoster.model_validate instead.
