VERDICT: PASS WITH CONDITIONS on fe6c2beaecd662a4710f7d2a61d8a3ee03cceb05 (the head the card names); the PR head is now 08463bd (six commits later), reviewed as a delta below

C-695 delta review of PR 336 (kill-switch halt client), Lane 7. Cherry-picked the six commits up to fe6c2be onto CURRENT main 5777030 (the PR is cut on b929f12): clean. Then all twelve commits up to 08463bd: clean. Author and committer Don Hagell on every fetched ref. A Lane 10 note on fe6c2be exists (20261104-1530, PASS); this report is independent and adds what I measured.

OBJECTIONS FIRST
1. At the card's SHA a 302 from the halt endpoint is reported as outcome "called", a success-looking result for a signal the agent never acted on.
2. The self-route guard now decodes the path, but it still matches by shape on any host, so it keeps refusing real agent endpoints (my C-525 F-C525-2, a decision never taken).
3. A guard on a decoded string is only as good as its agreement with the router; I tested the edges rather than the listed cases.
4. The gap counter's arithmetic and its lock rest on a spy, not on a race that fails.

ASSUMPTIONS
A1 httpx 0.28.1, Starlette TestClient routing. A2 Real local listeners for the redirect and proxy probes (no estate), made-up ids only, NO_PROXY cleared. A3 The self-route check is judged against the repo's own app routes, as the PR's test does.

RESULTS
1. Suites [HIGH, run]: kill-switch 217 passed at fe6c2be, 234 at 08463bd. Whole tools suite on the fe6c2be tree: 3133 passed, 6 skipped, 0 failed (11 min 20 s); the removed line in tools/tests/http_env_proxy_allowlist.txt is consistent with the code (that suite is green). Tools suite not re-run on 08463bd.
2. Halt client, real listeners [HIGH, probe], through the real new_endpoint_client() factory:
   - proxy: with HTTP_PROXY set, 0 proxy hits (a plain httpx control: 1). trust_env=False is in place (api.py:267-269); C-525 F-C525-4 CLOSED.
   - redirect: a 302 to a second listener is not followed (0 hits on it). At fe6c2be the result is outcome "called", http_status 302. At 08463bd it is outcome "failed", reason "http_redirect" (api.py:539-542). Severity LOW-MEDIUM at fe6c2be (a redirect looks like a delivered halt). Land the head, not fe6c2be alone.
   - 500 stays "failed http_error"; 200 "called" on both.
3. Decoding edge cases [HIGH, 31 forms through _is_self_endpoint]: refused or self: encoded /%6Bill and /%6bill, double-encoded, encoded dot segments, %2F inside a segment, an encoded "?", repeated slashes, leading "//", upper case and mixed case, a ";" suffix, encoded health, "%00", a newline, a backslash. Not self (correct, the router does not map them): "/halt", "/healthz", "/live", "/metrics", "/doc", "/redocs", overlong UTF-8 "%C0%AE", full-width solidus, "/kill%20/x". I found no spelling that reaches a self route but is judged foreign; C-525 F-C525-1 CLOSED for the forms I tried [MEDIUM: bounded by 31 forms, not a proof; uvicorn's decode not run].
4. F-C525-2 (over-block) STILL OPEN [HIGH, probe]: "/kill", "/KILL/x" (now also by case folding) and any path ending in a shape are judged self on any host; no host/port comparison was added. An agent whose own halt endpoint path ends in /kill never receives the signal (skipped, ledgered). Decision for Don; a host:port comparison removes the trade-off.
5. Gap counter arithmetic [HIGH, probe]: ledger forced to fail; one kill = 2 notes (endpoint outcome note + kill.agent note); a repeat kill of the same agent adds 2 more; 59 concurrent kills added 118 = 59 x 2 (three runs each, at fe6c2be with a plain int and at 08463bd with the lock; no lost increment seen at either); a domain kill of 60 already-killed agents added 121 = 60 x 2 + 1 domain note. So the unit is notes written, per process, reset on restart (README text at 1faf2ab states notes not actions). The race on the plain int at fe6c2be is not demonstrated (interpreter lock) but is closed at 08463bd by _GapCounter (api.py:249-260). The log line carries the event type and exception type only (a mutant that logs str(exc) is killed).
6. Hand mutants [HIGH, run on the 08463bd tree]: 25; 24 killed, 1 survives. Killed: no decode, "%" left, backslash, control char, DEL, ".." and "." segments, no slash collapse, no case fold, "untrusted path means not self", the four new shapes (/operator/, /docs/, /redoc, /openapi.json), trust_env True, follow_redirects True, counter not incremented, message logged, /health field dropped, 3xx as called, 3xx as http_error, counter lock removed, counter adds 2, _scrub off. Survivor: casefold replaced by lower (api.py:322); only differs for exotic Unicode (e.g. the Kelvin sign), where over-blocking is the safe direction: equivalent in effect, LOW.
7. F-C695-1 (LOW, carried from Lane 10): an injected endpoint_client bypasses the factory's pins; test-only injection, the lint covers source construction sites, not injected objects.
8. F-C695-2 (LOW, carried): _scrub removes scheme://... runs only; a scheme-less host:port in an exception text would pass (the host is already returned as endpoint_host).

CONCLUSION: the decoding guard, the no-proxy and no-redirect pins and the gap counter are correct and strongly killed (24/25). PASS WITH CONDITIONS on fe6c2be and land the head 08463bd, which is the version with the 3xx = failed rule. Conditions: (a) merge the head, not fe6c2be; (b) Don decides F-C525-2 (host:port comparison); (c) optionally pin casefold with one Unicode case.

What I did NOT do: no GX10; no CI (7/7 not verified by me); no uvicorn run; no end-to-end forward of an encoded halt signal; no tools suite on 08463bd; no auth-on run; the cli.py, drill and domain-kill code beyond the suite; no read of the PR text.
