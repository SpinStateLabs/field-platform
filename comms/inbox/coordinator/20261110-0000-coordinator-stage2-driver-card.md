# B-S2-DRIVER: Actions driver + G22 gate record so Stage 2 can run natively (Don chose "Build the driver", 2026-11-10)

Why: the clean-Stage-2 controller record cannot be written by the CLI; only Controller.run writes stage_start/stage_done. A hand-written row was blocked by the permission classifier. Don chose the native path.

Source (fp-estate-deployer report, 2026-11-09): Controller.run(2, live=True) needs
1. an Actions driver wrapping the s2-* steps and s2-6 (stage_controller.py says the driver is the coordinator's; none exists in tasks/gb10-require-scripts);
2. a G22 gate record for the target sha (41afda50 had none);
3. the Stage 2 go sentence passed in as input (G25) - Don's, never self-issued;
4. care: Controller.run(2) re-executes write_override and recreate_killswitch, and any abort rolls back (delete_override, recreate_killswitch), which would disarm an armed Stage 2.

Deliver (draft PR, tests, no live GB10 action): the driver, a dry-run harness proving rollback and no-op behaviour on an already-armed estate, and a note on how a live run is made safe against the armed Stage 2 (idempotent arming or a pre-flight that refuses to re-arm). Verify these facts against stage_controller.py before coding. Do not run anything live.
