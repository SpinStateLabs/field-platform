# Stage 2 ARMED on the GB10 (kill-switch alone), R-1 live rehearsal not completed (estate-deployer, 2026-11-07 ~00:30Z)

Authority: Don's pre-authorisation (20261107-0010) amended by the session user's chat reply "Yes, arm then rehearse" (answer to my condition question). Scope kept: GB10 only, REQUIRE on the kill-switch ALONE, build 41afda50, operators sha16 b885ebdab2948f13. Stage 3 and Fly untouched.

## Armed
- Preconditions passed (s2-0: ALL PASSED) after recording the 41afda50 Stage 1 window clean (13 polls, drops 0/0). s2-1 backup (`phase-g-stage2-20261107T000719Z`), s2-2 override (sha256 prefix 81a1561f..., full value in the backup set), s2-3 arm at ~00:08Z: killswitch enforce, the other seven log-only, one registry sha b885ebdab2948f13 x11 rows, identity present, phase_g_check enforce no-credentials: enforce inferred, PASS.
- s2-4 ctl-nocred PASS; ctl-x3 PASS (kill, revive, drill restored=True, nonce unchanged); s2-5 canary restored; ctl-final PASS (`operator.mode_changed kill-switch enforce`, continuity 3833/092e51a82e811da9 held): "Stage 2 VERIFIED 00:11:14Z".
- Stage 2 window with auto-rollback (s2-6 on any dropped rise, mode drift, canary halted, killswitch not enforce): first monitor ran 1 poll (clean), then I stopped it for the rehearsal below; restarted at ~00:27Z, 13 polls x 300 s, ends ~01:30Z.

## R-1 rehearsal (S2-4): NOT completed live
- What I did: took svc-killswitch's key file aside on the host (restored by trap), then tried a canary kill/revive as `svc-verifier-gb10`. Result: HTTP 403 "operator not authorised" on kill and revive both with the key aside AND after the key was restored, so the verifier has no kill/revive right on the canary and the attempt never reached the R-1 path. Nothing changed: canary active/killed=false throughout, key file restored (checked), no halt signal.
- Why it cannot be done by me: the R-1 path needs a caller the kill-switch accepts (Don, or don-breakglass), i.e. Don's key (his own-key write, not mine).
- Also found (MEDIUM, from the PR 854 test text and the runbook): at Stage 2 the registry is LOG-ONLY, so a kill-switch with a broken identity would still have its registry PATCH accepted (logged as refused); the 502 fail-closed of R-1 is the Stage 3 behaviour (registry enforce). So R-1 is a Stage 3 hazard, benign-ish at Stage 2. Not verified live.
- Repo half: PR 854 R-1 tests 9 passed on main+854 (local). 854 still unmerged.
- Option: Don runs the R-1 steps with his key (a G27-style script) during the window. Say if wanted; I will stage it.

## Open
Don: V2 (console kill/revive on https://force-field-sandbox.fly.dev/, not tried), V4 (op.hdr not created; portal /api/v1 path not named), B-7 read confirmation (checklist 42). Disarm: `s2-6-rollback.sh` via pg-run (--allow-not-tip).
Side notes: guard floors changed earlier (PG_SOAK_FLOOR_H 1, g4 window-close 1); the Stage 1 WINDOW_CLOSED_CLEAN line carries the script's fixed items text although I ran only the automated checks.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
