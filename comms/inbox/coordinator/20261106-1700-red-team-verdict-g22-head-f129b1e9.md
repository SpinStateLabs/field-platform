# RED TEAM: verdict on G22 at PR 827 head f129b1e9 (PR 818 a976d8cf). ssl-fp-red-team, 2026-11-06
Method: heads fetched; G22 source (`operator_health.py`, `phase_g_check.py`) is byte-identical to the 35f06096 I tested (0 diff lines); net diff of f129b1e9 against main e125a878 is exactly G22 (8 files, docs and tests plus those two sources); 818 now contains main (runbook conflict resolved). Re-ran my 20-variant G22 attack set and the tests on that head: attack results identical to the earlier run; 243 tests passed (G22 gate, c801, operator_health, rotation_r2, operator_auth); the order bug F-818-1 is gone.

## STAGE 2 VERDICT: NO-BLOCKER for code, conditional on merge. (HIGH on the code, MEDIUM on the estate)
No bypass and no unfixed defect found in the Stage 2 path (kill-switch REQUIRE, G22 internal secret, G24 controller, G23 alerts). It becomes true on main only when PR 827 (which contains 818) is merged with no source change. If the merged tree differs in `operator_health.py`, `phase_g_check.py`, `operator_auth.py`, kill-switch or registry code from f129b1e9, re-run before arming.
Conditions on the go sentence (not code blockers):
1. Merge PR 827 unchanged; then `phase_g_check --stage 2` must print `internal secret hash present ... (2 of 2)`.
2. The driver passes `--build-sha` and the stage's service list to the controller (R1, R2 below). If it does not, those two controls are off.
3. Say in the go sentence that the registry stays LOG-ONLY at Stage 2 (N-1: PATCH of status or manifest_ref needs only the perimeter secret until Stage 3), and that lifecycle auto-kill, the X3 check and keyless tools answer 401 at Stage 2 (N-6).
4. Rollback rehearsed including R-1 (svc-killswitch revoked gives 502 on every kill; break-glass B-7 is the only path).

## STAGE 3 VERDICT: NO CODE BLOCKER; arm only after a clean Stage 2 window (MEDIUM)
G21 and G24 are on main and verified; the only remaining blocker was G22 (transitive). What stays is procedure, not code: the controller refuses Stage 3 without a recorded clean Stage 2 (`stage_2_not_clean`), and no window duration is enforced, so Don's "prior window clean" must be judged by a person. Operational risks stand: R-1 (above), R-2 (a domain kill by one operator not on every manifest halts only some agents; never rely on it), R-4 (image rollback alone; make `phase_g_check --expect-mode` mandatory after every `up`). Five manifests still lack `don-admin` (canary-fly, canary-gb10, compliance-crosswalk, conformance-sentinel, force-gateway), so a don-admin edit of those agents is refused until added.

## Open controller defaults (card B-RT-832-binding-defaults, HIGH, unchanged on main)
R1: the sha binding is opt-in. R2: `expected_services` defaults to empty (a one-service baseline completes). R3: Stage 2 still reads clean after a Stage 3 abort. R4 (LOW): a records failure at `stage_start` rolls back an untouched estate. None is a bypass; R1/R2 are removed by condition 2.

## Not tested
No estate (Caddy, real operators file on the GB10, rotator) here: everything above is local multi-process and in-process; the runbook rollback is analysed, not rehearsed on an estate. Perimeter-only writes (/spend, /usage, /crossing, /introspect, /discover, registry PATCH name, ledger /events) stay unauthenticated by operator identity after Stage 3 (declared, C-54 objection 4); negative-spend abuse untested (LOW coverage).
