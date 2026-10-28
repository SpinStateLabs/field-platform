# C-100: PR 67 fix/console-frame-headers at 079f587 (C-96, my C-91 clickjacking finding) (teammate-don-reviewer, 2026-10-29) - CONDITIONS (FORCE format)

## Objections first
1. [MEDIUM, PROVEN, MERGE BLOCKER] The PR breaks an existing test. On the exact head, `tools/tests/test_gb10_caddy_tls.py::test_base_compose_and_base_caddyfile_are_unchanged_plain_http_8080` FAILS: `AssertionError: unexpected directive in the base :8080 site: 'header {'` (test_gb10_caddy_tls.py:205, the `_route_table` parser accepts only `handle`, `handle_path`, `reverse_proxy` and `}`). The same two test files (test_kr_edge_block_r2.py + test_gb10_caddy_tls.py) give 71 passed on main a8bd47c and 1 failed / 70 passed on 079f587. The CI tools job will go red. The new test file does not touch that parser.
2. [LOW] `frame-ancestors 'none'` is the ONLY CSP directive set: it stops framing, it does not limit scripts (the inline `onclick` handlers and 31 `innerHTML` sites still run without a script-src policy). This closes clickjacking only, as the PR says; it is not XSS hardening.
3. [LOW] If an upstream ever sets its own X-Frame-Options, the client receives both (probe below). The console sets none today.
4. [INFO] The headers cover the console catch-all only; the service prefixes (/ledger, /registry, ...) return JSON and carry none (by design).

## ASSUMPTIONS
- main a8bd47c is the base; the PR's 3 files are the whole change (HIGH). Real Caddy v2.11.4 (caddy:2-alpine on the GX10) behaves like the Caddy the estates run (MEDIUM: same floating tag, F-C27-1).

## REASONING
1. Diff: both Caddyfiles (integration/demo, integration/fly) get a `header { X-Frame-Options DENY; Content-Security-Policy "frame-ancestors 'none'"; X-Content-Type-Options nosniff }` block inside the console catch-all `handle`, before `reverse_proxy`; new tools/tests/test_console_frame_headers.py (82 lines). One commit, author and committer Don Hagell <13129187+dhagell@users.noreply.github.com>, 1 commit on a8bd47c.
2. New tests: 11 passed. File mutants on the real Caddyfiles (4): fly DENY -> SAMEORIGIN, fly CSP removed, demo nosniff removed, demo CSP -> 'self': each turns 3 tests red (all killed).
3. REAL CADDY PROBE (v2.11.4, real `reverse_proxy` to a live Python upstream on 127.0.0.1:8011 inside the same network namespace; fly Caddyfile as shipped; ports 58411, not in 55432-55442; containers removed afterwards): GET `/`, `/index.html`, `/api/x` -> 200 with all three headers (CSP `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`), each exactly once. Also seen on 502 responses with the upstream down, and on both the fly and demo Caddyfiles (demo with `--add-host console:127.0.0.1`). `/ledger/health` (service prefix): no frame headers. The R2 edge block is intact: `/ledger/operator/verify-hash` -> 403.
4. Probe, upstream sets `X-Frame-Options: SAMEORIGIN` itself: the client sees `X-Frame-Options: DENY` AND `X-Frame-Options: SAMEORIGIN` (both). Browsers apply the modern `frame-ancestors 'none'` regardless, so framing stays blocked; the duplicate XFO is only untidy.
5. The GB10 TLS listeners import the base route map (C-33), so both inherit the headers (the PR's own test asserts the import; I did not re-probe the TLS hop with the headers).

## CONCLUSION
CONDITIONS (HIGH). The behaviour is correct on real Caddy and the new tests are sound, but the PR as pushed turns CI red. Condition 1: update the route-table parser in test_gb10_caddy_tls.py (`_route_table`) to accept the `header { ... }` block (and its three directive lines) inside the console handle; re-run tools/tests/test_gb10_caddy_tls.py and test_kr_edge_block_r2.py on the exact head; I will re-review that head. F-C91-1 stays open until merged. NOT verified: the TLS hop with headers; a browser actually refusing to frame (no browser run).
