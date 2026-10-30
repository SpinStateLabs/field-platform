# Design note: the operator key on the ops-console page (Lane 10)

Scope: services/ops-console/src/ops_console/static/console.html and services/ops-console/src/ops_console/api.py on main (read-only; no key typed, kept or printed). PR 288 (C-221) changes the send rule and is open: where it matters I say what main does.

## 1. Objections first (failure conditions)
1. Any script in the page's origin reads sessionStorage: there is no `script-src` policy (Caddyfile:81-84 sets only `frame-ancestors 'none'`), so one DOM injection via an unescaped `innerHTML` (about 25 sites, console.html:909-1327) reads the key and the perimeter secret. The page escapes with `esc()` (:753); one missed site is enough. MEDIUM.
2. The pair is attached to EVERY console fetch on main (`hdrs()` :778-783, used by `api()` :831, the manifest fetch :1195, export :1264, the SSE stream :1347): reads, the long-lived stream, and downloads carry a bearer secret that only three writes need. Larger exposure to any proxy log, any middlebox, any Caddy access log line that prints headers. HIGH (code). PR 288 narrows it; unverified here.
3. `keyTransportOk()` (:764-768) trusts `isSecureContext`, protocol and hostname; an https page behind a TLS-terminating or intercepting middlebox still passes. MEDIUM.
4. The console forwards the human's pair to every downstream service the proxy calls (api.py:631-647), so the key reaches the registry, delegation and ledger-side services in headers. Their logs and error paths become part of the surface. MEDIUM.
5. sessionStorage is per tab but is copied into a tab opened from this one (general knowledge, MEDIUM), and survives reload: a shared screen or a duplicated tab keeps the key until forget or tab close.
Steelman for the current design: sessionStorage not localStorage; key refused outside https/loopback and removed on load (:773-776); input cleared after store (:807); never in a URL; no external scripts or fonts (grep of console.html found none); framing blocked. This is better than most admin pages.

## 2. Channel list (closed / open / unverified)
| # | channel | state | evidence |
|---|---|---|---|
| 1 | URL, query, fragment, `location`, history entries | CLOSED by design: no code writes the key to a URL; sent only as headers | :778-783; the page's own text says so (:263) |
| 2 | `localStorage`, cookies, IndexedDB | CLOSED: only sessionStorage is used | grep: no other store |
| 3 | sessionStorage | OPEN BY DESIGN: readable by any script of the origin until tab close or forget | :769-770, :814-815 |
| 4 | DOM / visible text | CLOSED after store: password input cleared (:807); status line prints the operator id, not the key (:801-803) | :801-807 |
| 5 | DOM during entry | OPEN (LOW): the value sits in a password input until store; autocomplete="off" is not honoured by every password manager (MEDIUM, general knowledge) | :267 |
| 6 | error text and `alert` | CLOSED for the key: `api()` throws the response body, not the request (:835-838); a server echo of the request header is the risk (see 9) | :831-838 |
| 7 | redirects | UNVERIFIED: browsers drop custom headers on a cross-origin redirect, keep them on same-origin; the console has no redirect route that I found. Not probed (needs a browser) | n/a |
| 8 | Referer | CLOSED for the key (not in URL); the page has no `Referrer-Policy`, which affects the shared-secret nowhere because it is a header too | Caddyfile:81-84 |
| 9 | server logs and error bodies | PARTIAL: `ServiceClient.get/post` return `str(exc)` on a transport error (api.py:102,109); httpx exception text names the URL, not the headers (MEDIUM, general knowledge); refusal ledgering takes `request.headers` (api.py:631-647) and masks the claimed id (operator_health.py:73), with no key found in `note_refused` in what I read (LOW: not read to the end) | api.py, operator_health.py |
| 10 | browser extensions | OPEN, unclosable from the page: an extension with page access reads sessionStorage and the password input | general knowledge |
| 11 | browser history/autofill of the form | OPEN (LOW): the key form is not a `<form>` with a submit, so browsers rarely offer to save; still dependent on the browser | :259-269 |
| 12 | bfcache / back-forward | UNVERIFIED | needs a browser |
| 13 | proxies, access logs, SSE stream | OPEN on main (every request carries the pair); closed by PR 288 only if it does what its card says | :778, :1347 |
| 14 | clickjacking | CLOSED: DENY plus `frame-ancestors 'none'` | Caddyfile:81-84 |
| 15 | script injection (XSS) | OPEN in policy: no `script-src`/`default-src` CSP; closed only by `esc()` discipline | Caddyfile:81-84 |
| 16 | key in the clipboard / shell history of the operator | OUT OF SCOPE of the page; the runbook text puts the key in `$(cat ~/.field/operator-key)` (:531), which is correct | :531 |

## 3. Recommended fixes (in order, each testable without a browser except 2)
1. Send the pair only on the guarded writes (PR 288). Test: a read, the stream and an export each carry neither header; the three writes carry both.
2. Add a CSP to the console handle in Caddyfile: `default-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'`. Cost: the page uses inline `<script>` and `onclick=` handlers (:268-269), so this needs a nonce or moving the code to a file; that is a larger change. Fallback: ban only external sources: `default-src 'none'; connect-src 'self'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'`. That still blocks exfiltration to another origin (the real harm of channel 15). MEDIUM confidence it fits the page (not tried).
3. Add `Referrer-Policy: no-referrer` and `Cache-Control: no-store` on the console HTML, so nothing leaks through referrers or caches.
4. A static test that lists every `innerHTML` assignment and requires `esc(` or a constant for each interpolation (closes the class "one missed `esc`").
Do NOT add: encryption of the key in sessionStorage (same origin script can decrypt it).

## What I did NOT do
Did not open the page in a browser (channels 7 and 12). Did not type, create or print any key. Did not read PR 288 (open; main differs). Did not read operator_health.py note_refused in full (channel 9 stays LOW). Did not check the operator's own host. Could not push (note delivered in chat).
