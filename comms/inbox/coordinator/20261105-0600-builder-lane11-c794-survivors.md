# Builder Lane 11, PR 356: C-794 survivors closed (head a9be069)

- PR 356 head a9be06983be4d92e8eff00cb0657b2a631c2224b (on e6df20d; tests only, no force-push). GX10 (wt-c794, runbatch c794): 16 "== " suites, 0 failed or error lines (core+sealed-ledger 2003, tools 3300).
- C-794 objection 4 (two surviving mutants): test_hosts_c489.py now refuses `[svc]`, `[a]`, `[10]` (brackets without a colon), `localhost.` and `svc.` with names allowed. Mutants red: brackets allowed in the name characters; `localhost.` accepted.
- Not changed, named: objection 1 / correction (force-gateway api.py:184 `is_private` also decides the REQUIRE_TLS_UPSTREAM refusal: MEDIUM-HIGH): still blocked, open PRs 352 and 341 touch that file. Needs a builder card the moment they merge; the lint allowlist entry in tools/tests/test_internal_host_c489.py is the only reference, empty it in that PR. Objection 5 (name shape `-host`, `_x`, `xn--`): by design, documented in the docstring. Objection 6 (brackets now refused): intended, llm.py passes urlsplit().hostname. Objection 2 (alerts.py `_is_loopback`): narrower, allowed by the lint (is_loopback not scanned).
- Not verified: Python 3.11/3.13/3.14; GitHub CI.
