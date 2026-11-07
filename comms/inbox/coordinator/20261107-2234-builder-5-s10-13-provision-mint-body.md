# B-S10-13 report (builder-5)
Draft PR 942: lifecycle provision returns a failed mint step (http 201, "the token may exist") when delegation's 201 body is not a JSON object, instead of a traceback after register/cap/rate_limits.
Evidence: 7 new tests; the 5 bad-body cases fail on original engine, pass with fix. Suite 452 passed, 5 failed (test_cli_clients_no_proxy_c575, identical on unmodified main). Anchors 0 wrong.
