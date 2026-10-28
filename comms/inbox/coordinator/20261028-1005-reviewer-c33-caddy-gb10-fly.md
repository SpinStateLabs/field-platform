# C-33: same real-Caddy probe on Caddyfile.gb10 and the Fly Caddyfile (teammate-don-reviewer, 2026-10-28) - PASS (HIGH for what was run)

VERIFIED on the GX10, real caddy v2.11.4 (image caddy:2-alpine as present today; version read with `caddy version`). Source: main c8ecba7 (integration/demo/Caddyfile.gb10, integration/demo/Caddyfile as its Caddyfile.routes, integration/fly/Caddyfile). Method as C-27: every `reverse_proxy host:port` in the route files replaced by `respond "BACKEND {http.request.uri}" 200`; the GB10 TLS site (`tls internal`, `reverse_proxy 127.0.0.1:8080`, which sets X-Forwarded-For) kept as shipped. Probe: the same 42 request shapes as C-27 (+1 XFF check) from ~/ff-work/c33/probe2.py. Ports 58301/58303/58213 on 127.0.0.1 (not 55432-55442); both containers removed.

## Results
| Target | Client | Shapes | Outcome |
|---|---|---|---|
| GB10 TLS listener (18443 analogue, https://localhost:8443 in the container) | host, non-loopback | 43 | 43x 403, 0 bypass |
| GB10 :8080 site (18080 analogue) | host, non-loopback | 43 | 43x 403, 0 bypass |
| Fly Caddyfile (stubbed upstreams 127.0.0.1:80xx) | host, non-loopback | 43 | 43x 403, 0 bypass |
| GB10 TLS listener | LOOPBACK client inside the container (the dangerous case: the TLS hop reaches :8080 from 127.0.0.1) | /ledger, /registry, console-root forms of verify-hash and rotation-state, and `/ledger/operator%2Fverify-hash` | all 403 (the proxy hop's X-Forwarded-For trips `@kr_internal_forwarded`); /ledger/health still 200 |
| GB10 :8080 | loopback inside the container | /ledger/operator/rotation-state | reaches the upstream (allowed by design; this is the rotator path) |
| Fly | loopback inside the container | /ledger/operator/verify-hash | reaches the upstream (allowed); with `X-Forwarded-For: 10.0.0.1` -> 403 |
Controls (non-blanket): /ledger/health and /ledger/operatorx/y return the upstream on the TLS site.

## Findings
1. PASS: no bypass on any of the three configurations; the GB10 TLS hop is refused even from a loopback client, which was the untested claim in C-27.
2. LOW (test-method trap, not a product defect): the GB10 TLS site matches on host name (10.0.0.62, gx10, localhost). A request with Host 127.0.0.1 matches no site and gets an EMPTY 200. My first run (host 127.0.0.1) reported 43x 200 for that reason and was invalid; I re-ran with Host localhost. Anyone writing a probe must use a matching host name, and an empty 200 must not be read as "proxied".
3. LOW (carried from C-27): floating `caddy:2-alpine` tag (integration/demo/docker-compose.yml:150); v2.11.4 behaves as above today. Pin the tag and add this stubbed probe (static Caddyfiles, no secrets) as a CI job so a Caddy normalisation change cannot reopen the route.

## Not verified
The real GB10 listeners 18080/18443 and the real Fly edge (Fly's proxy and its X-Forwarded-For handling) were not touched; only Caddy's behaviour on the shipped Caddyfiles was. Upstream services were stubs, so "the service answers" was not exercised here (see C-20 finding 3).
