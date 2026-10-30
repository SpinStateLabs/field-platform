# C-515: review of PR 316 (console CSP headers), Lane 10

Reviewed: PR 316 head 9b1fb08 (`fix/console-csp-headers-c456`; integration/demo/Caddyfile, integration/fly/Caddyfile, three test files). This implements the fallback policy from my note 20261101-0210 (section 3, item 2). Probe: 20261102-2200-design-c515-csp-browser-probe.js (headless Chromium from the container, a stub server serving the PR's console.html under the policy under test; `NODE_PATH=$(npm root -g) node run.js "<policy>"`).

VERDICT: PASS WITH ONE CONDITION on 9b1fb08. The policy does what the card asks and breaks nothing I could find; the stated closure of the key-exfiltration channel is overstated because the policy has no `form-action`. Confidence HIGH (browser run).

## ASSUMPTIONS
1. A real Chromium run on the unmodified console.html with stub API responses is a fair test of "does not break the inline script, SSE or export".
2. `caddy` is not installed here, so `caddy validate` was NOT run on either file.

## Objections first (what could be wrong with the claim)
1. CSP does not cover every exfiltration route: `default-src` does not fall back for `form-action`, `base-uri` or navigation. An injected script (allowed by `script-src 'unsafe-inline'`) that reads the key from sessionStorage can POST it with a form to another origin, or navigate to one with it in the URL. Probe: under the PR's exact policy a form POST to another origin WAS ATTEMPTED (request observed); fetch and image requests to another origin were BLOCKED. HIGH (run).
2. `script-src 'unsafe-inline'` stays, so the first step of an injection is unaffected (the PR says so; honest).
3. A policy header on the console route only: other routes (API through the proxy) are not console pages, so no gap there; the SSE stream's `Cache-Control` is replaced by Caddy's (`no-store`), which is fine for a stream.
4. Navigation (`location = ...`) cannot be blocked by CSP at all (general knowledge, MEDIUM; `navigate-to` was dropped from browsers). The residual is real even with `form-action`.
Steelman: the policy blocks the cheap exfiltration channels (fetch, image, WebSocket, scripts and styles from elsewhere, framing) and costs nothing; most injections use those.

## Results (the card's questions)
- Inline script and styles work: the page loaded under the policy, 33 buttons, the page's own functions defined; the only page error (`TypeError ... null to object`) is identical with NO policy (my stub's JSON shape), so it is not caused by the CSP. Violations logged were only my own probes. HIGH.
- Export: `exportEvents('csv')` produced a download named from the stub's Content-Disposition under the policy (Blob URL download is not blocked). Stream: `fetch('/api/stream')` returned 200 under the policy. HIGH.
- `Referrer-Policy: no-referrer` and `Cache-Control: no-store` are in the console `handle` of both Caddyfiles with the same CSP value (read from the diff; the equality is pinned by test_console_csp_c456.py). Not seen on a live response (no caddy). MEDIUM.
- Nothing external is loaded: grep of console.html found no `src=`/`href=` to another origin, no `@import`, no font URL; only a `data:` icon (covered by `img-src data:`). HIGH.
- Tests: 104 passed in the three changed test files (HIGH, run). My own six mutants, each turned red: drop Referrer-Policy (fly), drop `no-store` (demo), the two files' CSP differing (`img-src data: https:` in fly), adding `form-action 'none'` to both (red on purpose: the tests pin the policy exactly), changing the Referrer-Policy value, removing a header from one file. 6 of 6 killed. The builder's 26 stated mutants: not re-run one by one.
- Whole tools suite: NOT run to green here (no full workspace install in this container); the three files above were.

## Findings
F-C515-1 MEDIUM-LOW: add `form-action 'none'; base-uri 'none'` to the policy in both files. Probe: under the policy plus those two directives the form POST was blocked, export and stream still worked, no new page error (run). The console's eight forms are handled in script and none relies on a native submit (8 `preventDefault` calls for 8 `<form>`; not read case by case: MEDIUM). Cost: update the exact-value pin and the two mutant tables in test_console_csp_c456.py (the PR's own mutants 115-116 treat `form-action *` and `'self'` as regressions: they would need to flip). Also reword the Caddyfile comment and the PR text from "a DOM injection could otherwise send the key out" to what the policy blocks (fetch, image, WebSocket, framing, other-origin script and style) and what it does not (inline script, navigation).
F-C515-2 LOW: `Permissions-Policy` and `X-Content-Type-Options` (the latter is already on the console handle per the existing header block) are not part of this card; mention only.

## What I did NOT do
Did not run `caddy validate` (no binary) or request a live response; the header placement is from the diff. Did not run the builder's 26 mutants individually. Did not run the whole tools suite. Did not test every console form's submit path. Did not test other browsers (Firefox and Safari differ on some CSP details; not run). Did not edit the PR.
