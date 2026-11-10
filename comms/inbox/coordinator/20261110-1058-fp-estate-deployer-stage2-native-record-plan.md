# Plan (read-only): native clean-Stage-2 record on the armed GB10, via tools/stage2_driver.py

Author: fp-estate-deployer. Status: PLAN ONLY. Nothing armed, nothing run, no record written. Basis: main df376056
(`tools/stage2_driver.py`, 147 lines), reviews R-PR1054-b223c7d and R-PR1054-df37605, `tools/stage_controller.py`,
runbook "Stage 2" and "Stage controller (P36, G24)". Estate runs build 41afda50 (Stage 2 armed, kill-switch enforce).

## 1. How the driver yields a native record without disarming (HIGH on the code reading)
- Call `run_stage2(records, estate, go_sentence=<Don's G25>, build_sha="41afda50...", expected_services=<the eight>, live=True, allow_already_armed=True)`.
- With the override present and `allow_already_armed=False` the driver raises `Refused("stage2_already_armed")` before the controller is built. That is the safe default; do not use it for this purpose.
- With `allow_already_armed=True`, `Stage2Actions(armed_before=True)` makes `write_override`, `recreate_killswitch` and `delete_override` no-ops in BOTH directions. `Controller.run` then writes natively `stage_start`, `step_done` x2, `stage_done` (stage=2). `stage_clean(2)` becomes true, which clears Stage 3's `stage_2_not_clean`.
- The checks still run for real, read-only: override present; kill-switch mode `enforce` (phase_g_check --expect-mode enforce); all services healthy; counters baseline (the eight) must not rise.
- Gap: no `Stage2Estate` implementation exists. The driver module has no command line and says the coordinator supplies it. Needed: a small READ-ONLY adapter (`override_present`, `mode`, `healthy`, `counters`) on the host that holds the compose files, over the same Stage 0 wrapper and paramiko path as pg-run.py. `write_override`, `delete_override` and `recreate_kill_switch` must raise or be unreachable (armed_before makes them unreachable). The adapter is new live-estate code and must be reviewed and dry-run on the stub harness before use.
- Half-armed (override file present, container not recreated, mode `log-only`): the `recreate_killswitch` check fails, the abort rollback is a no-op, `rollback_verify` fails (expects enforce), status `rollback_failed` ("act by hand"). Nothing is disarmed (fail closed), but the records file then holds `rollback_failed`, so every later run is refused until `record ack-rollback --stage 2`, and `stage_clean(2)` stays false (review note O3). Today's estate is not half-armed: the monitor read enforce x1 / log-only x7 for 48 of 48 polls (19:01Z to 23:02Z). The monitor has ended; the estate has been unwatched since 23:02Z unless restarted (re-probe read-only at go time).
- A crash mid-run leaves `stage_start` with no closing row: later runs refuse with `stage_in_progress` until `ack-rollback`.

## 2. G22 and which sha (MEDIUM: gate evidence not yet re-verified by me)
- Target sha8 = 41afda50, NOT df376056. The record binds the build the estate RUNS (F-816-5: alerts and gate rows must carry the same 8 hex as `build_sha` passed to the run). The driver is code that runs from main; it does not redeploy. Recording G22 against df376056 would assert a build the GB10 does not run, and would not match the existing alerts_proven row (41afda50).
- Writer: fp-estate-deployer (this session) writes it with `python tools/stage_controller.py record gate G22 --build-sha 41afda50278ad82086fc9ab1dd09417ca09cf37f --records <the records file>`, exactly as G21 was written, and only after verifying, from git and tests on 41afda50, the runbook G22 entry gates (a) to (d), plus (e) read-only: the internal secret hash is present on kill-switch and registry /health (`phase_g_check --stage 2` "2 of 2"), nothing printed. Don's approval needed for the write (same pattern as G21).
- Honest caveat: G22 was never recorded for this estate; Stage 2 was armed earlier through the s2-* scripts, not the controller. Recording G22 now attests the gates hold on the running build now.

## 3. G25 go sentence (NOT issued; Don's words only)
Constraints (stage_controller.py): non-empty, at most 500 characters, passes the alert content check (no key or long hex; sha8 is fine). Only its length and an 8-hex sha256 prefix are stored. Suggested text for Don to issue, or edit:

`GO STAGE 2 RECORD 41afda50 (I'm present): run the controller driver with allow_already_armed on the GB10, change nothing, G22 gates a to e met`

It must say record-only so it is not mistaken for a re-arm. It is not the Stage 3 sentence (`GO STAGE 3 41afda50`), which stays separate and Don's.

## 4. Risks and rollback
1. New unreviewed adapter on a live estate (mitigation: read-only methods only, review, stub dry run, then one live run).
2. A false abort (a transient health blip or a counter rise) writes `abort` and `rollback_failed`, blocking runs until `ack-rollback`, with nothing disarmed. Cost: delay, not exposure.
3. The record is a point-in-time `stage_done`, not a soak. PR 837's window judge may want more at Stage 3 entry (not verified).
4. Controller alerts: `stage_transition` pings fire to Don's phone during the run (expected).
5. The records file is trusted by file permission only. A native run is auditable evidence; a hand-written row is not.
6. O1 race (override check before the run lock): small, MEDIUM.
7. Rollback for the ESTATE is unchanged and not the driver's: the reviewed `s2-6-rollback.sh` (disarm to log-only), via pg-run.py, only on Don's say. The driver's own rollback is a no-op under allow_already_armed by design. The Stage 2 monitor should run during the driver run (its auto-rollback to s2-6 stays as the safety net).
8. No redeploy, no Stage 3, no Fly.

Sequence once Don approves: (i) restart the read-only monitor; (ii) verify and record G22 for 41afda50; (iii) write and review the adapter, stub dry run (`live=False` first writes only a `plan` row); (iv) Don issues the G25 sentence; (v) one live `allow_already_armed` run; (vi) `plan --stage 3 --build-sha 41afda50` shows whether Stage 3 still refuses. Arming Stage 3 stays a separate step.
