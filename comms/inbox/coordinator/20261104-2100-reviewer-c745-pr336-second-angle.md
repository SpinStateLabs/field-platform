VERDICT: PASS WITH CONDITIONS on fe6c2beaecd662a4710f7d2a61d8a3ee03cceb05 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's new test file ran: 57 passed; the rest of the kill-switch suite was not run)

Second angle after C-682 (Lane 14). Head matches the card. Six commits on main; author and committer of all are the no-reply identity. Files: kill_switch/api.py (+48 -8 net), README, docs/ENVIRONMENT.md (1 line), tests/test_self_guard_c574.py (+192), tools/tests/http_env_proxy_allowlist.txt (-1: the site is migrated).

OBJECTIONS FIRST
1. A redirect answered by a halt endpoint is recorded as SUCCESS, PROVEN: the endpoint result treats only status 400 and above as a failure (api.py ~line 518, `status >= 400`), so 301, 302, 307, 308 and 399 all produce outcome "called". The client never follows a redirect (also proven below), so the signal did not reach the final target; a gateway or login page that redirects every request makes every halt look delivered. Not introduced by this PR (the rule predates it) but it is exactly the "halt client redirect behaviour" the card asks about. MEDIUM-LOW.
2. The ledger-gap counter counts FAILED NOTES, not failed actions. One kill with the ledger down raised the count by 2 (the kill writes two records); five kills raised it to 10 in my probe. The name "ledger_note_failures" says notes, the README text and commit message say "the counter counts failed records", so the arithmetic is consistent, but an operator reading "2" after one kill may think two kills failed. LOW.
3. The counter is per process and resets on restart; a multi-worker deployment has one counter per worker and /health shows whichever worker answers. It is exposed on the open /health route (a count, no text). LOW.
4. Increment safety: the counter is incremented with a bare `+= 1` from request threads. In my probe 300 concurrent kills each failing 2 notes counted exactly 600 (no lost update), but that is the interpreter lock's behaviour, not a guarantee. LOW.
5. One mutant survives: removing the explicit follow_redirects=False from the client constructor changes nothing the tests see (the library's default is already no redirects). The comment calls the setting "load-bearing, not decoration"; no test would notice if the library default changed. LOW.

ASSUMPTIONS
A1 "Gap" = a failed append of a ledger record inside the act-first path (api.py ~lines 431-441). A2 Empty ledger = a fresh app with no failures; single = one failed kill; wrapped = a very large counter (Python integers do not wrap). A3 The halt client probe used real local listeners for a proxy and a target; the injected fake client stood in for the 3xx status probe.

REASONING
1. Counter arithmetic: fresh app: 0 on /health; one kill with the ledger raising: HTTP 200 for the kill (act first), counter 2; four more kills: counter 10; 300 concurrent kills x 2 notes: 600. HIGH. "Wrapped": Python ints are unbounded and the JSON number is exact to 2^53; no wrap. HIGH.
2. Halt client: with every proxy variable pointing at a local listener, the real client (new_endpoint_client) reached the target directly (target 1 hit, proxy 0 hits); a 302 from the target was returned as 302 and not followed (target 2 hits, nothing else); trust_env is False and follow_redirects False on the client object. HIGH.
3. Status handling: a fake endpoint answering 200, 204, 301, 302, 307, 308, 399: outcome "called"; 400, 404, 500: outcome "failed", reason http_error. HIGH.
4. Path guard (_canonical_path and _is_self_endpoint): decoded once, a remaining percent, a backslash, a control character or a dot segment is refused as untrustworthy and treated as self (fail closed); case-folded; new shapes /operator/, /docs/, /redoc, /openapi.json. HIGH by reading and by mutants.
5. Mutants (each alone, restored, nothing committed): trust_env pin removed -> 1 failed; counter not incremented -> 2; counter incremented by 2 -> 2; health field removed -> 2; log removed -> 1; log carrying the exception message -> 1; decode twice -> 1; no decode -> 6; percent-after-decode allowed -> 1; dot segments allowed -> 4; backslash allowed -> 2; control characters allowed -> 4; case folding removed -> 6; untrusted path treated as not self -> 11; each of /operator/, /docs/, /openapi.json removed -> 4, 4, 2. follow_redirects pin removed -> 57 passed (survives, objection 5). HIGH.
6. Allowlist: the line for the migrated client is removed from tools/tests/http_env_proxy_allowlist.txt, which the lint requires once the site is fixed. HIGH (read; the lint test was not run).
7. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The decode, refusal and counter behaviours are pinned by red tests and the client ignores the proxy environment and redirects. The result classification treats a redirect as delivery. Conditions, none blocking:
- C1 F-C745-1: classify 3xx as failed (reason http_redirect) and add a test with a 302.
- C2 F-C745-2: document "notes" versus "actions" next to the counter, or count per action.
- C3 F-C745-5: pin follow_redirects=False with a test against a real redirect (the probe above) so a library default change is caught.

FINDINGS
F-C745-1 MEDIUM-LOW, services/kill-switch/src/kill_switch/api.py:517-526 (3xx counted as "called"). PROVEN.
F-C745-2 LOW, api.py:431-441 (counter counts notes; per-process; reset on restart). PROVEN.
F-C745-3 LOW, api.py:438 (unsynchronised increment). MEDIUM.
F-C745-4 LOW, api.py:269 versus tests/test_self_guard_c574.py (follow_redirects pin unpinned; survives). PROVEN.

NOT VERIFIED: the rest of the kill-switch suite and the lint test; CI; multi-worker behaviour; whether the registry-side kill happens before the endpoint call in every path (read only for the paths probed).
