# fp-estate-deployer: Stage 3 prep steps A-C (2026-11-09) - NOTHING WAS WRITTEN TO THE ESTATE

Summary: Step A partly verified, nothing recorded; Step B not started; Step C not run. Three items need a decision (end).

## STEP A
- G21 evidence (direct reads, HIGH): 9a2417c04 and 36fa4aeb2 are ancestors of 41afda50 (git merge-base --is-ancestor). Tests on a clean worktree at 41afda50 with PYTHONPATH set to that worktree: tools/tests/test_manifests_don_admin_s3_3.py 6 passed, 4 skipped; lifecycle-manager test_provision_alias_listed_require_g21, test_provision_register_c73, test_provision_unchanged_p29: 55 passed.
- A first run without PYTHONPATH gave 4 failures: the venv imports an older editable lifecycle_manager from another checkout (environment error, not a result; same trap as in the stage 2-3 prep notes).
- `record gate G21 --build-sha 41afda50...` NOT written: no stage-controller-records.jsonl exists on the GB10 host (~/.stage0-run and ~ to depth 4) or in the local task folders; the file is cwd-relative by default, so I do not know which file the controller driver reads. G22 was recorded somewhere I cannot find. Writing a new file at a guessed path could mislead. Need: path (or "create it at X").
- alerts-proven NOT recorded (not knowable). `field alert-test` NOT run: no FIELD_NTFY_* variable in the host environment, no ntfy file in ~/.field-local or the compose .env, and `field`/field_core is not installed on the host (only in containers). Nothing was sent. The coordinator must ask Don how the topic is to be configured; I will not create a topic (a secret).

## STEP B (not started, needs a decision)
- Read of current state (HIGH): kill-switch REQUIRE=1 in the container, other seven blank; all eight healthy; no override file in the deploy dir; .env has 0 FIELD_OPERATOR_REQUIRE lines. Shape = Stage 2. (Dropped counters and canary halt not re-read in this session.)
- The "existing monitor" is not a script on the host: ~/.stage0-run holds only per-run bundle copies up to s3-0 (no s2-6 or s3-6 there), and the 0430 report says the monitor was a harness task inside the earlier session. s2-6 / s3-6 live in a private tasks folder on rog-command and run through pg-run.py --live. A 5-minute loop that fires s2-6 on a trigger needs new glue plus an unattended live rollback, outside "no new rollback logic". Stopped.

## STEP C (not run, needs a decision)
- s3-6 as it stands has no Stage-2-shape check after the seven (it checks log-only once, after both ups). The 0430 proposal needs an edit to s3-6, which was not authorised. The existing local stub harness (dryrun.py) is pinned to a scratch worktree at 14fed1e and exercises s3-6 as written, not the proposed check. Without --live, pg-run.py sends nothing to the GB10.

## Decisions needed
1. Records file path for G21 (and later alerts-proven), or authority to create it where the driver will read it.
2. How the ntfy topic file is provisioned on the GB10 (Don/machine-to-machine); then alert-test, then Don confirms receipt in chat.
3. Step B: approve a session-run poller (this session polls every 5 min, calls the reviewed s2-6 via pg-run.py --live on trigger), or another owner; Step C: approve editing s3-6 locally (not deployed) to add the Stage-2-shape check, then stub-harness dry run.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
