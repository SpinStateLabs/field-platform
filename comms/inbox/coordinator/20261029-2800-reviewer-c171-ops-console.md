# C-171 reviewer report: services/ops-console server side (api.py 741 lines; console.html is R-05) on main 7b4d6f7

VERDICT: the console never holds an operator identity, forwards only the perimeter secret to upstreams and the human's own pair on action routes, and refuses to start otherwise; 114 mutants run, 88 killed, 26 survived. The notable survivor is the symlink-escape guard on the manifest read.

OBJECTIONS FIRST
1. Frame headers and the secure-context refusal are not server code here: the first is the Caddy edge (PR 67), the second is JavaScript (C-20) tested through a node harness; I report where they live, not a mutation result for them.
2. 114 mutants (75 v1 + 39 v2 sampled from 446) are not a coverage figure; the suite takes 44 s, so the sample was capped.
3. I read the identity and forwarding code (api.py:44-130, :612-650) and the manifest and event routes by grep; not every route body.

ASSUMPTIONS
1. Main 7b4d6f7 (PR 94 clone, loader change only); ops-console suite 171 tests. [HIGH]

REASONING
1. Which secret goes where: every upstream `ServiceClient` is built with `_console_headers()` = `x-field-auth` (the perimeter secret from FIELD_SHARED_SECRET) only, "never an operator pair, whatever the environment holds" (api.py:75-80, :86-95). The human's `x-field-operator` / `x-field-operator-key` are forwarded per request by `_operator_kw` (:619-641) on the action routes only: kill, revive, drill, bulk, fleet-halt, token revoke, escalation resolve (:650-735); a missing pair is a 401 under ENFORCE, a malformed one a counted refusal. The console refuses to start when FIELD_OPERATOR, FIELD_OPERATOR_KEY or FIELD_OPERATOR_KEY_FILE is set (`refuse_own_identity`, :58-72; names only, never values). Mutants on these paths were killed (65 of 75 v1). [HIGH]
2. Frame headers: not set by the console process (no X-Frame-Options or frame-ancestors in api.py); they come from the Caddy console catch-all (PR 67, verified on the base file and on the GB10 TLS and plain listeners in C-173). The console reached directly on its container port (8011, compose network only) carries none. [HIGH]
3. Secure-context refusal (C-20): client-side (console.html:757-789: the stored key is sent only when `window.isSecureContext` and https, or http on loopback); tested by `tests/test_setup_behaviour.py` with its own mutant table (:357-360). Not a server rule. [HIGH]
4. LOW-MEDIUM, F-C171-1: `guarded_manifest_path` (api.py:192-230): `if not real.is_relative_to(base): ... a symlink inside pointing out` (L218) forced False SURVIVES the 171 tests: the guard that stops a symlink inside the manifest directory from making `GET /api/agents/{id}/manifest` read a file outside it is untested; `MANIFEST_MAX_BYTES` boundary (L222 `>` -> `>=`) also survives. The route is open under the perimeter secret and returns the parsed manifest. [HIGH on the survival; not probed with a real symlink escape]
5. LOW, F-C171-2: raw upstream text reaches the browser: `ServiceClient.get/post` return `(0, str(exc))` on any exception (api.py:97-110) and `_proxy` raises `HTTPException(status or 502, detail=data)` (:643-648, also :504, :572), so a connection error string or an upstream error body is returned verbatim to the page. Typical httpx messages carry no secret, but the mutant `return 0, str(exc)` -> `None` survives (no test pins what reaches the browser). [HIGH]
6. LOW, F-C171-3: `ConsoleLedger.append` (api.py:374-390): `if status != 201:` forced False, True and `==` all SURVIVE: how a failed ledger append from the console is treated is untested (the console's own events go to the ledger self-reported). [HIGH]
7. LOW, F-C171-4: other survivors: L503 `status != 200` in `agent_manifest` (a registry error dict treated as a record), L633 `if op and key:` -> `or` (a half pair would be forwarded; `parse_headers` already refuses incomplete pairs, so equivalent in practice, not probed), SSE boundaries (L457, L467, L471), `MAX_LISTED_ERRORS` (L254), bulk `max_length=100` (L148), default upstream URLs (L325-343), export filename and header strings (L582-614), `since/until/limit` params (L569, L578), `status != "retired"` count filter (L703). [HIGH]

CONCLUSION
No secret leak and no identity fallback found. Add: a symlink-escape test for the manifest route, a test that a failed ledger append and an upstream exception are shown as designed, and the `status != 201` handling. Not done: console.html (R-05), a live symlink probe.
