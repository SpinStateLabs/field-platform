# Lane O reviewer: PR 453 (C-1162, Caddy TLS phase 2, repo side: 18080 bound to loopback) @09f073768e9b9fc3c9ab403621c6a1099de18053. UNVERIFIED (cloud, no GX10, no CI, no real Caddy, no deploy)

VERDICT: PASS WITH CONDITIONS, naming head 09f07376. Lane B (docs, compose). Two commits (7088c482, 09f07376), both Don Hagell noreply as author and committer (git log, HIGH). The head does NOT contain current main: 32 commits behind origin/main 97dcfec1 (git rev-list --count pr453..origin/main), rebuild needed. Files: .github/workflows/ci.yml, docs/runbooks/v1.2-deploy-rollback.md, integration/demo/Caddyfile.gb10, docker-compose.gb10.yml, tools/tests/test_compose_static_pins.py, tools/tests/test_gb10_caddy_tls.py. Earlier Lane 7 reports exist (Q-98/Q-99 and C-1169 lines in the inbox); I did not read them; this review is independent. I did not write the head. Claimed through dispatch.sh (R-PR453-09f0737).

Objections first: (1) the change is a deploy-ordering hazard that no test can hold: the compose comment and runbook say "Deploy this block ONLY after every LAN caller is switched to 18443 and verified"; the repo change itself, once merged and deployed, closes plain HTTP 18080 to the LAN, and nothing in the repo knows whether a caller still uses it (read, HIGH). Deploying is the coordinator's and Don's act, not mine, and the runbook names Don's chat confirmation as the gate (runbook line 2081). (2) the CI step asserts the refusal as curl exit 7 on the runner's own LAN address; a runner with no routable address (the `hostname -I | awk` result empty) or one where the connection times out gives a different code and the step fails for a reason that is not the loopback bind (read, MEDIUM). (3) public-repo rule: the diff uses 192.0.2.10 (a documentation-range address) and `<gb10-lan-address>` only; no estate address, flag, build id or credential in the added lines (grep of the added text, HIGH).

Run here (cloud, scratch worktree on 09f07376, relative PYTHONPATH of every service src and packages src): tools/tests/test_gb10_caddy_tls.py plus test_compose_static_pins.py: 687 passed. These are STATIC tests of the YAML, Caddyfile, CI text and runbook; nothing here starts Caddy, docker or the CI step. NOT run: the 16-suite set, CI, anything on a GX10 or GB10.

Mutants (30 run in a scratch worktree, each a text edit of the real config, run against the two static test files; no syntax-broken kills. My first sweep had four Caddyfile mutants and one base-compose mutant that edited the first occurrence of a string inside a COMMENT, so they could not matter: I discarded them and rewrote them as edits of the real lines; the table is the second sweep. The test file carries its own MUTANTS table, so part of the kills overlap with it, but every mutant below is mine):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 18080 is published on 127.0.0.1 only (plain, 0.0.0.0, a LAN address, wrong port, dropped) | 5 | 5 | 0 |
| B2 18443 stays published for the LAN (loopback-only, wrong ports, extra 18080) | 4 | 4 | 0 |
| B3 Caddy's data dir persists on the named volume caddy_data at /data | 4 | 4 | 0 |
| B4 the GB10 Caddyfile: tls internal site, import of the base routes, listener, upstream, default_sni, skip_install_trust | 6 | 6 | 0 |
| B5 CI proves 18080 is refused on the LAN (exit 7) and published as exactly 127.0.0.1:18080 | 5 | 4 | 1 |
| B6 the base compose keeps plain 8080 | 3 | 3 | 0 |
| B7 the runbook documents the phase 2 rollback and the loopback binding | 3 | 1 | 2 |
| Total (counted from the rows) | 30 | 27 | 3 |

Survivors (3), all real LOW pin gaps:
- F-O-pr453-1 LOW-MEDIUM: the CI assertion `grep -qx '127.0.0.1:18080'` (exact line match) can be weakened to `grep -q '18080'` and no static test notices, although that weakened check would also pass `0.0.0.0:18080` (ci.yml, the compose port check). The step exists to catch exactly the all-interfaces binding.
- F-O-pr453-2 LOW (2 mutants): the runbook rollback sentence ("put "18080:8080" back and recreate the proxy") and the loopback binding text can be changed (to "do nothing" and to 0.0.0.0) without a test failing; the runbook is a human instruction whose accuracy no check holds.

CONDITIONS (blocking): C1 CI green on the exact head REBUILT on current main (32 behind) and, because this is compose/Caddy/CI, a GX10 run that includes the compose and Caddy tests; I could not run it. C2 the deploy gate (objection 1) is the coordinator's and Don's: I make no statement about deploy; the merge is separate from the deploy.
Optional, NEW PR after the head is frozen: F-O-pr453-1/2 pins.

Tokens/cost line: not available to me. I do not know.
