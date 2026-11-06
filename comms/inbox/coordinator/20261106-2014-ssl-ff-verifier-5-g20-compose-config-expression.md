# GX10 verifier ssl-ff-verifier-5: V-G20-compose-config-expression (reviewer-7 C1 on PR 845)

Verdict: **PASS.** Real `docker compose config` resolves the G20 expression correctly in all three cases. HIGH.

Run: GX10, Docker Compose v5.0.2, tree = main 250154d3f87181585227f279821efb6c5dcbc84e (includes G20 / ccab2379; checked-out HEAD == full SHA verified), `docker compose -p ver5g20 -f integration/demo/docker-compose.yml -f integration/demo/docker-compose.gb10.yml config` (config only; nothing started, no estate access). Source line (docker-compose.gb10.yml:208): `ports: !override ["${FIELD_GB10_PLAIN_BIND:+${FIELD_GB10_PLAIN_BIND}:}18080:8080", "18443:8443"]`.
The only other required variable the file demanded was FIELD_GB10_LAN_IP (a `:?` guard); I supplied the documentation address 192.0.2.1 (RFC 5737 TEST-NET-1), not an estate address. The gb10.required.yml overlay was not layered.

Resolved proxy ports (rc=0 each):
| FIELD_GB10_PLAIN_BIND | 18080 line | 18443 line |
|---|---|---|
| unset | target 8080, published "18080", no host_ip (all interfaces) | target 8443, published "18443", no host_ip |
| blank (empty string) | target 8080, published "18080", no host_ip (all interfaces) | target 8443, published "18443", no host_ip |
| 127.0.0.1 | host_ip 127.0.0.1, target 8080, published "18080" | target 8443, published "18443", no host_ip |

Checks: unset and blank produce the identical phase-1 result (`:+` treats blank as unset), exactly "18080:8080" on all interfaces; 127.0.0.1 binds only 18080 to loopback; 18443 is unchanged in all three. `grep -c host_ip` on the three outputs: 0, 0, 1. `!override` replaced the base list (one 18080 and one 18443 entry each, no duplicates). Caveat: tested on Compose v5.0.2 only; CI/estate compose version may differ (MEDIUM for other versions).
