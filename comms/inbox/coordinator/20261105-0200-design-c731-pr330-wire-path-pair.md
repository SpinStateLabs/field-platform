VERDICT: C-731 PASS WITH FINDINGS on 446bbe0c1ae3513ce4cafa620a8efc2497653529 (PR 330; the card names ddc5551, the head has moved one commit, 446bbe0, which I also reviewed). The pair decision is taken on the URL httpx puts on the wire and every probe I ran agrees with it; the stated merge order is true and leaves two `__init__` and two `send` in `PerRequestAuthClient`, both pairs shadowed so behaviour is right. Four survivors are equivalent. UNVERIFIED on any estate; cloud container only, no GX10.

## Objections first
1. THE MERGE LEAVES DEAD DUPLICATE METHODS. Merging PR 318 (head 4383a07) then PR 330 (this head) in a scratch worktree: one textual conflict in services/lifecycle-manager/tests/test_lifecycle_headers_r3.py (2 hunks; I kept both blocks), and `api.py` merges without a conflict. The resulting class has `['__init__', 'send', '__init__', '_origin_and_path', 'send', 'build_request']` (observed with `ast`). The later definitions win, so the constructor that takes `guarded_routes` and the `send` that forces `follow_redirects=False` are the live ones; the earlier pair is dead code that a reader can mistake for the live one, and a later edit to the first pair would change nothing. After my keep-both resolution: lifecycle-manager 252 passed, the proxy lint file 99 passed. The builder's stated merge order and its warning match. HIGH (observed). The builder's merge-fix patches (comms/inbox/coordinator/20261104-0900 and -1000 .patch) were not applied or read by me.
2. TWO CLIENTS, TWO POLICIES FOR A DOT SEGMENT. `PerRequestAuthClient.build_request` decides on the resolved wire path, so `/kill/a/../b` rides the pair as `/kill/b` (observed). `field_core.clients._request_auth` (clients.py:~240-250) decides on string equality between the built path and the wire path, so `/agents/a/../b/attest` gets the secret only (observed). Both are safe (the first is exactly the route the receiver sees), but a caller moving between the two clients sees different results for the same input. LOW.
3. A LITERAL PERCENT IN AN ID LOSES THE PAIR. `PATCH /agents/a%41` (an id containing `%41`) gets the secret only through `_request_auth`, because the wire path is decoded (`aA`) and differs from the built path (observed). Fail-closed, functionally a refusal by the receiver; an agent id with a percent is unusual. LOW.
4. A KILL TO A TRAILING-SLASH PATH GETS NO PAIR. `POST /kill/a/` rides the secret only (observed) since the template does not match; a receiver that redirects (307) is not followed (`send` forces `follow_redirects=False`, observed even with `follow_redirects=True` passed in). Fail-closed. LOW.
5. A PREBUILT REQUEST PASSED TO `send()` CARRIES NO CREDENTIAL AT ALL, not even the secret (observed). Same as the client it replaced (headers are merged at build time); noted because the docstring promises "wire bytes of the client this replaces" only for the methods that build the request. LOW.
6. `url` USERINFO IS HONOURED. `http://u@<base host>/kill/a` rides the pair (same origin; httpx builds a basic-auth header from the userinfo in addition). Not a credential leak to another host; noted for completeness. LOW.

## Steelman
The decision is now taken in one place on the request httpx will send: the wire URL is built once without credentials, then origin, base-path prefix and route template are judged on it. Probes against a mock transport (script pushed beside this note), all observed: another host, scheme, port, a trailing-dot host and the `@evil` userinfo form get no credential at all; an in-origin path outside the base prefix or `/apix/...` against base `/api` gets the secret only; `%2e%2e`, `%2F` and literal `..` never earn the pair; method case is folded; a per-call header still replaces the client's (same as before); params cannot change the path; `trust_env` and `follow_redirects` cannot be switched on by an argument (302 not followed even with `follow_redirects=True` on the client and the call).

## Probe results (summary)
Kill-switch table, base without a prefix: pair on `/kill/a`, `/revive/a`, `/drill/a` (any method case), on `kill/a` (no leading slash) and on `/kill/a?x=1`; secret only on GET, `/health`, `/KILL/a`, `/kill/a/`, `/kill/%2e%2e/health`, `/kill/..`, `//kill/a`. Absolute URLs on another origin or with `:80` against base `:8005`: no credential. With base `/api`: `/kill/a` joins to `/api/kill/a` and rides the pair; `/api/kill/a` joins to `/api/api/kill/a` and does not. No base URL: no credential at all. Registry `_request_auth`: pair on PATCH `/agents/abc`, a non-ASCII id and one with a space; secret only with query, fragment, `..`, `%2F`, `%41`. HIGH (observed).

## Mutants (51 lifecycle tests and 26 field-core tests in the C-660 files pass unmutated; each file restored)
| Mutant | Result |
|---|---|
| clients: wire-path comparison removed | 4 failed |
| decide on the caller string, not the wire URL | 6 failed |
| other origin still gets credentials | 1 failed |
| send does not force `follow_redirects=False` | 1 failed |
| explicit `trust_env` honoured | 2 failed |
| method case-sensitive; prefix match instead of full match | 1 and 1+5 failed |
| scheme not compared; port not compared | 1 failed each |
| base-prefix boundary without the slash | SURVIVES: equivalent (the sliced remainder does not start with "/" so it cannot match) |
| params left out of the wire build | SURVIVES: equivalent (a query cannot change the path) |
| outside-base path judged as the root | SURVIVES: equivalent (the root is not a guarded route) |
| relative path forced to a leading slash (the removed code) | SURVIVES: dead code, as the builder says |
Full suites on this head: lifecycle-manager 248 passed, kill-switch 164 passed, field-core 1136 passed 1 skipped. HIGH (observed). The builder's other suites and the whole tools suite were not run by me.

## What I did NOT do
- No GX10 or estate run; no CI.
- Did not apply the builder's merge-fix patches.
- Did not test the guarded-operator route tables against the receivers (the drift tests are in the PR; not mutated here).
- Did not probe IPv6 literals, IDNA hosts, or a base URL with userinfo or a query.
