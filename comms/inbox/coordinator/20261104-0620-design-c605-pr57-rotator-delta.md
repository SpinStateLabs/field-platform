# C-605: read of PR 57 (key rotation R4a rotator core) at 30ac1e1 against C-496, Lane 10

Read-only; UNVERIFIED on any estate. No key was printed, read or kept. Head 30ac1e1; the delta from 11c55c7 (the head of reviewer C-496) is 11 files, of which the PR's own are tools/operator_rotate.py (1 line) and the rotation tests; the rest is main merged in (861f02a) and the C-57 lint files.

VERDICT: the C-496 blocker is FIXED; no new finding of MEDIUM or higher in the delta. Confidence HIGH (run).

## ASSUMPTIONS
1. C-496 F-PR57D-1 was: `tools/operator_rotate.py:88` built `httpx.Client(timeout=TIMEOUT_S)` and so read the proxy environment while carrying the shared secret.
2. The delta of the PR's own code is the commit a46679c ("the estate HTTP client ignores the proxy environment") plus tests in 30ac1e1.

## Objections first
1. The fix pins `trust_env=False` but not `follow_redirects`: httpx's default is False, so nothing follows a redirect today, but a later edit passing `follow_redirects=True` would resend `x-field-auth` to a redirect target (my C-645 probe shows the mechanism). LOW. The estate client is not the lifecycle `PerRequestAuthClient`, so the C-547 constructor protections do not apply to it.
2. Config errors are echoed: `ConfigError(f"identity: {exc}")` (operator_rotate.py:198) and `ConfigError(str(exc))` (:226), printed as `detail` (:247). The exceptions are `ValueError` or `TypeError` from `int()` and the identity constructor on config values; they quote a config value (such as a number that failed to parse), not a key (the key is read from a file path the config names; the message carries the path string at most). I did not trace every ValueError message of `rot.Identity`. LOW.
3. The proxy fix is a call-site edit; only the C-57 lint keeps it so, and the lint is on main (this branch has the lint files merged in). If this branch merges before the lint, nothing guards the line. LOW.
Steelman: the client is built with a mock-transport escape hatch for tests, the failure paths raise `EstateError(type(exc).__name__)` or `"HTTP <status>"` (no body, no message), and the ledger appends go through the shared `LedgerClient`.

## Results
- operator_rotate.py:88 is now `httpx.Client(timeout=TIMEOUT_S, trust_env=False)`. Probe (a proxy variable set to a closed local port, then `HttpEstate(...)`): `trust_env False`, `follow_redirects False`, 0 proxy mounts. So the blocker is fixed in behaviour, not only in text.
- The lint file on the head: the C-57 lint passes; the new allowlist file on the branch does not list operator_rotate.py (it would fail if the site were still unmigrated): 346 passed across the lint, the rotation tests (test_operator_rotate_r4a.py, test_deployment_agent_rotation.py) and 6 field-core rotation test files.
- Error handling in the estate client: `_get` raises `EstateError(type(exc).__name__)` on a transport failure and `"HTTP <code>"` or `"not JSON"` otherwise; no upstream body or message is placed in an error (the class C pattern, kept). `build_sha` and `rotation_state` read `/health` and the rotation-state route with the perimeter secret only (`_headers()` returns `x-field-auth`), never the operator pair.
- The ledger appends use `LedgerClient(base_url=ledger_url)`: after PR 330 merges, the pair rides only `POST /events` (a guarded route), not reads.
- New tests in 30ac1e1 (no-row precheck, incident expiry, `verify_current` daemon check): pass.

## Findings
F-C605-1 LOW: pass `follow_redirects=False` explicitly at operator_rotate.py:88 and pin it next to the `trust_env` pin.
F-C605-2 LOW: confirm that no `rot.Identity` ValueError message can include the key path or key material, or print only the exception type in `ConfigError` for the identity branch.

## What I did NOT do
Did not run the rotator against any estate or read any key file. Did not trace all ValueError texts in the rotation core. Did not run the whole tools suite. Did not edit the PR.
