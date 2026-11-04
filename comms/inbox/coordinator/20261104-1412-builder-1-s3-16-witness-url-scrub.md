# builder-1 S3-16 (sealed-ledger witness URL scrub)
PR: https://github.com/SpinStateLabs/field-platform/pull/638 (draft), head bceb9753.
Ran: tests/test_witness_url_scrub.py 13 (11 red before); 3 mutants caught (4, 8, 3 failed); services/sealed-ledger/tests 815 passed, 5 skipped, 1 error = test_operator_observer_c6_serve (errors on unmodified main here too).
Open for Don: the daemon's `read failed ({exc})` warning prints httpx's exception text, unverified whether it can carry the URL; separate hunk, not changed.
Other: main CI is red from tools/start_role_session.py (#532) tripping test_http_env_proxy_lint_c57; ~15 of my PRs show it (561, 563, 568, 571, 572, 573, 576, 578, 579, 580, 581, 582, 584); commented once on each. Proposed patch (not built; not in my queue): pass ProxyHandler({}) / trust_env=False in start_role_session.call, or add the allowlist line the test names. Needs an owner.
