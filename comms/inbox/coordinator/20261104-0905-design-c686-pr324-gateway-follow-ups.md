# C-686: read of PR 324 (posture-flag refusal names the variable, never its value), follow-ups from C-596, Lane 10

Head ca70eec (force-gateway api.py 6 lines, tests +39). Read-only; UNVERIFIED on any estate. Probe: 20261104-0900-design-c686-gateway-echo-probe.py (a canary in `FIELD_SENTINEL_URL` and in five numeric variables, made-up strings only).

VERDICT: PASS on ca70eec for what it changes: the posture-flag refusal now names only the variable (api.py:299-301 on the head; the 40-character value echo of C-376 F-C376-2 / C-502 is gone) and the force-gateway suite passes (447). The two follow-ups the card asks about are REAL on this head, and cards exist for both (below). Confidence HIGH (run).

## ASSUMPTIONS
1. `/health` is reachable without the perimeter secret on an estate that sets none; with a secret set I did not check whether `/health` is an open path (not in source I read).
2. "Five numeric tunables": I tried five variable names read by the gateway; the card's five may differ.

## Objections first
1. `GET /health` returns the configured sentinel URL verbatim as `sentinel_url` (api.py:822-824 sets it, api.py:858 returns it). Probe: with `FIELD_SENTINEL_URL` holding a user name, a password and a query token (canaries), `/health` answers 200 and BOTH canaries appear in the body. A URL with userinfo or a token in the query leaks to anyone who can read `/health`. MEDIUM (class C: an environment value placed in an API reply; the repository's own compose defaults carry no credential, but the variable is operator-set). HIGH (run).
2. The 503 body under enforce when the sentinel is unreachable: the code path names the variable `FIELD_SENTINEL_URL` (api.py:39 docstring: "unset while enforcing => every /v1/messages answers 503 naming it"), not its value as far as I read; I did not provoke an unreachable sentinel with a credentialed URL to see whether the transport exception text (`str(exc)` names the URL) reaches the body. UNVERIFIED, MEDIUM-LOW.
3. Numeric tunables in a startup `ValueError`: of the five I tried, ONE raises with the value in its message: `FORCE_GATEWAY_LATENCY_BUDGET_MS` (api.py:801 `float(os.environ.get(...))`: a non-number makes `create_app` raise `ValueError` quoting the string); the other four (`FORCE_GATEWAY_SENTINEL_TIMEOUT`, `FORCE_TELEMETRY_RETAIN`, `FORCE_GATEWAY_COOLDOWN_S`, `FORCE_GATEWAY_JUDGE_SAMPLE`) fall back to their defaults without an error (the resolvers at api.py:322-334 and :238-246 catch `ValueError`). A secret pointed at the budget variable by mistake reaches the traceback. LOW-MEDIUM. HIGH for that one.
Steelman: the PR does what its title says, with a test per posture flag, and the remaining sites are separate cards.

## Results
- The refusal text: `f"{name} is not a recognised value; use 1, true, yes or on to arm it, 0, false, no or off to leave it off, or leave it unset"`: names the variable, no value (the diff removes the `[:40]` echo). Test file +39 lines; the force-gateway suite: 447 passed (with absolute source paths).
- Cards: the follow-ups are carried by C-623 (builder; `/health` and the 503 show scheme, host and port only; in review as PR 352 at 8d86806) and C-582 (the numeric tunables raise a variable-naming error); the reviewer card for PR 352 is C-663. So yes, a card exists for each; neither is merged.

## Findings
F-C686-1 MEDIUM: `/health` must not echo a URL with userinfo or a query; return scheme, host and port only (C-623 does this: keep my probe as an acceptance test on PR 352 with both canaries absent).
F-C686-2 LOW-MEDIUM: parse the latency budget through the same tolerant resolver as the other four (default on junk) or raise an error naming only the variable (C-582).
F-C686-3 MEDIUM-LOW (verify): provoke the unreachable-sentinel 503 with a credentialed URL and confirm the body carries no URL; I did not.

## What I did NOT do
Did not run the gateway against a sentinel. Did not read PR 352. Did not check whether `/health` is an open path under a perimeter secret. Did not edit the PR.
