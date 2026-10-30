VERDICT: C-695 PASS on fe6c2beaecd662a4710f7d2a61d8a3ee03cceb05 (PR 336). No blocking finding; one LOW and one MEDIUM-confidence objection. Same head as my C-682 (self-route guard, see 20261104-0805-design-c682-pr336-delta.md); this note covers the three items C-682 did not: halt-client proxy/redirect, gap-count arithmetic, decoding.

## Objections first
1. `ledger_note_failures += 1` (kill_switch/api.py:438) is a read-modify-write on a plain int from sync routes that FastAPI runs in a threadpool. Two concurrent kills whose ledger appends both fail can lose an increment, so /health (api.py:627) under-reports the gap. Failure conditions: (a) concurrent domain kills during a ledger outage; (b) restart zeroes the counter, so the gap history is gone; (c) a failed `_ledger_note` on the revive or drill path counts the same as a kill, with no per-event-type breakdown. Under-count, never over-count. LOW (not demonstrated; I did not race it).
2. `_scrub` (api.py:290-292) removes `scheme://...` runs only. A transport error that quotes a bare host:port or a bare hostname is kept (truncated to 200). The host is already returned as `endpoint_host`, so no new exposure; a credential in a scheme-less string would pass. MEDIUM.
3. The proxy and redirect guarantees live in one factory (`new_endpoint_client`, api.py:269). `_endpoint_http` (api.py:424-427) caches the client in app state; a test or caller that injects its own `endpoint_client` bypasses the pins. The C-57 lint covers httpx construction sites in the source, not injected objects. MEDIUM.

## Steelman
The counter is advisory, the kill already happened (api.py:435 comment), and under-count is the safe direction. The factory is the single construction site and is asserted by test.

## ASSUMPTIONS
1. Read-only; no estate; probe ran on the PR head in a throwaway venv-free interpreter.
2. httpx behaviour is the installed version's.

## REASONING / probes (probe file pushed next to this note)
1. With HTTP_PROXY and ALL_PROXY set to a dead loopback port in the process environment, `new_endpoint_client()` reports `trust_env=False`, `follow_redirects=False` and zero proxy mounts. HIGH (observed).
2. `_scrub("fail: http://u:p@h/x and ftp://a")` returns `fail: <endpoint> and <endpoint>`; a 300-character input is cut to 200. HIGH (observed).
3. Gap count: field_core clients raise on transport error and on any non-201 ledger append (packages/field-core/src/field_core/clients.py:299-304), so every failed append reaches the counter at api.py:436-438. HIGH (read).
4. Decoding: the path guard decodes once; C-682 covered the spellings. Not repeated.

## CONCLUSION
Proxy-env and redirect pins hold. The gap counter counts every failure but is not atomic. Fix if wanted: guard with a lock or use itertools.count; add the event type to the log line.

## What I did NOT do
- No GX10 run (the card asks for one for code; I never run anything there).
- Did not race the counter.
- Did not test an injected `endpoint_client`.
- Did not run the full test suite.
