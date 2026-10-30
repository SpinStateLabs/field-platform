# C-610: read of PR 336 (kill-switch self-route guard on the decoded path), Lane 10

Reviewed: PR 336 head 96d812e (kill-switch `_canonical_path`, `_is_self_endpoint`, the halt client, the ledger-gap counter; services/kill-switch api.py, README, tests/test_self_guard_c574.py, one allowlist line removed, ENVIRONMENT.md). Probe: 20261103-2000-design-c610-self-route-probe-test.py (49 paths plus a route-derived check; `FIELD_REPO=<checkout> python -m pytest -q`). Read-only; output UNVERIFIED on any estate.

VERDICT: the decoding rule is sound and well pinned; the guard is still a denylist of route shapes, and it misses routes this service serves. One finding is the same class as the bind-source and proxy checkers (a list that must equal the app's routes). Confidence HIGH (run).

## ASSUMPTIONS
1. The guard's purpose: a halt signal built from a manifest must never re-enter this service by any route (the file's own comment, api.py:296-301).
2. Routes are those FastAPI exposes: `/docs`, `/redoc`, `/openapi.json` count.

## Objections first (failure conditions)
1. The shapes are a list (`/kill/`, `/revive/`, `/drill/`, `/heartbeat/`, `/liveness`, `/health`) while the app serves more: probe test `every route of the real app is self` FAILS. Not covered: `POST /operator/verify-hash`, `GET /operator/rotation-state`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json`. The first two read or verify operator-key material (a hash check; key fingerprints and expiry) and are reachable by a halt signal whose method is GET or POST if the endpoint host is the kill-switch's own and is on the allowlist. Exposure needs that allowlist entry (deploy-specific, "I do not know" for the estate), so MEDIUM-LOW; the recursion guard exists precisely for the case where it is set. HIGH that they are missed (run).
2. Whatever the decoding, a route added later (a new `/operator/...`) is not in the list: a fourth round in waiting. The fix is structural, as in my bind-source note: derive the guarded set from `app.routes` (or assert in a test, as the probe does, that every route of the app is matched).
3. Case: `/KILL/a1`, `/HEALTH`, `/Liveness` pass the guard. Starlette routes are case-sensitive, so they do not reach a route on this service; a case-insensitive intermediary maps only the PREFIX (the lower-case tail still matches `/kill/`). Practical risk none, hardening only. LOW.
4. Paths that do not route (a `;x=1` path parameter, `%20`, a trailing dot, a zero-width or full-width character) pass the guard; Starlette does not normalise them to routes. Not findings; listed so nobody re-tests them.
Steelman: the guard fails closed on everything odd (double encoding, dot segments, backslash, control characters, NUL), collapses repeated slashes, matches the shape at any depth (`/x/kill/a1` and `/killswitch/kill/a1`), and refuses a legitimate-looking `/v1/kill` by design (stated, pinned, visible as `skipped: self_endpoint`).

## Results (the card's questions)
- Path decoding, my cases: single encoding of a shape (`/%6Bill/a1`, `/%68ealth`, `/%6Civeness`) refused; double encoding (`/%256Bill/a1`) refused; `%2e%2e` and literal `..` refused; an encoded slash inside a segment (`/kill%2Fa1`) decoded to a real slash and refused; backslash, NUL, control characters refused; repeated slashes and a trailing slash handled; a query or fragment never reaches the function (it takes `parts.path`). All 38 of these pass.
- Gap-count arithmetic: the counter starts at 0, increments once per failed `_ledger_note` (api.py:432), is exposed on `/health` (:621); the log line carries the event type and the exception TYPE only (no message), and the PR's test asserts a secret in the exception is absent from the log. Weak spot: the test asserts `>= 1`, so a counter that adds 2 per failure survives (my mutant `+= 2`: 38 passed). LOW.
- Other `except Exception` sites: one is the outbound call (returns a scrubbed `EndpointResult`, with `_scrub`), one the drill restore (writes a `kill.drill.restore_failed` note); neither is a silent ledger gap.
- Redirect and proxy environment: the halt client is `httpx.Client(timeout=..., follow_redirects=False, trust_env=False)`; the allowlist line for it is removed and the C-57 lint test passes (21 passed); the PR's proxy-listener test goes red when `trust_env=False` is removed (my mutant: 1 failed).
- Suite: kill-switch 198 passed on the head.
- Mutants of mine: `trust_env` removed (red), double-encoding check dropped (red), dot segments allowed (4 red), slash collapse removed (5 red), `/health` shape dropped (2 red), `/liveness` shape dropped (2 red), no decoding (3 red); SURVIVORS: counter `+= 2` and DEL (character 127) allowed (the control-character test names no 127 case). Both LOW.

## Findings
F-C610-1 MEDIUM-LOW: derive the self shapes from the app (or add the route-derived test of my probe): cover `/operator/*`, `/docs`, `/redoc`, `/openapi.json` and any future route. One test, no list to maintain.
F-C610-2 LOW: casefold the canonical path before the shape check.
F-C610-3 LOW: assert the counter equals the number of failed writes (`== 1` after one failed kill) and add a DEL (`%7f`) case.

## What I did NOT do
Did not run the service against a live allowlist or a proxy. Did not read the README text beyond the changed bullet. Did not run the whole tools suite. Did not edit the PR.
