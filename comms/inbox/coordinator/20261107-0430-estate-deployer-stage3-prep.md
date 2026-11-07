# Stage 3 preparation, NOT armed (estate-deployer, 2026-11-07 04:30Z)

R-1 RULING RECORDED: Don chose repo tests only (PR 854 tests landed as ff06b3398 plus the three live Stage 1 rollbacks) as the Stage 2 rehearsal. The live R-1 rehearsal moves to the Stage 3 entry. Stage 2 stays armed.

## Stage 2 monitoring
- GAP: no monitor ran 01:13Z to 04:27Z (the window task ended at 01:13Z). First read after the gap, 04:27:51Z: 8/8 services, killswitch enforce, other seven log-only, dropped 0/0 on all eight, canary halted=False (HIGH, direct read). Cumulative counters cannot show a transient drop inside the gap; they show none now.
- Harness-tracked task b0v7tfunq: 48 polls x 5 min (about 4 h), auto-rollback via s2-6 on any drop rise, enforce/log-only shape change, or canary halt. Restart it at the end if Stage 2 is still held.
- Not explained: killswitch refused_count=45 (s3-0 read). My own ctl-nocred/ctl-x3 probes and the earlier 403 attempts account for some; I have not reconciled the 45 (LOW). dropped_refused_records is 0. I will check whether it grows.

## 1. Stage 3 conditions on main (origin/main is 3804d0b90, not ccd013d4; ccd013d4 is 2 commits back)
| Cond | Status | Source |
|---|---|---|
| B-S3-1 Stage 2 window judge | HELD. PR 837 is OPEN (mergeable, checks SUCCESS). Not on main. Host-side window record exists (s2-4 window-close, 1 h). | gh pr view 837 |
| Stage 2 window clean, 1 h | MET. s3-0 0.2 passed: armed 00:08:42Z, closed clean 01:14:13Z. | s3-0 run 04:3xZ |
| Stage 1 window record | MET (s3-0 0.2b no miss). | s3-0 |
| Registry/identities | MET: 11 rows b885ebdab2948f13 in all eight, health 51/51. | s3-0 0.3 |
| P29 (no-change re-provision) | MET: efe430bc6 and 9a2417c04 are ancestors of 41afda50. Use --env STAGE0_PG_P29_COMMIT=efe430bc6d083b04225106f00ba1018ced559a33. | s3-0 0.4 |
| Manifests lack don-admin | RECONCILED: main has FIVE manifests with a non-empty authorized_operators (canary-fly, canary-gb10, deployment-agent, ssl-invoicing-agent, ssl-timekeeping-agent) and all five list don-admin; test_manifests_don_admin_s3_3.py pins it. The architect's "only canary-fly and canary-gb10" is stale. | git grep on origin/main |
| GB10 renewal job identity | OPEN (FAIL): no crontab line passes --operator-id job-renewal-gb10; ~/vt-renewal/renew_token.py differs from tools/renew_token.py. Key files present. A host config change; I did not make it. | s3-0 0.5 |
| Don line 18 (two Windows renewal tasks carry job-renewal-rog) | OPEN, Don's. | s3-0 0.6 |
| Live R-1 rehearsal | MOVED to Stage 3 entry (Don's ruling). Needs Don's key. | ruling |
| RT3 stage-controller | ack-rollback and exclusive lock landed (25d2fc6cb, PR 859 closed). Stage 3 spec: gates G21, needs a clean Stage 2 record, go sentence, build sha. | tools/stage_controller.py |
| Rollback rehearsal, --expect-mode after every up | GAP. s3-6 checks shape and phase_g_check log-only once, after both recreates. A mixed middle state (seven log-only, kill-switch enforce) is the Stage 2 shape; I propose a Stage-2-shape check after the seven. Not edited (untested rollback code). Say go and I dry-run it first. | s3-6 read |
| s3-0 overall | 3 open: GB10 cron, renew_token pin, Don line 18. Everything else passed. | s3-0 |

## 2. Redeploy to main for Stage 3?
- Recommendation: NO redeploy. The Stage 3 scripts and the controller are host-side. C-5 is already in 41afda50 (Stage 2 REQUIRE works).
- main differs from 41afda50 in 86 files across service code (kill-switch request bounds, ledger observer alert coalescing, lifecycle, registry, delegation, field-core). I have not judged whether any is a Stage 3 entry fix; the architect should say.
- What a redeploy does: gb10-deploy-stage0.sh runs compose with the two base files only (line 99, 348), no require-canary override. A redeploy recreates the kill-switch LOG-ONLY and returns the estate to Stage 0 (what my two earlier redeploys did). It is not a rollback of REQUIRE and it does not use the Stage 2 disarm path. Expect: Stage 2 disarm first (s2-6), redeploy, Stage 1 re-arm, 1 h window, a NEW Stage 2 go sentence (the pre-authorisation names 41afda50), 1 h window, then Stage 3. About 3.5 h and two Don sentences. Controller records keyed to the old sha8 would also be refused.
- Redeploy only if the architect names a main-only fix as a Stage 3 entry condition.

## 3. Stage 3 plan (not authorised)
Entry: S3 conditions above; controller records for the running sha8: alerts-proven, gate G21 (G22 for Stage 2 is recorded). Live R-1 rehearsal with Don's key (see below).
Arm: s3-0 (preconditions) -> s3-1 backup -> s3-2 render check -> s3-3 arm all eight (set REQUIRE in .env, remove override, recreate eight) -> s3-4 verify steps one per invocation (no-credentials refused, own-key positive path by Don, window-close) -> s3-5 restore canary. 1 h soak.
Rollback (s3-6), reverse order: remove FIELD_OPERATOR_REQUIRE from .env, delete override, recreate the SEVEN first (registry delegation governor fedbroker ledger console lifecycle), kill-switch LAST, then phase_g_check --expect-mode log-only. Never by image alone. Auto-rollback on any dropped_* rise or canary failure, as in Stage 2.
Go sentence, exactly: `GO STAGE 3 41afda50` (plain token; sha8 of the running build; no 16-hex operators sha in it, the content check withholds a 16-hex run). If we redeploy, the sha8 changes.
Don must supply: (a) the go sentence; (b) line 18 confirmation, or tell me to proceed with it recorded as his; (c) a ruling on the GB10 renewal job: may I set --operator-id job-renewal-gb10 in the crontab and replace ~/vt-renewal/renew_token.py with tools/renew_token.py (host config change, Stage 3 entry); (d) the live R-1 rehearsal run with his key and break-glass; (e) the ruling on whether PR 837 must merge first (B-S3-1 held).

## 4. Fly
Fly "Stage 2" is Stage 4b (REQUIRE). Scripts f4b-0..4 exist. Gates: 4a armed and verified at least the soak floor ago (Fly 4a armed; floor in f4lib), GB10 Stage 3 record clean (f4b-0 --stage3-record, E1) so Fly REQUIRE cannot precede GB10 Stage 3, a renewal record (E2), Don's own go sentence, and every internal caller with an identity (checklist 4b).
PR 867 (entrypoint exports FIELD_INTERNAL_SECRET_SHA256): OPEN, mergeable; CI shows `tests (3.11)` and `tests (3.13)` FAILURE, 3.12 and 3.14 in progress, compose-smoke, fly-image-smoke, compose-upgrade-smoke SUCCESS. A reviewer PASS does not clear a failing CI. After merge Fly needs a redeploy of the new image (current main-3804d0b v19 lacks it), then the Fly internal secret hash (a secret set, Don's chat go) and the G22-style check. A Fly redeploy is not authorised.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
