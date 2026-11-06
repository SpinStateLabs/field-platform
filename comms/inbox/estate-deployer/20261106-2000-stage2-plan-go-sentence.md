# GB10 redeployed to f7408db5 at Stage 1 LOG-ONLY; Stage 2 prepared, NOT armed (estate-deployer, 2026-11-06 ~19:50Z)

## Red-team conditions (20261106-2000-red-team-NO-BLOCKER-main-f7408db5.md) and status
| # | Condition | Status |
|---|---|---|
| S2-1 | `phase_g_check --stage 2` prints "internal secret hash present ... (2 of 2)" on the real estate | NOT MET: 0 of 2 (see 3(e)) |
| S2-2 | Driver passes `--build-sha` and the service list to the stage controller (R1, R2) | OPEN, goes in the go sentence; GB10 toolchain here (pg-run s2-*) does not use the controller |
| S2-3 | Go sentence says registry stays LOG-ONLY (N-1) and lifecycle auto-kill, X3 check, keyless tools answer 401 (N-6) | in the sentence below |
| S2-4 | Rollback rehearsed incl. R-1 (revoked/unreadable svc-killswitch key: kills/revives 502, B-7 break-glass) | NOT rehearsed at Stage 2; Stage 1 rollback (g6) rehearsed twice today |
| S3-1..3 | clean judged Stage 2 window; reverse-order rollback rehearsed + `--expect-mode` after every `up`; five manifests lack don-admin | Stage 3 not in scope |

## Redeploy (done, GB10 only)
- Disarmed Stage 1 (g6, flags blank), sync of f7408db5 to the GB10 bare repo (fast-forward), Stage 0 phases pre, backup (set `stage0-20261106d`), build (18 images, all bake f7408db5), up (stop-to-healthy 7 s), verify (health 51/51, continuity 3/3 vs pin 3640/d61ffe69751a0bd1, restarts 0, 0 Tracebacks), canary (5/5, 28/28, 4/4, 7/7, 2/2, token revoked). Then g0-g5: LOG-ONLY re-armed, g4 PASS, canary restored.
- Now: 8/8 log-only, registry b885ebdab2948f13 x11 rows, build f7408db5 on all eight, drops 0/0 on all eight, canary-gb10 halted=False. Fly: 8/8 log-only, 11 rows, drops 0/0, continuity 3/3 vs 664/1645215d0770cced (image main-3804d0b, not redeployed).
- GB10 Stage 1 window started 2026-11-06T19:44:45Z, 13 polls x 300 s, auto-rollback on any dropped_unauthenticated/refused rise (g6 --allow-not-tip). Result recorded when it ends (~20:45Z).
- Script edits (local source, diff below): (1) manifests guard allows untracked `manifests/ssl-fp-*.yaml` (Don: "ignore ssl-fp files"); (2) `project_cids` excludes the approver pilot container (profile `approver`, up 2 days, live key mount): the deploy never touches it. The auto mode classifier refused me stopping it, so I did not. It stayed up through the outage window (it is outside compose here). Operators file from `operators.conf` (see 1130 report).
- Side effects: "other workloads" count 23 vs 22 at backup (approver counted as other; one more unidentified, unrelated, not fatal per DS0-R1-19). Fixed once more by hand: nothing.

## Stage 2 checklist (runbook :1471) results
1. Clean Stage 1 window on this build: PENDING (window running, 1 poll so far clean).
2. Guards slice in the image: PASS (g4 positive/negative controls PASS on f7408db5; red-team verified G21-24).
3. `$C`/`$C3` defined (s2 scripts via pg-run), override file absent: PASS ("No such file"); `svc-verifier-gb10` row present (11 ids, g2) and key file present 0600 48 bytes: PASS.
3(a) image carries G22: PASS (`internal_secret_sha256_present` and `operator_internal_route_denied` in all 8 /health).
3(b) mode policy as built: PASS (read-only; red-team tests).
3(c) holder is the rotator only; sender C-496 not merged: routes stay disabled under ENFORCE by (b): ACCEPTED per runbook text.
3(d) deny counter in each /health: PASS (0 on all eight).
3(e) secret file on each estate and FIELD_INTERNAL_SECRET_SHA256 in each service env: FAIL. GB10: hash absent on all eight (0 of 2 for killswitch+registry); no secret file. Defect found: `integration/` compose files and `.env` do not pass FIELD_INTERNAL_SECRET_SHA256 to any service (git grep of origin/main f7408db5: only docs, field_core and tests). So the hash cannot be set through `.env`; it needs a compose change (card) or an uncommitted override that sets it on killswitch and registry (registry recreated too: a second `up` the Stage 2 scripts do not do; s2-0..s2-6 also have no G22 gate). Fly equivalent: `fly secrets import FIELD_INTERNAL_SECRET_SHA256=...` (one restart), Fly is not in Stage 2 anyway (Fly Stage 4b is separate).
4-5. Override write + REQUIRE `up`: not run (needs Don).
6-8. Exit evidence, only `$C3` may `up`, rollback: not run; rollback procedure in sec. below.

