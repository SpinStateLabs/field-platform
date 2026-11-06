# RED TEAM: updated Stage 2 / Stage 3 verdicts on main e125a878. ssl-fp-red-team, 2026-11-06
Method: main e125a878 in its own worktree; PR 818/827 trial-merged onto it; same attack scripts as before (sc_attack2.py, g22_attack.py, qcell.py; not in repo). Tests: G21 + stage controller on main 127 passed; G22 set + controller on main+818+827 298 passed.

## STAGE 2 VERDICT: BLOCKERS (one blocker)
| ID | Finding | Conf |
|----|---------|------|
| B-RT-g22-not-landed | G22 is NOT on main (0 hits for INTERNAL_HEADER in operator_health.py; no FIELD_INTERNAL_SECRET anywhere in packages, services or tools). PRs 818 (35f06096) and 827 (a6d524da) are open. Without it any perimeter-secret holder can call `/operator/verify-hash` and `/operator/rotation-state` under ENFORCE (repro in the 20261105-1850 Stage 2 report, unchanged). | HIGH |

Merge note (HIGH): PR 818 conflicts with main in `docs/runbooks/v1.2-deploy-rollback.md` only (the code merges cleanly and 298 tests pass with 827). 818 needs a rebase before it can land.

## STAGE 3 VERDICT: BLOCKERS (same single blocker, transitive)
Stage 3 requires an armed, clean Stage 2, and Stage 2 requires G22, so B-RT-g22-not-landed blocks it too. No Stage-3-only blocker remains.

## What cleared since 3804d0b9 (verified on main, HIGH)
- G21 on main (9a2417c0, f3b6870c): `edit_refused`, estate self-agent manifests list `don-admin`; 10 G21 tests pass on Windows. Residual (declared): five manifests still lack `don-admin` (canary-fly, canary-gb10, compliance-crosswalk, conformance-sentinel, force-gateway); a don-admin edit of those is refused until added.
- G23 (fd0ac135) and G24 (ede21674 + b1b229f1 + 75085ae3) on main. Controller on main is identical to PR 832. Re-run: records failure rolls back (F-816-1), interrupt rolls back then re-raises (F-816-2), empty baseline gives health_failure (F-816-3), Stage 3 refused without a clean Stage 2 (F-816-4), a gate/alerts record on another sha is refused when a build sha is passed (F-816-5). 117 controller tests pass.
- Board pack links (87b6eee0, 5a3c3c0d): `query_cell` links only `GET http(s)://...`; hostile inputs (`javascript:`, `"><script>`, `'`, `<d>`, `onmouseover=`) are escaped or left as text; the console button fetches with x-field-auth and saves the file, never opens it. No injection found. Residuals: userinfo (`http://evil@host`) is allowed in an href, and the links still point at internal service addresses (127.0.0.1:8002) that a board reader cannot open and that reveal topology (LOW; same as my 1000 note, point 3).

## Residual, non-blocking but to settle before the go sentence (controller defaults; card B-RT-832-binding-defaults stands, HIGH)
- RT-832-R1: the sha binding is opt-in (no `--build-sha` = records of any sha, or none, pass).
- RT-832-R2: `expected_services` defaults to empty: a one-service baseline completes.
- RT-832-R3: after a Stage 3 abort, Stage 2 still reads clean; a retry plans without re-arming.
- RT-832-R4 (LOW): records failure at `stage_start` rolls back an untouched estate.
The coordinator/driver must pass the build sha and the full service list for each stage; if it does, R1/R2 do not bite.

## To flip to NO-BLOCKER (both stages)
1. PR 818 rebased on main (runbook conflict) and merged with 827 (G22), `phase_g_check --stage 2` showing `internal_secret_sha256_present` 2 of 2.
2. A re-run of my G22 attack set on the merged head (about 20 variants pass today on the PR head).
3. Driver passes `--build-sha` and the stage's service list (R1/R2), or the defaults are fixed.
Stage 2 go sentence: keep BLOCKED until 1 and 2. The Stage 2 go sentence should still say the registry stays LOG-ONLY (N-1).
