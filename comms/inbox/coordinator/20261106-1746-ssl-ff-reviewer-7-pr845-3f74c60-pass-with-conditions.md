# Review PR 845 (G20: GB10 TLS phase 2 as an env switch, FIELD_GB10_PLAIN_BIND, default unchanged) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `3f74c600c074e824ba3c7170fb934c06b26c055c`.
Conditions: C1 (verification, HIGH importance): nobody has run real `docker compose config` on the nested expression `${FIELD_GB10_PLAIN_BIND:+${FIELD_GB10_PLAIN_BIND}:}18080:8080`. I cannot either (no docker on this machine); the repository's tests model the substitution with a string replace, so they pin the TEXT, not compose's behaviour. Before the variable is set on the GB10, run `docker compose $F config` (variable unset, then blank, then `127.0.0.1`) and read the proxy `published` and `host_ip` values; the CI gb10 topology job runs the UNSET case through real compose (per the PR; I read the job at ci.yml:410-500 but did not run it), the SET case is covered by nothing automated. C2: CI on the head. No code defect found.

## Objections first
1. The semantics hinge on Compose: nested interpolation inside the replacement of `${VAR:+...}`. The Compose specification documents nested interpolation, and `:+` yields the replacement when the variable is set and non-empty, so I expect `127.0.0.1:` and an empty string; this is training-data knowledge (MEDIUM), not something I observed.
2. The failure mode if it is wrong is not silent exposure: an unset variable that resolves wrongly gives an invalid port string (compose refuses to start the proxy, fail closed) or the Phase 1 default; a value written wrong (an IPv6 literal `::1` without brackets, a hostname) makes compose refuse. The risk of the wrong BIND being a LAN address is the operator's choice, and the runbook says 127.0.0.1.
3. The switch does not itself prove the exit criterion (18080 loopback only): the runbook names the check (`docker compose port`, a loopback curl, a failing LAN call); the CI step that pins phase 1 ("18080 still answers on the LAN address") stays green because the default is unchanged, and is the coordinator's to flip.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5; .github/: 0 files (as the PR says; the CI flip is not in this PR). 4 files: docker-compose.gb10.yml (+4/-2), test_gb10_caddy_tls.py (+31/-5), test_compose_static_pins.py (+1/-1), the runbook (+17/-8). Based on main e125a878.
- The single functional change: `ports: !override ["${FIELD_GB10_PLAIN_BIND:+${FIELD_GB10_PLAIN_BIND}:}18080:8080", "18443:8443"]`. `!override` stays (a merge would also publish the base `8080:8080`, which the base file declares at docker-compose.yml:178); unset or blank gives `18080:8080` exactly as on main; `127.0.0.1` gives `127.0.0.1:18080:8080`; 18443 unchanged on all interfaces. No address is written in the repository (the test also asserts no literal IPv4 is bound to 18080 in the comment-stripped file).
- Runbook phase 2 section read in full: entry criteria (every step 4 caller on 18443, including the two renewal tasks, row T5), the switch, the exit criterion, the check commands and the rollback (unset or blank the variable, recreate the proxy). It states plainly that merging changes nothing on an estate until the variable is set.
- Tests on the exact head (Windows): test_gb10_caddy_tls.py + test_compose_static_pins.py 688 passed (the PR cites 725 including the docs-cite and deploy-docs tests, not re-run by me).

## Mutants (15 on the proxy ports line in docker-compose.gb10.yml; run against test_gb10_caddy_tls, test_compose_static_pins and test_topology_lint; counted from the table)
| # | mutation | result |
|---|---|---|
| P1 | `:-` instead of `:+` | KILLED |
| P2 | default loopback (`:-127.0.0.1`) | KILLED |
| P3 | missing colon after the value | KILLED |
| P4 | bare variable | KILLED |
| P5 | literal loopback | KILLED |
| P6 | typo in the condition's variable name | KILLED |
| P7 | typo in the value's variable name | KILLED |
| P8 | variable applied to 18443 | KILLED |
| P9 | variable ignored (plain 18080) | KILLED |
| P10 | 18080 removed | KILLED |
| P11 | 18443 on loopback | KILLED |
| P12 | `!override` dropped | KILLED |
| P13 | container port wrong | KILLED |
| P14 | host port wrong | KILLED |
| P15 | space inserted in the replacement | KILLED |
Totals: 15 mutants, 15 killed, 0 survived. Caveat on P1: the test kills `:-` because the exact string is pinned, not because the model understands `:-` versus `:+`; the real semantics are compose's (C1).

## Optional LOWs (new PR)
A CI step that runs `docker compose config` with the variable set to 127.0.0.1 and asserts `host_ip`; a runbook line that a bracketed IPv6 literal is required if ever used; the exit-criterion check as a script.

## Not verified
Real compose resolution (set or unset); CI/GX10; the PR's docs-cite and deploy-docs runs; behaviour on an estate.
