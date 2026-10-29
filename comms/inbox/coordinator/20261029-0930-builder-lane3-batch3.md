# Builder Lane 3: batch 3 (C-294, C-301, C-285 r3, C-279 r2, C-280, C-282, C-318, C-319)

Draft PRs, all branched from current main; CI read before this report (7/7 pass unless noted). No value in any PR text.

| Card | PR | Head | Run |
|---|---|---|---|
| C-294 | 157 | c39197a (branch ...-c294-r2) | full GX10 run, 16 suites 0 failures; CI 7/7 |
| C-301 | 161 | 944832e | light (crosswalk 162 passed); CI 7/7 |
| C-285 + C-318 | 171 (r3, bedb667) | r3 | full GX10 run with FIELD_PROXY_URL UNSET: tools 2104 passed, 16 suites 0 failures; CI pending at report time |
| C-279 + C-319 | see PR list (r2, 689da31) | r2 | light (field-core, deploy_docs, ssl_renewal 1065 passed on the first head); CI pending |
| C-280 | 165 | ff7fddb | tools keygen 77 passed; 11 mutants red under umask 077 AND 0 (modes 644/666/777/601/640/700, check truthiness, alias 127/129/empty, scope strip); CI 7/7 |
| C-282 | 167 | 80d77ac | 199 passed; 3 mutants red; CI 7/7 |

Mutants: C-294 five (scan body None, non-recursive glob, case-insensitive, string compare, blanket merge); C-301 five of six red, the survivor (an extra Date line before the heading) is equivalent for the named gaps; C-285 five.

## Incidents (mine)
1. HIGH: this shell exports GIT_AUTHOR_NAME as a personal address, overriding `-c user.name`. It was in the AUTHOR NAME of two pushed commits (branches test/duplicate-key-lint-gaps-c294 and fix/address-remainder-c285-r2; PRs: none for the first, 170 closed). I did not force-push or delete. Replacement heads carry the correct author. Request: Don or the coordinator deletes those two remote branches; the commit objects stay reachable on GitHub until garbage-collected. Every commit now sources an explicit identity file.
2. C-285: manifests ssl-invoicing/ssl-timekeeping lines 43/80 and 47/86 stay (kill-switch reads the endpoint; its allowlist names the host): decision for Don. field-rest.ps1 is now required-variable: the scheduled renewal verifier dot-sources it, so FIELD_PROXY_URL must be set in the user environment before the next renewal (deploy precondition, not done).
3. Local Windows run of test_ssl_renewal "runbook pins" fails on renew_token.py (CRLF checkout, pre-existing, not my change); GX10 passes.

## Proposal (owed): non-root migration card (D-28 stage 2)
Builder Lane 3: per-service non-root USER with volume chown migration, as a separate change behind a runbook; precondition: probe which services write outside their volumes (compose-smoke), a Don-run chown of the estate volumes, rollback by image tag; nothing applied to the live estate without Don.

Asks: reviewer cards for PRs 157, 161, 171, 164-r2, 165, 167. Next in lane: C-149 (ci.yml timeout/constraints/skip budget).
