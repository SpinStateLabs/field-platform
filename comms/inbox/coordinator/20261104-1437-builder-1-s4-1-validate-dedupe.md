# builder-1 S4-1 (field-core validate: schema dedupe + impossible expiry)
PR: https://github.com/SpinStateLabs/field-platform/pull/650 (draft), head 01236dd4.
Ran: tests/test_validation_schema_gap_dedupe.py 11 (5 red before); 4 mutants caught (3, 1, 1, 1 failed; one survivor found and closed with a new test); packages/field-core/tests 1555 passed, 2 skipped (parity + resolver tests included).
Decision for Don: impossible expiry is a WARNING (status VALID -> VALID_WITH_WARNINGS); a critical gap would flip the resolver to 'invalid' and make the sentinel BLOCK on I.manifest.
Note: the main-red lint failure is fixed on main (b963407a); #591 got its single comment this round.
