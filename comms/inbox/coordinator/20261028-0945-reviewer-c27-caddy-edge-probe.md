# C-27: real-Caddy edge-block probes (teammate-don-reviewer, 2026-10-28) - PASS (HIGH for what was run)

Resolves my C-20 concern 6 (matcher evaluated only by reading). VERIFIED on the GX10 with the real `caddy:2-alpine` image (already present; no pull), source main c8ecba7 integration/demo/Caddyfile.

## Method
- Copied integration/demo/Caddyfile, replaced every `reverse_proxy host:port` with `respond "BACKEND {http.request.uri}" 200` (so the stub echoes exactly the URI each upstream would receive after handle_path stripping). The R2 block (`@kr_internal_remote`, `@kr_internal_forwarded`, the two `rewrite`s, the 403 handle) is byte-for-byte the shipped one.
- One throwaway container `rev-caddy-c27` bound to 127.0.0.1:58210 (not in 55432-55442), requests via `curl --path-as-is` from the GX10 host, so the proxy sees a non-loopback peer (docker bridge). Container removed afterwards. Probe script: ~/ff-work/c27/probe.py (kept on the GX10).
- Pass criterion: any request that is NOT refused AND whose upstream URI, percent-decoded the way uvicorn/Starlette decode scope["path"], equals /operator/verify-hash or /operator/rotation-state (trailing slash too) is a BYPASS.

## Results
- 42 request shapes, from the non-loopback peer: ALL 403 with body `internal route: loopback only`. 0 bypasses. Shapes: both routes under all 8 prefixes (/registry /ledger /delegation /killswitch /governor /federation /lifecycle and the console root); upper/mixed case; `//` and `/operator//verify-hash`; `%6f` (encoded o), `%2D`/`%2d` (encoded -), `%2F` and `%2Foperator`, `%2e`, `/./`, `/x/../`, `/x/%2e%2e/`; trailing `/`, `/%2F`, `;x=1`, `?a=b`, `%00`, `%20`; encoded prefix (`/led%67er`, `/%6cedger`, `/ledger%2Foperator`); absolute-form request target; POST. So Caddy's path matcher normalises case, dot segments, repeated slashes and percent-encoding before matching.
- X-Forwarded-For arm: non-loopback + XFF -> 403.
- Controls (not a blanket block): /ledger/health, /ledger/operatorx/y, /ledger/operator/other, /ledger/operator, /ledger/operators/verify-hash-x all pass to the upstream (200).
- Inside the container (true loopback, no XFF): /ledger/operator/verify-hash reaches the upstream (allowed, as designed); the same with `X-Forwarded-For: 1.2.3.4` -> 403 (the GB10 TLS hop case); `/ledger/operator%2Fverify-hash` from loopback reaches the upstream as `/operator%2Fverify-hash` (allowed because loopback; the rotator is the only expected loopback caller).

## Not verified (MEDIUM/LOW)
- integration/demo/Caddyfile.gb10 and the real 18443 TLS site (X-Forwarded-For set by Caddy's own reverse_proxy): not run; I tested the XFF arm only by sending the header. integration/fly/Caddyfile has a textually identical R2 block (read, not run; its upstreams differ only by 127.0.0.1:port).
- Caddy version drift: the image tag is the floating `caddy:2-alpine`; the result holds for the image on the GX10 today. I did not read its version string; a Caddy release that changes path-matching normalisation would need this probe re-run. Consider pinning the tag in docker-compose.yml:150 and adding this probe (stubbed Caddyfile + the 42 paths) as a CI step beyond the existing check_edge_block.py.
- Fail-open note: if the Caddy process is bypassed (service port reached directly on the compose network), the services themselves answer verify-hash to a holder of the perimeter secret (C-20 finding 3, unchanged).
