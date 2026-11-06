# estate-deployer: GB10 Stage 1 LOG-ONLY ARMED on ede21674 (eleven-row file), 1 h window running

Window start 2026-11-06T07:12:52Z (re-armed), ends about 08:13Z. Auto-rollback (g6) trips on any rise of dropped_unauthenticated_records / dropped_refused_records, mode != log-only on any of 8, or canary halted.

## Done (HIGH, from run logs)
- g0 PASS (11 rows, 4 daemon keys match, health 51/51 on ede21674). g1-g5 PASS. g4: 8/8 log-only, registry sha16 b885ebdab2948f13, rows 11, identity_present on registry/delegation/killswitch/lifecycle, one operator.unauthenticated row per guarded service, ledger continuity ok, dropped 0/0 everywhere.
- Ruling honored: patched COPY only, outside the repo (scratchpad `s1p/`), shared scripts untouched.

## Patch diff (gb10-require-scripts/_lib.sh only)
- TEN_IDS: append `svc-verifier-gb10` (sorted, 11 ids)
- OPS_ROWS=10 -> 11
- STAGED: operators-staging/operators-ten-row.json -> operators-eleven-row.json
- OPS_SHA16 default: ce5a9abcba8d2509 -> b885ebdab2948f13
(cosmetic strings "ten"/"10 rows" and the BK copy name operators-ten-row.staged.json left as is.)

## Events to know
1. g0 0.5 refused: a stale live `~/.field-local/operators/operators.json` (the OLD ten-row, ce5a9abc, from the Oct 27 arm) existed. Unreferenced at Stage 0. Copied and moved to `~/field-backups/operators-superseded-ten-row-20261106/`; nothing deleted.
2. Two self-inflicted rollbacks (g6 ran clean both times, estate back to Stage 0 shape, counters 0/0): my window monitor mis-parsed (a path bug, then a canary-status string check) and tripped with no data. Not an estate fault. Monitor fixed: relative path, 3-try read, fail-closed only on read failure (no rollback), rollback only on real counters. g6 closes the backup set, so each re-arm needed a fresh g1. Side effect: g6 rollback rehearsed twice on this build (runbook :1434-1435 relevant to G26).
3. killswitch showed refused_count=11 at g4 (log-only refusals, dropped=0). Baseline, not a gate counter; watching.

## Next
- Window clean -> Fly Stage 1 sequencing (E8 flylib stage-aware fix and four Fly key secrets still needed), then G20 TLS phase 2.
- G25/G26 still need G21/G22 merged (PRs 817/818) and red-team no-blocker; a redeploy for them resets the window.
- G27 untouched (Don's).
