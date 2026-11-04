# builder-1 S4-8 (field-agent FieldClient scheme)
PR: https://github.com/SpinStateLabs/field-platform/pull/656 (draft), head dc312fda.
Ran: tests/test_field_client_scheme.py 31 (21 red before); 6 mutants caught (17, 4, 3, 1, 4, 5 failed); packages/field-agent/tests 237 passed + 1 known failure (test_the_process_never_exits_on_a_halt, also on unmodified main here); tools/tests/test_internal_host_c489.py 171 passed.
Finding beyond the card, NOT fixed: a custom prefixes entry like "@evil.example" keeps the http scheme but moves the HOST via userinfo; prefixes is caller-supplied, so left; a same-host check in _call would close it.
Decision for Don: a FieldClient with a non-http(s) or scheme-less base_url now raises at construction.
