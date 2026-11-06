# Review PR 836 (G16: phase_g_stage0_check, read-only Stage 0 record check + deploy-record template) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `989f14b78fd5887348269f6d14b5d5f7ef2586c0`.
Conditions: C1 (one test, no code change): pin the eight services and their literal paths in a test (mutants D1 and D2 survive: the tests build their fake estate from the tool's own table, so a wrong path or a dropped service passes). C2: CI on the head. The tool's logic is right, it sends only unauthenticated `GET .../health`, and its output is ids and booleans only.

## Objections first
1. It proves "behaves off", not "unset": `/health` shows `operator_mode` off, `identity_present` false and no identity id, which is also what an explicit `FIELD_OPERATOR_REQUIRE=0` with no registry looks like. The template says "FIELD_OPERATOR* unset in every service environment"; the check cannot prove that (LOW wording; the template's own last paragraph says it proves nothing about secrets or files).
2. It reads through the proxy at one base: a service behind a wrong route, or the console answering for another prefix, is caught only if it answers with the wrong `service` name; the per-path table is not tested literally (C1).
3. A healthy Stage 0 needs all eight to answer: one stopped service fails the whole check (by design, "silence is not proof"); a deployer should expect FAIL while any container restarts.

## Checks (HIGH, run by me)
- Identity: 1 commit, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5; .github/: 0 files. 3 files: tools/phase_g_stage0_check.py (+111), tools/tests/test_phase_g_stage0_check_g16.py (+147), docs/templates/stage0-deploy-record.md (+22). Based on 117469db; main is e125a878; new files only, no overlap.
- Paths verified against the proxy: `integration/demo/Caddyfile` has `handle_path` for /registry, /ledger, /delegation, /killswitch, /governor, /federation and /lifecycle, and the console is the root default (reverse_proxy console:8011): the eight paths in the tool are the real ones (HIGH, read).
- Fields verified against the services: each of the eight `/health` handlers returns `service`, `build_sha` and `**op_health.health_fields()` (federation, lifecycle and ops-console read directly; the other five use a response model fed from the same `OperatorHealthFields`: `operator_mode`, `operator_identity_id`, `identity_present`, operator_health.py:124-128, 282-288). `build_sha` is "unknown" when unset, which fails the 40/64-hex check (fail closed).
- Template: blanks only; no address, key, hash or build id (read in full); says to keep the filled record outside the public repo.
- Tests on the exact head (Windows): test_phase_g_stage0_check_g16.py 16 passed; `environment_anchors --check` 0 wrong rows. The PR also reports the boundary-echo and http-env-proxy lints 163 passed (not re-run by me).

## Mutants (23 on phase_g_stage0_check.py vs the 16 tests; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| flags A1-A7 (log-only accepted, enforce accepted, absent block passes, identity present accepted, identity_present missing accepted, id set accepted, empty-string id refused) | 7 | 5 | 2 (A5, A7) |
| service and sha B1-B9 (name unchecked, status unchecked, sha regex any / 7-hex, expected sha not compared, agreement removed, agreement ignores a missing service, full sha printed, shown sha 40) | 9 | 7 | 2 (B2, B7) |
| exits and calls C1-C5 (authenticated call, empty result passes, failed exit 0, bad expect-sha accepted, usage exit 1) | 5 | 3 | 2 (C1, C2) |
| list D1-D2 (console path wrong, a service dropped) | 2 | 0 | 2 (D1, D2) |
Totals: 23 mutants, 15 killed, 8 survived. By id: killed A1 A2 A3 A4 A6 B1 B3 B4 B5 B6 B8 B9 C3 C4 C5 (15); survived A5 A7 B2 B7 C1 C2 D1 D2 (8); 15+8 = 23.
Survivor reading: C1 (authenticated call) and C2 (empty result passes) are equivalent here (`Estate(base, None)` sends no credential whatever the flag says, and an empty result cannot occur because every service adds a check). B7 is covered by each missing service failing its own check. A5, A7, B2 are LOW boundary pins. D1/D2 are real (condition C1): a Stage 0 run with only seven services checked would still print PASS.

## Optional LOWs (new PR)
Pin the identity_present-missing and empty-id boundaries and the HTTP status; reword the template to "operator flags: off as seen from /health".

## Not verified
CI/GX10; Linux; a real estate (my evidence is code reading plus the PR's fake-estate tests, not a live run); the PR's 163 lint tests.
