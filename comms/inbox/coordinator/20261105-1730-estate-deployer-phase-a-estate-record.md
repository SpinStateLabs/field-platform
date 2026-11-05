# ESTATE-DEPLOYER: Phase A estate record (truth), 2026-11-05 17:21Z

Measured read-only by ssl-fp-estate-deployer. No estate was changed. Tags: HIGH = measured today.

## GB10 (HIGH)
- Image/build: `/health` build_sha = cefb81b6e905eb1fa8ff7093fe057908dbda7ea3 (PR #52, 2026-10-27). origin/main = 3804d0b9 (472 commits ahead; CI green on it).
- All eight services started 2026-10-28T00:51:07Z, restarts 0, no recreate since.
- **Stage 1 LOG-ONLY IS ALREADY ARMED** (G18 armed 2026-10-28T00:51:05Z, ~8 days): `.env` has FIELD_OPERATORS_DIR + FIELD_OPERATOR_REGISTRY + four per-daemon key dirs; FIELD_OPERATOR_REQUIRE blank. Operators file sha16 ce5a9abcba8d2509, 10 rows. Record: `~/field-backups/phase-g-deploy-record.txt` (an earlier arm 2026-10-27T20:06Z was rolled back 20:08Z; the 00:51Z arm stayed). No require override file on disk.
- Per-service (all 8) operator_mode=log-only; REQUIRE blank x8; dropped_unauthenticated_records=0 and dropped_refused_records=0 on all 8 at 17:21Z. identity_present true for registry, delegation, killswitch, lifecycle.
- `phase_g_check --expect-mode log-only` (no key): 32/32 PASS. Ledger consistent (3331 events). canary-gb10 halted=False.
- Stage 0 is therefore deployed (G16) but at cefb81b, not current main.

## Fly force-field-sandbox (HIGH)
- v17 (2026-11-04), image main-efe430b, build_sha efe430bc... ; machine 8d9250a3216638, 3/3 checks.
- operator_mode=off; zero FIELD_OPERATOR_* env vars; no operator secrets set; drops 0/0. Stage 0 deployed, Stage 1 NOT armed on Fly.

## Readings of the task vs truth
- G16 on GB10 exists at old SHA; G18 on GB10 exists. A window of 8 days with zero drops exists in counters (MEDIUM: counters reset on restart, none since 10-28; no traffic profile known).
- Stages 2/3 entry NOT met: no G21/G22/G23/G24 PRs on main (only #629 docs found), no red-team report seen.

## Plan
B: deploy main 3804d0b9 to both estates via tasks/deploy-stage0-scripts (needs flags-blank per script: GB10 Stage 1 rolled back, redeployed, re-armed; rehearses rollback). C: ten-row file already exists (sha16 above); re-check with `operator_keygen.py --check`. D: Fly Stage 1 arm after B. E/F/G/H blocked as above.
