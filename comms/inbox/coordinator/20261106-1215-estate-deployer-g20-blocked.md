# G20 (GB10 TLS phase 2) blocked (estate-deployer, 2026-11-06)

Source: runbook docs/runbooks/v1.2-deploy-rollback.md, sec. 8 "Phase 2" (lines ~2105-2145 on main e125a878). HIGH.
Blocked on two things, neither an estate act I can do:
1. Entry criteria: every LAN caller switched to https://<gb10-lan>:18443 AND verified, each recorded: field-rest.ps1 / provision_ssl_agents.py (FIELD_PROXY_URL), the two rog-command renewal tasks' --base, estate_kill_watcher --base, the manifests' kill_switch endpoints, ops console in a browser. These sit on rog-command (Don's machine) and in repo changes.
2. A separate PR changing integration/demo/docker-compose.gb10.yml ports to "127.0.0.1:18080:8080" (static test + CI check flipped); I deploy only that merged change, outside the 14:50/15:05 renewal tasks.
No such PR is in my list; need a builder card (compose + test change) and Don/rog-command caller switches. Rollback is ready: put "18080:8080" back, recreate proxy.
Everything else unblocked is done; G25/G26 still wait on red-team no-blockers and G21/G22 on main (817 closed, 818 open; see 1200 plan).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
