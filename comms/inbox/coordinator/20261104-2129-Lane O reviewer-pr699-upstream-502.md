# LANE O review: PR 699 (force-gateway S5-21: real_upstream transport error or non-JSON body is a named 502) @ efcf22bb

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Head efcf22bb, 1 commit, 0 behind origin/main, merge clean, Don Hagell numeric noreply. api.py +19/-11 (re-indents the `httpx.post(...)` call into a `try`), tests +82, docs/ENVIRONMENT.md 20 lines (anchor refresh; `python tools/environment_anchors.py --check` at this head: 0 wrong anchor row(s)).

Objections first: (1) the PR re-indents the whole upstream request (URL, body, headers, timeout) into the new `try`, and the new tests replace `httpx.post` with a fake that ignores every argument; nothing in the force-gateway suite pins what is sent (measured below). A change to the body, the `anthropic-version` header or the 120 s timeout in that block goes unnoticed. (2) The exception class is named in the detail (`ConnectError`, `ReadTimeout`); that is a small information disclosure about the transport, chosen on purpose, and fine, but the tests pin only two classes. (3) `scrub_secret` on a JSON answer is pinned only by older tests (one mutant killed by older tests only), not by this file.

Baseline (unmutated, measured): force-gateway suite 457 passed. Survivor check ran the whole suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 a transport error is a 502 naming the class only, never the text, URL or key | 8 | 5 | 0 | 3 |
| B2 a non-JSON body is a 502 keeping the upstream status in the detail | 6 | 5 | 1 | 0 |
| B3 a JSON body passes through with its status and scrubbed; the request is unchanged | 6 | 1 | 2 | 3 |
| Total | 20 | 11 | 3 | 6 |

Totals counted from the table: 20 = 11+3+6; no invalid, no noapply.

Survivors, 6 = 4 real gaps + 2 equivalent:
Real gaps:
- B1 `except httpx.TransportError` instead of `httpx.HTTPError`: `DecodingError` and `TooManyRedirects` (a `RequestError` but not a `TransportError`) would no longer be a named 502; the tests raise only ConnectError and ReadTimeout.
- B3 `timeout=12.0` instead of `120.0`: unpinned.
- B3 `anthropic-version` hard-coded: forwarding of the caller's version header is unpinned.
- B3 `json={}` instead of the body: the request body is unpinned.
Equivalent (for the response, which is what the claim covers):
- B1 `from exc` instead of `from None`: changes only the exception chain; the HTTP detail is identical. Note the chain would carry the exception text to server logs.
- B1 `except Exception` in place of `except httpx.HTTPError`: differs only for non-httpx exceptions, which no test raises.

Conditions: capture the arguments in `fake_post` and assert URL, body, headers and timeout; add a `DecodingError` case. Confidence: HIGH on counts, MEDIUM on classification. Token/cost: I do not know.
