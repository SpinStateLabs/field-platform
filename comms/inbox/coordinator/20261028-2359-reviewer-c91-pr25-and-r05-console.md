# C-91 (remainder: #25 brand) and R-05 (console.html XSS and secret handling) (teammate-don-reviewer, 2026-10-28) - PASS with LOW (FORCE format)

## Objections first
1. [MEDIUM] Static analysis only: I read every `innerHTML`/`insertAdjacentHTML` site and its helpers, not a browser run. A DOM XSS through an unescaped path I did not follow is still possible; the 62 jsdom tests (C-41) cover the Setup area, not the older panels.
2. [LOW] `esc()` escapes & < > " ' but not the backtick; safe only while no attribute is unquoted. I found none.
3. [LOW] The CI guard added by #25 is an accident guard, not a perimeter proof (below).

## ASSUMPTIONS
- main c6883e5/84d26a4 console.html (1,932 lines) is what ships (HIGH: `git show origin/main:`). `esc` is the only escaping helper (HIGH: grep, 65 uses).

## REASONING
### #25 brand (console.html +87/-45, ci.yml +16)
1. The CSS/markup change touches no route, header or JS binding (PR text; the diff is markup, CSS, data: URI favicons). Favicons are inline `data:` URIs (line 11).
2. New CI step `fly-image-smoke`: `curl -sf` GET `/` through Caddy, asserts text/html, the brand strings, and that the page has no external URL via the regex `(src|href|action)="(https?:)?//|url\((["']?)(https?:)?//|@import|fonts\.(googleapis|gstatic)`. Run against main's console.html: 0 hits (PASS).
3. LOW, PROVEN (regex tested on six samples): the guard misses single-quoted and unquoted attributes (`<script src='https://evil.example/x.js'>`, `<link href=https://...>`, `<img src=//evil.example/p.png>`), `<meta http-equiv=refresh content='0;url=https://...'>` and JavaScript `fetch('https://...')`; it does catch a double-quoted `href="https://ok.example"` (so it also blocks legitimate external links). Air-gap by construction depends on review, not on this step.

### R-05 console.html XSS and secret handling
4. Sinks: 0 `eval`, `new Function`, `document.write`, `javascript:`, `postMessage`, `localStorage`, `document.cookie`, `console.log/debug/info`. 31 `innerHTML` and 1 `insertAdjacentHTML` (line 1038). Every server-derived value reaching them goes through `esc()` or a helper that does: `kv` (line 1162, escapes key and value), `tokenRows` (955), `unavail` (898), `fillSelect` (escapes value and label, line 910), `domainTally` (1115), `modelsCell` (992), `actionButtons` (939: `const id = esc(a.agent_id)` used in `data-id="${id}"` with `this.dataset.id`, not string-built JS), `togglePayload` (1038: `esc(JSON.stringify(e, null, 2))`). The 38 interpolations in 905-1195 not directly wrapped in `esc(` are constants, counts or pre-escaped variables (checked one by one).
5. `table(headers, rows)` (line 894) interpolates `headers` RAW (`<th>${h}</th>`). All call sites I read pass literal arrays; INFO: it becomes an XSS sink the day a call passes data. Escape it.
6. Setup block (~1380-1900): 0 `innerHTML`; every node is `mk(tag, cls, text)` -> `textContent` (66 call sites); its `kv` (line 1409) builds DOM nodes.
7. URL building: `enc(id)` for path segments (line 1164), `URLSearchParams` for the export query (1262); `a.href` assignments (lines 1271, 1560, 1563, 1703, 1800) are blob URLs or `#setup/<constant slug>`. The one `target="_blank"` (1294) has `rel="noopener"`. The export filename from `Content-Disposition` is used only as `a.download` (the browser sanitises it).
8. Secrets: `x-field-auth` is in `sessionStorage` (line 826) and, with the operator pair (814-815), added by `hdrs()` to every request; none is placed in a URL (`secret=`, `?secret` grep: 0) or logged. All three are readable by any script in the origin, which is why F-C91-1 (no CSP / frame protection) matters; unchanged here.
9. Confirms C-91 finding 1: still no CSP/X-Frame-Options/nosniff; inline `onclick` handlers (about 10 sites) block a strict `script-src 'self'` without a refactor.

## CONCLUSION
PASS (HIGH on the sink inventory, MEDIUM overall because static). #25: PASS with the LOW regex gap; C-91 is now complete (#25 reviewed). R-05: no DOM XSS found; one INFO (`table()` headers unescaped) and the carried missing-headers LOW. Fixes if wanted: escape `table()` headers; extend the CI check to quote-free attributes, `meta refresh` and `fetch('http`; add the Caddy frame and CSP headers (F-C91-1). Rows added to the register: F-C91-4 (now reviewed, LOW regex gap), F-C105-1 (INFO `table()` headers).