## REQUIRE and image rollback; how Stage 2 differs from Stage 3
- REQUIRE is reversible in config (delete override, `$C up --no-deps killswitch`, expect log-only) but NOT by image: an image without C-5 under a set REQUIRE presents no identity and every kill breaks (runbook :1640ish; controller prints this at plan for Stage 3). Rollback anchors exist (`:rollback-20261106d` tags and stage0 backup set) for the config path only.
- Stage 2 = REQUIRE on the kill-switch only: Don's/verifier's kills work (registry LOG-ONLY allows the PATCH), X3 check, lifecycle auto-kill and keyless tools answer 401, registry/other seven stay LOG-ONLY (N-1: registry PATCH needs only the perimeter secret). Stage 3 = all eight: kill-switch registry PATCH under REQUIRE (needs identity), a dead registry makes kills 502 fail closed, drills/domain kills degrade (runbook :1392); rollback in reverse order (seven first, kill-switch last).

## Draft go sentence for Stage 2 (Don types it in chat; coordinator relays; NOT yet valid)
"Stage 2 go: on the GB10 only, build f7408db5943091156f78a1e88292adb10f62c9ae, operators file sha16 b885ebdab2948f13 (11 rows), after the Stage 1 window recorded CLEAN at <UTC from window.log>, with `phase_g_check --stage 2` showing internal secret hash present 2 of 2, set FIELD_OPERATOR_REQUIRE=1 on the kill-switch ALONE through the uncommitted override (sha256 recorded). I accept that: the registry and the other seven stay LOG-ONLY (N-1); lifecycle auto-kill, the X3 check and every keyless tool answer 401 (N-6); REQUIRE is not rolled back by image, only by deleting the override and recreating the kill-switch; if svc-killswitch's key is revoked or unreadable every kill and revive answers 502 and B-7 break-glass is the only path (R-1). Stage 3 is not authorised by this sentence. Fly is not touched."

## What blocks the go
(1) 3(e): a compose change or override to pass FIELD_INTERNAL_SECRET_SHA256 + creating the secret file/hash (coordinator step; I will not print the secret); (2) the clean-window time (~20:45Z) and a judged Stage 1 window; (3) Don's chat OK; (4) approver pilot is excluded from the redeploy, owner should confirm it did not need the new image.

## Diff: gb10-deploy-stage0.sh (tasks/deploy-stage0-scripts)
```
80c80
< ALLOW_UNTRACKED='^\?\? manifests/volatility-trader.yaml$'
---
> ALLOW_UNTRACKED='^\?\? manifests/(volatility-trader|ssl-fp-[a-z0-9-]+)\.yaml$'   # Don 2026-11-06: ignore the ssl-fp-* estate manifests (installed on the host, untracked)
103c103,105
< project_cids() { "$DOCKER_CMD" ps -q --filter label=com.docker.compose.project=field-platform; }
---
> # The approver pilot (profile `approver`, S2) runs beside the estate and is not part of a deploy: it is excluded here so the stack
> # stop, the service-set check and the restart counts never touch it. Added 2026-11-06 (auto mode refused stopping it).
> project_cids() { local c; for c in $("$DOCKER_CMD" ps -q --filter label=com.docker.compose.project=field-platform); do [ "$(svc_of "$c")" = approver ] || echo "$c"; done; }
128c130
<   if [ -n "$dirty" ]; then printf '%s\n' "$dirty" | head -n 20; die "working tree is not clean beyond the known untracked manifests/volatility-trader.yaml (stash nothing: fix by hand)"; fi
---
>   if [ -n "$dirty" ]; then printf '%s\n' "$dirty" | head -n 20; die "working tree is not clean beyond the known untracked manifests (volatility-trader, ssl-fp-*) (stash nothing: fix by hand)"; fi
```

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
