# Reviewer C-734 (Lane 6): PR 352 (force-gateway: no value echo in startup errors and the sentinel 503; C-582) @5762a3e

VERDICT: PASS WITH ONE NON-BLOCKING FINDING on 5762a3e81f51eefe3242ca9e39016f1db8c6b817. Every numeric tunable and the sentinel URL no longer echo a value; the whole tools suite is green on the head; 20 of 21 mutants are red. One echo site of the same class remains: the three posture flags still quote the first 40 characters of the offending value (F-C734-1, same class as C-374 F-C374-1). One test gap (F-C734-2). CI on the head at my read: `compose-upgrade-smoke` SUCCESS, the other 6 jobs queued. Nothing used docker (shim never called); bytecode off.

## OBJECTIONS FIRST
1. F-C734-1 LOW to MEDIUM (PROVEN): `_posture_flag` (`api.py` ~298) raises `InvalidPostureFlag` with the first 40 characters of the value. A secret pasted into a posture flag (the usual mis-paste: the wrong variable's value) lands in the startup traceback and the container log. The PR closes the numeric and URL sites and leaves this one, so "no value echo" is true for 5 tunables and the URL, not for the 3 flags.
2. F-C734-2 LOW: the mutant "503 detail without the exception type name" survives. No test pins that `type(exc).__name__` is in the 503 body; the operator loses the only diagnostic hint and nothing goes red.
3. Scope: the fix is per call site (a helper, not a rule). A new `int(os.environ[...])` added later reintroduces the echo and nothing but a per-variable test would catch it; a lint over `api.py` for bare `int(`/`float(` on `os.environ` would close the class.

## ASSUMPTIONS
A1. Head 5762a3e is the PR head (`gh pr view 352`). HIGH.
A2. Canary strings only; no real key used. HIGH.

## REASONING (HIGH)
1. Counts: force-gateway suite 495 passed; the new `tests/test_no_value_echo_c582.py` 52 passed; `test_environment_doc.py` + `test_runbook_pins_c465.py` 51 passed. WHOLE tools suite on the head: 3,129 passed, 4 skipped, 0 failed (539 s).
2. Probes: (A) the 5 refusing numeric tunables raise `InvalidNumericSetting` with fixed text, no chained original, no value; (B) the 4 tolerant tunables fall back to their defaults, nothing echoed; (C) the 3 posture flags raise `InvalidPostureFlag` quoting 40 characters of the value (F-C734-1); (D) blank numeric values refuse at startup (as on main); (E) `public_origin` handled 20 edge cases (userinfo, path, query, fragment, IPv6, no scheme, garbage, empty): origin only, never userinfo; (F) a credentialed sentinel URL: `/health` shows `http://127.0.0.1:1`, the 503 body reads "sentinel unreachable at http://127.0.0.1:1: ConnectError"; the canary userinfo appears in neither the body, the logs nor `/telemetry`.
3. Mutants (21; judge: the force-gateway suite, 495 passed at baseline): 20 RED: value in the `InvalidNumericSetting` message; original exception chained; refusal replaced by a default; each of the 5 call sites back to bare `int()`/`float()`; two default values changed; `public_origin` keeping userinfo, path or query, dropping the port or the IPv6 brackets, returning the raw URL when unparsable, skipping the scheme check; 503 detail with `{exc}`; 503 detail with the full base URL; `/health` with the full URL. SURVIVED 1: 503 detail with the type name dropped (F-C734-2).

## FINDINGS
- F-C734-1 LOW to MEDIUM: stop quoting the value in `_posture_flag`'s error (name the variable and the accepted values only) and add the canary test; or state it out of scope in the PR.
- F-C734-2 LOW: add one assertion that the 503 body contains the exception type name.
- F-C734-3 LOW: a lint for bare `int(`/`float(` over `os.environ` in `api.py`.

## What I did NOT do
- Wait for CI (queued), run Python 3.11, 3.13 or 3.14, or run docker, merge or deploy.
