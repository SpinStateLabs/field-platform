VERDICT: PASS WITH CONDITIONS on main b929f12659cf7673678fea05dd8da66f5435e7d2

C-524 lifecycle-manager post-merge re-audit (Lane 7). Scope: PerRequestAuthClient (api.py:87), the builders (api.py:114, :123), key per request, proxy environment (C-462 F-C462-2), error text.

OBJECTIONS FIRST
1. Key-per-request is proven only against a local origin; a real receiving guard was not in the loop.
2. A green R3 header suite says nothing about transport behaviour; the class overrides only build_request.
3. "No leak in responses/logs" with made-up markers shows absence for the paths I drove, not for all paths.

ASSUMPTIONS
A1 httpx 0.28.1 (venv, CI-pinned line). A2 Made-up secrets/keys in temp dirs only. A3 NO_PROXY/no_proxy cleared in probes (sandbox value masks proxy tests). A4 Tree = main b929f12, clean.

REASONING / RESULTS
1. Key per request (probe, real local origin) [HIGH]: key file v1 -> sent; rewritten to v2 -> v2 on next request, same client; empty / multi-token / non-UTF-8 / missing file -> no operator pair, shared-secret header still sent; restored -> pair back; a per-request x-field-auth replaces the client one; wire headers byte-equal to the old httpx.Client(headers=auth_headers()) for an unchanged key. Matches the docstring (api.py:88-103).
2. F-C462-2 proxy environment, STILL OPEN on main [HIGH, wire-proven]: with HTTP_PROXY, http_proxy or ALL_PROXY set, PerRequestAuthClient sends the request to the proxy (1 hit each, same as a plain httpx.Client control) carrying the shared secret and the operator key. _trust_env is True on both delegation_client() and killswitch_client() (api.py:117, :128). Severity: HIGH (credential disclosure to a third hop wherever an env proxy is set). Class: proxy-environment / secret egress. Fix is in PR 318 (constructor pins trust_env=False); not on main.
3. Next-door, same class: cli.py:194 builds a bare httpx.Client carrying _perimeter() headers (same exposure by construction, trust_env default True). Not wire-probed [MEDIUM]. Severity MEDIUM-HIGH.
4. follow_redirects is False by default (httpx), so no redirect re-send of the secret [HIGH]; no code pins it. LOW: pin it so an httpx default change cannot reopen it.
5. Error text [HIGH for the driven paths]: /health, /findings 404, /sweep 503/422, /sweep 500 with upstream down -> fixed or generic text; the secret and key markers appear in no response body and no captured log line (8 lines). Key-file problems log fixed text + exception type only (operator_auth.py:312-343).
6. Suites: lifecycle-manager 224 passed (main). Hand mutants on tests/test_lifecycle_headers_r3.py: 6/6 killed, no survivors: override order flipped (8 red), per-request headers dropped (10), keys captured at init (10), auth merge removed (23), killswitch built as plain client (11), delegation built as plain client (14).
7. Mutant NOT possible on main: removing trust_env=False (it is absent). No test asserts the proxy behaviour on main; PR 318 adds that.

FINDINGS
- F-C524-1 HIGH, proxy-environment: api.py:87-129 (above). Merge PR 318 after its own gates.
- F-C524-2 MEDIUM-HIGH, same class: cli.py:194; PR 318's lint scope decides whether it is caught (my C-547 report lists the lint's cross-file/alias gaps).
- F-C524-3 LOW: pin follow_redirects=False in the constructor.

CONCLUSION: the key-per-request design is correct and well killed by tests; the proxy-environment exposure is real on main and unfixed. PASS WITH CONDITIONS: land the PR 318 fix and cover cli.py:194.

What I did NOT do: no real receiving guard; no wire probe of cli.py:194; no registry/ledger client (field-core clients) audit here; no GX10 run; no whole tools suite (package suite only); no async paths in the tick loop exercised beyond the suite.
